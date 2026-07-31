"""Tests for the file-I/O layer."""

from pathlib import Path

from PIL import Image

from auto_border_pano import pipeline
from tests.conftest import synthetic_panorama


def _write_panorama(path: Path, width: int = 3000, height: int = 800) -> Path:
    synthetic_panorama(width, height).save(path, "JPEG", quality=95)
    return path


def test_output_paths_follow_the_naming_contract() -> None:
    paths = pipeline.output_paths("/tmp/holiday")
    assert [p.name for p in paths] == [
        "holiday_1_padded_square.jpg",
        "holiday_2_section1.jpg",
        "holiday_3_section2.jpg",
        "holiday_4_section3.jpg",
    ]


def test_process_image_writes_four_files(tmp_path: Path) -> None:
    source = _write_panorama(tmp_path / "pano.jpg")
    written = pipeline.process_image(source, tmp_path / "out")
    assert len(written) == 4
    assert all(p.exists() for p in written)


def test_process_image_output_dimensions(tmp_path: Path) -> None:
    source = _write_panorama(tmp_path / "pano.jpg")
    written = pipeline.process_image(source, tmp_path / "out")
    with Image.open(written[0]) as square:
        assert square.size == (3200, 3200)
    for section in written[1:]:
        with Image.open(section) as img:
            assert img.size == (1080, 1080)


def test_find_panoramas_matches_all_jpeg_spellings(tmp_path: Path) -> None:
    for name in ("a.jpg", "b.JPG", "c.jpeg", "d.JPEG", "ignore.png"):
        (tmp_path / name).touch()
    found = {p.name for p in pipeline.find_panoramas(tmp_path)}
    assert found == {"a.jpg", "b.JPG", "c.jpeg", "d.JPEG"}


def test_find_panoramas_does_not_return_duplicates(tmp_path: Path) -> None:
    # On a case-insensitive filesystem (macOS default) naive globbing of
    # both *.jpg and *.JPG returns the same file twice.
    (tmp_path / "only.jpg").touch()
    assert len(pipeline.find_panoramas(tmp_path)) == 1


def test_process_folder_creates_output_dir_and_reports_progress(
    tmp_path: Path,
) -> None:
    source_dir = tmp_path / "in"
    source_dir.mkdir()
    _write_panorama(source_dir / "one.jpg", 600, 200)
    _write_panorama(source_dir / "two.jpg", 600, 200)
    out_dir = tmp_path / "out"

    seen: list[tuple[int, int, str]] = []
    written = pipeline.process_folder(
        source_dir,
        out_dir,
        on_progress=lambda done, total, path: seen.append(
            (done, total, path.name)
        ),
    )

    assert out_dir.is_dir()
    assert len(written) == 8
    assert [s[:2] for s in seen] == [(0, 2), (1, 2)]


def test_process_folder_continues_after_a_bad_file(tmp_path: Path) -> None:
    source_dir = tmp_path / "in"
    source_dir.mkdir()
    _write_panorama(source_dir / "good.jpg", 600, 200)
    (source_dir / "broken.jpg").write_text("not an image")

    written = pipeline.process_folder(source_dir, tmp_path / "out")
    assert len(written) == 4
