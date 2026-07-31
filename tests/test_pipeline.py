"""Tests for the file-I/O layer."""

import hashlib
from pathlib import Path

import pytest
from PIL import Image

from auto_border_pano import pipeline
from tests.conftest import synthetic_panorama

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# SHA-256 of each output produced from tests/fixtures/golden_panorama.jpg by
# the *current* code, which was manually verified byte-identical to the
# pre-refactor reference outputs during the src-layout migration. This test
# is the standing guard for that "no output image may change" constraint;
# without it, nothing catches a future regression, since `reference/` (the
# original one-time comparison target) is gitignored.
#
# These hashes are tied to the installed Pillow version's JPEG encoder. If a
# deliberate Pillow upgrade changes encoding, regenerate them with:
#   uv run python -c "
#   import hashlib, pathlib
#   from auto_border_pano import pipeline
#   out = pipeline.process_image(
#       'tests/fixtures/golden_panorama.jpg', '/tmp/golden_regen/golden'
#   )
#   for p in out:
#       print(p.name, hashlib.sha256(p.read_bytes()).hexdigest())
#   "
# and confirm the change is expected (e.g. by diffing the images visually)
# before updating the values below.
GOLDEN_OUTPUT_HASHES = {
    "golden_1_padded_square.jpg": (
        "767abc12bc4a5146f3db687411cbd2293f1335b5e44e666637e8cdf45de98672"
    ),
    "golden_2_section1.jpg": "6311ba82c3a97f6d387f8dcff38908806e4816cbbb0ace68fb803a5d0ef297de",
    "golden_3_section2.jpg": "ce564811141462bafa31cfdd353eaa00ef65a81082670cd620221003044189bd",
    "golden_4_section3.jpg": "215a7d9cd5c6bb8cc01e3ae9cf2f66c4f152e01b9fb964935013d337c0963a0c",
}


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
    result = pipeline.process_folder(
        source_dir,
        out_dir,
        on_progress=lambda done, total, path: seen.append((done, total, path.name)),
    )

    assert out_dir.is_dir()
    assert len(result.written) == 8
    assert result.failed == []
    assert result.succeeded_count == 2
    assert [s[:2] for s in seen] == [(0, 2), (1, 2)]


def test_process_folder_continues_after_a_bad_file(tmp_path: Path) -> None:
    source_dir = tmp_path / "in"
    source_dir.mkdir()
    _write_panorama(source_dir / "good.jpg", 600, 200)
    (source_dir / "broken.jpg").write_text("not an image")

    result = pipeline.process_folder(source_dir, tmp_path / "out")

    assert len(result.written) == 4
    assert result.succeeded_count == 1
    assert len(result.failed) == 1
    failed_path, message = result.failed[0]
    assert failed_path.name == "broken.jpg"
    assert message
    assert result.last_prefix == tmp_path / "out" / "good"


def test_process_folder_fully_failing_batch_is_distinguishable(
    tmp_path: Path,
) -> None:
    source_dir = tmp_path / "in"
    source_dir.mkdir()
    (source_dir / "broken1.jpg").write_text("not an image")
    (source_dir / "broken2.jpg").write_text("also not an image")

    result = pipeline.process_folder(source_dir, tmp_path / "out")

    assert result.written == []
    assert result.succeeded_count == 0
    assert len(result.failed) == 2
    assert result.last_prefix is None


def test_process_folder_continues_past_a_non_oserror_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # PIL.Image.DecompressionBombError subclasses Exception directly, not
    # OSError or ValueError -- exactly what a huge panorama triggers. A
    # narrow except tuple here would abort the whole batch, which is the
    # one thing process_folder's docstring promises it prevents.
    source_dir = tmp_path / "in"
    source_dir.mkdir()
    _write_panorama(source_dir / "good.jpg", 600, 200)
    _write_panorama(source_dir / "huge.jpg", 600, 200)

    real_process_image = pipeline.process_image

    def fake_process_image(input_path: Path, output_prefix: Path) -> list[Path]:
        if Path(input_path).name == "huge.jpg":
            raise Image.DecompressionBombError("synthetic bomb")
        return real_process_image(input_path, output_prefix)

    monkeypatch.setattr(pipeline, "process_image", fake_process_image)

    result = pipeline.process_folder(source_dir, tmp_path / "out")

    assert result.succeeded_count == 1
    assert len(result.failed) == 1
    assert result.failed[0][0].name == "huge.jpg"
    assert "synthetic bomb" in result.failed[0][1]


def test_golden_panorama_outputs_are_byte_identical(tmp_path: Path) -> None:
    written = pipeline.process_image(FIXTURES_DIR / "golden_panorama.jpg", tmp_path / "golden")
    actual_hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in written}
    assert actual_hashes == GOLDEN_OUTPUT_HASHES
