"""Tests for the argparse entry point."""

import argparse
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from maskingframe import cli, pipeline
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
    assert "maskingframe --help" in captured.err


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


def test_defaults_produce_the_default_style() -> None:
    args = cli.build_parser().parse_args(["in.jpg"])
    assert cli._style_from_args(args) == pipeline.DEFAULT_STYLE


def test_flags_build_a_style() -> None:
    args = cli.build_parser().parse_args(
        [
            "in.jpg",
            "--border",
            "12",
            "--border-colour",
            "#000",
            "--gutter",
            "2.5",
            "--gutter-colour",
            "c9302a",
            "--border-detail-frames",
        ]
    )
    style = cli._style_from_args(args)
    assert style.border_percent == 12.0
    assert style.border_colour == "#000000"
    assert style.gutter_percent == 2.5
    assert style.gutter_colour == "#c9302a"
    assert style.border_detail_frames is True


def test_american_spellings_are_accepted() -> None:
    args = cli.build_parser().parse_args(["in.jpg", "--border-color", "#000000"])
    assert cli._style_from_args(args).border_colour == "#000000"

    args = cli.build_parser().parse_args(["in.jpg", "--gutter-color", "#000000"])
    assert cli._style_from_args(args).gutter_colour == "#000000"


@pytest.mark.parametrize("flag", ["--border", "--gutter"])
@pytest.mark.parametrize("value", ["-1", "41", "banana"])
def test_out_of_range_widths_are_rejected(flag: str, value: str) -> None:
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["in.jpg", flag, value])


def test_bad_colour_is_rejected() -> None:
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["in.jpg", "--border-colour", "chartreuse"])


def test_border_flags_reach_the_written_image(tmp_path: Path) -> None:
    source = tmp_path / "pano.jpg"
    synthetic_panorama(3000, 1250).save(source, "JPEG", quality=95)

    exit_code = cli.main(
        [str(source), str(tmp_path / "out"), "--border", "12", "--border-colour", "#c9302a"]
    )

    assert exit_code == 0
    with Image.open(tmp_path / "out_1_padded.jpg") as padded:
        assert padded.convert("RGB").getpixel((0, 0)) == (201, 48, 42)


def test_border_flags_reach_a_batch_run(tmp_path: Path) -> None:
    source_dir = tmp_path / "in"
    source_dir.mkdir()
    synthetic_panorama(3000, 1250).save(source_dir / "a.jpg", "JPEG", quality=95)

    exit_code = cli.main([str(source_dir), str(tmp_path / "out"), "--border-colour", "#c9302a"])

    assert exit_code == 0
    with Image.open(tmp_path / "out" / "a_1_padded.jpg") as padded:
        assert padded.convert("RGB").getpixel((0, 0)) == (201, 48, 42)


def test_percent_type_rejects_out_of_range() -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        cli._percent_type("41")


def test_help_lists_the_new_flags() -> None:
    help_text = cli.build_parser().format_help()
    for flag in ("--border", "--border-colour", "--gutter", "--gutter-colour"):
        assert flag in help_text
    assert "--border-color" in help_text
    assert "--gutter-color" in help_text
    assert "composites only" in help_text


# --- compose subcommand -------------------------------------------------
#
# The compose path shares every style flag with the split path, so these
# tests concentrate on what is genuinely different: the variable-length
# input list, the -o output, and the layout name reaching stdout.

COMPOSE_FIXTURES = [
    str(Path(__file__).parent / "fixtures" / name)
    for name in ("compose_wide.jpg", "compose_square.jpg", "compose_tall.jpg")
]


def test_compose_two_inputs_writes_a_diptych(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = cli.main(["compose", *COMPOSE_FIXTURES[:2], "-o", str(tmp_path / "out")])

    assert exit_code == 0
    assert (tmp_path / "out_diptych.jpg").exists()
    assert "out_diptych.jpg" in capsys.readouterr().out


def test_compose_three_inputs_writes_a_triptych(tmp_path: Path) -> None:
    exit_code = cli.main(["compose", *COMPOSE_FIXTURES, "--output", str(tmp_path / "out")])

    assert exit_code == 0
    assert (tmp_path / "out_triptych.jpg").exists()


def test_compose_prints_the_winning_layout(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    expected = pipeline.name_layout(COMPOSE_FIXTURES[:2])

    assert cli.main(["compose", *COMPOSE_FIXTURES[:2], "-o", str(tmp_path / "out")]) == 0
    assert expected in capsys.readouterr().out


def test_compose_rejects_one_input(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        cli.main(["compose", COMPOSE_FIXTURES[0], "-o", str(tmp_path / "out")])


def test_compose_rejects_four_inputs(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        cli.main(["compose", *COMPOSE_FIXTURES, COMPOSE_FIXTURES[0], "-o", str(tmp_path / "out")])
    assert "4" in capsys.readouterr().err


def test_compose_defaults_its_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    assert cli.main(["compose", *COMPOSE_FIXTURES[:2]]) == 0
    assert (tmp_path / "output_diptych.jpg").exists()


def test_compose_missing_input_is_an_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = str(tmp_path / "nope.jpg")

    exit_code = cli.main(["compose", COMPOSE_FIXTURES[0], missing, "-o", str(tmp_path / "out")])

    assert exit_code == 1
    assert "nope.jpg" in capsys.readouterr().err
    assert not (tmp_path / "out_diptych.jpg").exists()


def test_compose_accepts_portrait_input(tmp_path: Path) -> None:
    tall = str(Path(__file__).parent / "fixtures" / "compose_tall.jpg")

    assert cli.main(["compose", tall, tall, "-o", str(tmp_path / "out")]) == 0
    assert (tmp_path / "out_diptych.jpg").exists()


def test_compose_gutter_colour_reaches_the_written_pixels(tmp_path: Path) -> None:
    exit_code = cli.main(
        [
            "compose",
            *COMPOSE_FIXTURES[:2],
            "-o",
            str(tmp_path / "out"),
            "--border",
            "0",
            "--gutter",
            "6",
            "--gutter-colour",
            "#c9302a",
        ]
    )

    assert exit_code == 0
    with Image.open(tmp_path / "out_diptych.jpg") as composite:
        raw = composite.convert("RGB").tobytes()
    closest = min(
        (raw[i] - 201) ** 2 + (raw[i + 1] - 48) ** 2 + (raw[i + 2] - 42) ** 2
        for i in range(0, len(raw), 3)
    )
    assert closest < 200, "the gutter colour never landed in the composite"


def test_compose_ratio_reaches_the_written_image(tmp_path: Path) -> None:
    exit_code = cli.main(
        ["compose", *COMPOSE_FIXTURES[:2], "-o", str(tmp_path / "out"), "--ratio", "square"]
    )

    assert exit_code == 0
    with Image.open(tmp_path / "out_diptych.jpg") as composite:
        assert composite.size == (pipeline.RATIOS["1:1"].width, pipeline.RATIOS["1:1"].height)


def test_a_file_literally_named_compose_still_splits(tmp_path: Path) -> None:
    # The bare form is dispatched by the first argument, so a source file
    # whose own name is "compose" must not be mistaken for the subcommand.
    monkeypatched = tmp_path / "compose"
    synthetic_panorama(600, 200).save(monkeypatched, "JPEG", quality=95)

    exit_code = cli.main([str(monkeypatched), str(tmp_path / "out")])

    assert exit_code == 0
    assert (tmp_path / "out_1_padded.jpg").exists()


def test_bare_form_is_unchanged_by_the_subcommand(tmp_path: Path) -> None:
    source = tmp_path / "pano.jpg"
    synthetic_panorama(600, 200).save(source, "JPEG", quality=95)

    exit_code = cli.main([str(source), str(tmp_path / "out"), "--ratio", "1:1"])

    assert exit_code == 0
    assert sorted(p.name for p in tmp_path.glob("out_*.jpg")) == [
        "out_1_padded.jpg",
        "out_2_section1.jpg",
        "out_3_section2.jpg",
        "out_4_section3.jpg",
    ]


def test_compose_help_mentions_the_subcommand() -> None:
    assert "compose" in cli.build_parser().format_help()
    compose_help = cli.build_compose_parser().format_help()
    assert "--gutter" in compose_help
    assert "-o" in compose_help
