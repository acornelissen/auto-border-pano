"""Tests for the argparse entry point."""

from pathlib import Path

import pytest

from auto_border_pano import cli
from tests.conftest import synthetic_panorama


def test_single_file_mode_writes_outputs(tmp_path: Path) -> None:
    source = tmp_path / "pano.jpg"
    synthetic_panorama(600, 200).save(source, "JPEG", quality=95)

    exit_code = cli.main([str(source), str(tmp_path / "out")])

    assert exit_code == 0
    assert (tmp_path / "out_1_padded_square.jpg").exists()


def test_folder_mode_writes_outputs(tmp_path: Path) -> None:
    source_dir = tmp_path / "in"
    source_dir.mkdir()
    synthetic_panorama(600, 200).save(source_dir / "a.jpg", "JPEG", quality=95)

    exit_code = cli.main([str(source_dir), str(tmp_path / "out")])

    assert exit_code == 0
    assert (tmp_path / "out" / "a_1_padded_square.jpg").exists()


def test_missing_input_is_an_error(tmp_path: Path) -> None:
    assert cli.main([str(tmp_path / "nope.jpg")]) == 1


def test_default_prefix_is_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "pano.jpg"
    synthetic_panorama(600, 200).save(source, "JPEG", quality=95)

    assert cli.main([str(source)]) == 0
    assert (tmp_path / "output_1_padded_square.jpg").exists()


def test_folder_mode_default_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    source_dir = tmp_path / "in"
    source_dir.mkdir()
    synthetic_panorama(600, 200).save(source_dir / "a.jpg", "JPEG", quality=95)

    exit_code = cli.main([str(source_dir)])

    assert exit_code == 0
    assert (tmp_path / "output" / "a_1_padded_square.jpg").exists()


def test_gui_main_without_tkinter(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Simulate tkinter being unavailable by hiding it from sys.modules
    import sys

    # Remove tkinter from sys.modules if it exists
    monkeypatch.delitem(sys.modules, "tkinter", raising=False)

    # Mock __import__ to raise ImportError when tkinter is imported
    import builtins

    original_import = builtins.__import__

    def mock_import(  # type: ignore[no-untyped-def]
        name, globals_=None, locals_=None, fromlist=(), level=0
    ):
        if name == "tkinter":
            raise ImportError("No module named 'tkinter'")
        return original_import(name, globals_, locals_, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", mock_import)

    exit_code = cli.gui_main()

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "tkinter is not available" in captured.err
    assert "brew install python-tk" in captured.err
