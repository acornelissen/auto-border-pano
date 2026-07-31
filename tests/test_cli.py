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
