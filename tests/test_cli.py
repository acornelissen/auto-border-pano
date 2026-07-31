"""Tests for the argparse entry point."""

from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from auto_border_pano import cli, pipeline
from tests.conftest import synthetic_panorama


def test_single_file_mode_writes_outputs(tmp_path: Path) -> None:
    source = tmp_path / "pano.jpg"
    synthetic_panorama(600, 200).save(source, "JPEG", quality=95)

    exit_code = cli.main([str(source), str(tmp_path / "out")])

    assert exit_code == 0
    assert (tmp_path / "out_1_padded.jpg").exists()


def test_folder_mode_writes_outputs(tmp_path: Path) -> None:
    source_dir = tmp_path / "in"
    source_dir.mkdir()
    synthetic_panorama(600, 200).save(source_dir / "a.jpg", "JPEG", quality=95)

    exit_code = cli.main([str(source_dir), str(tmp_path / "out")])

    assert exit_code == 0
    assert (tmp_path / "out" / "a_1_padded.jpg").exists()


def test_missing_input_is_an_error(tmp_path: Path) -> None:
    assert cli.main([str(tmp_path / "nope.jpg")]) == 1


def test_folder_mode_with_one_bad_file_exits_nonzero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source_dir = tmp_path / "in"
    source_dir.mkdir()
    synthetic_panorama(600, 200).save(source_dir / "good.jpg", "JPEG", quality=95)
    (source_dir / "broken.jpg").write_text("not an image")

    exit_code = cli.main([str(source_dir), str(tmp_path / "out")])

    assert exit_code == 1
    assert (tmp_path / "out" / "good_1_padded.jpg").exists()
    captured = capsys.readouterr()
    assert "broken.jpg" in captured.err


def test_single_file_non_oserror_failure_prints_clean_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # PIL.Image.DecompressionBombError subclasses Exception directly, not
    # OSError or ValueError. A narrow except tuple lets it raise straight
    # through main() as a traceback instead of a clean stderr message.
    source = tmp_path / "pano.jpg"
    synthetic_panorama(600, 200).save(source, "JPEG", quality=95)

    def boom(*_args: Any, **_kwargs: Any) -> list[Path]:
        raise Image.DecompressionBombError("synthetic bomb")

    monkeypatch.setattr(pipeline, "process_image", boom)

    exit_code = cli.main([str(source), str(tmp_path / "out")])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "synthetic bomb" in captured.err


def test_empty_folder_prints_clear_message_and_exits_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source_dir = tmp_path / "in"
    source_dir.mkdir()

    exit_code = cli.main([str(source_dir), str(tmp_path / "out")])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert f"No JPG files found in '{source_dir}'" in captured.out


def test_default_prefix_is_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "pano.jpg"
    synthetic_panorama(600, 200).save(source, "JPEG", quality=95)

    assert cli.main([str(source)]) == 0
    assert (tmp_path / "output_1_padded.jpg").exists()


def test_folder_mode_default_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    source_dir = tmp_path / "in"
    source_dir.mkdir()
    synthetic_panorama(600, 200).save(source_dir / "a.jpg", "JPEG", quality=95)

    exit_code = cli.main([str(source_dir)])

    assert exit_code == 0
    assert (tmp_path / "output" / "a_1_padded.jpg").exists()


def test_gui_main_without_qt(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Missing the GUI toolkit must explain itself and exit non-zero, not
    raise. The guard lives in cli rather than at the GUI package's module
    scope so that importing the package can never kill the host process."""
    import builtins
    import sys

    monkeypatch.delitem(sys.modules, "PySide6", raising=False)
    original_import = builtins.__import__

    def mock_import(  # type: ignore[no-untyped-def]
        name, globals_=None, locals_=None, fromlist=(), level=0
    ):
        if name == "PySide6":
            raise ImportError("No module named 'PySide6'")
        return original_import(name, globals_, locals_, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", mock_import)

    exit_code = cli.gui_main()

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "PySide6 is not available" in captured.err
    assert "pano-split --help" in captured.err


def test_ratio_flag_changes_the_output_shape(tmp_path: Path) -> None:
    source = tmp_path / "pano.jpg"
    synthetic_panorama(3000, 1250).save(source, "JPEG", quality=95)

    assert cli.main([str(source), str(tmp_path / "wide"), "--ratio", "1.91:1"]) == 0

    with Image.open(tmp_path / "wide_2_section1.jpg") as img:
        assert img.size == (1080, 566)


def test_default_ratio_is_four_five(tmp_path: Path) -> None:
    source = tmp_path / "pano.jpg"
    synthetic_panorama(3000, 1250).save(source, "JPEG", quality=95)

    assert cli.main([str(source), str(tmp_path / "out")]) == 0

    with Image.open(tmp_path / "out_2_section1.jpg") as img:
        assert img.size == (1080, 1350)


def test_unknown_ratio_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "pano.jpg"
    synthetic_panorama(3000, 1250).save(source, "JPEG", quality=95)

    with pytest.raises(SystemExit):
        cli.main([str(source), str(tmp_path / "out"), "--ratio", "16:9"])


@pytest.mark.parametrize(
    ("spelling", "expected_size"),
    [
        ("4:5", (1080, 1350)),
        ("portrait", (1080, 1350)),
        ("PORTRAIT", (1080, 1350)),
        ("Portrait", (1080, 1350)),
        ("1:1", (1080, 1080)),
        ("square", (1080, 1080)),
        ("SQUARE", (1080, 1080)),
        ("1.91:1", (1080, 566)),
        ("landscape", (1080, 566)),
        ("LANDSCAPE", (1080, 566)),
    ],
)
def test_ratio_flag_accepts_names_and_labels_case_insensitively(
    tmp_path: Path, spelling: str, expected_size: tuple[int, int]
) -> None:
    source = tmp_path / "pano.jpg"
    synthetic_panorama(3000, 1250).save(source, "JPEG", quality=95)

    assert cli.main([str(source), str(tmp_path / "out"), "--ratio", spelling]) == 0

    with Image.open(tmp_path / "out_2_section1.jpg") as img:
        assert img.size == expected_size


def test_unknown_ratio_message_names_the_accepted_options(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "pano.jpg"
    synthetic_panorama(3000, 1250).save(source, "JPEG", quality=95)

    with pytest.raises(SystemExit) as excinfo:
        cli.main([str(source), str(tmp_path / "out"), "--ratio", "16:9"])

    assert excinfo.value.code != 0
    captured = capsys.readouterr()
    assert "portrait|4:5" in captured.err
    assert "square|1:1" in captured.err
    assert "landscape|1.91:1" in captured.err


def test_ratio_choices_are_presented_narrowest_to_widest_not_alphabetical() -> None:
    help_text = cli.build_parser().format_help()
    assert help_text.index("portrait|4:5") < help_text.index("square|1:1")
    assert help_text.index("square|1:1") < help_text.index("landscape|1.91:1")


def test_portrait_input_exits_nonzero(tmp_path: Path) -> None:
    source = tmp_path / "tall.jpg"
    synthetic_panorama(800, 3000).save(source, "JPEG", quality=95)

    assert cli.main([str(source), str(tmp_path / "out")]) == 1
