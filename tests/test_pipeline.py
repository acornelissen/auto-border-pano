"""Tests for the file-I/O layer."""

from pathlib import Path

import pytest
from PIL import Image

from auto_border_pano import pipeline
from tests.conftest import synthetic_panorama


def _write_panorama(path: Path, width: int = 3000, height: int = 1250) -> Path:
    synthetic_panorama(width, height).save(path, "JPEG", quality=95)
    return path


def test_output_paths_follow_the_naming_contract() -> None:
    paths = pipeline.output_paths("/tmp/holiday", 3)
    assert [p.name for p in paths] == [
        "holiday_1_padded.jpg",
        "holiday_2_section1.jpg",
        "holiday_3_section2.jpg",
        "holiday_4_section3.jpg",
    ]


def test_output_paths_length_tracks_the_count() -> None:
    assert len(pipeline.output_paths("/tmp/x", 2)) == 3
    assert len(pipeline.output_paths("/tmp/x", 5)) == 6


def test_process_image_writes_frame_one_plus_detail_frames(tmp_path: Path) -> None:
    source = _write_panorama(tmp_path / "pano.jpg", 3000, 1250)
    written = pipeline.process_image(source, tmp_path / "out", pipeline.RATIOS["4:5"])
    assert len(written) == 1 + 3
    assert all(p.exists() for p in written)


def test_process_image_output_sizes_match_the_ratio(tmp_path: Path) -> None:
    source = _write_panorama(tmp_path / "pano.jpg", 3000, 1250)
    for ratio in pipeline.RATIOS.values():
        written = pipeline.process_image(source, tmp_path / ratio.name, ratio)
        with Image.open(written[0]) as frame:
            assert abs(frame.width / frame.height - ratio.value) < 0.01
        for detail in written[1:]:
            with Image.open(detail) as img:
                assert img.size == (ratio.width, ratio.height)


def test_process_image_rejects_portrait_input(tmp_path: Path) -> None:
    source = _write_panorama(tmp_path / "tall.jpg", 800, 3000)
    with pytest.raises(ValueError, match="portrait"):
        pipeline.process_image(source, tmp_path / "out")


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
    _write_panorama(source_dir / "one.jpg", 3000, 1250)
    _write_panorama(source_dir / "two.jpg", 3000, 1250)
    out_dir = tmp_path / "out"

    seen: list[tuple[int, int, str]] = []
    result = pipeline.process_folder(
        source_dir,
        out_dir,
        on_progress=lambda done, total, path: seen.append((done, total, path.name)),
    )

    assert out_dir.is_dir()
    # At the default 4:5 ratio a 3000x1250 panorama produces 1 padded frame
    # plus 3 detail frames per source; sizing the fixtures rather than
    # recomputing via geometry.section_count keeps this test from passing
    # vacuously if both it and the production code were wrong together.
    assert len(result.written) == 2 * (1 + 3)
    assert result.failed == []
    assert result.succeeded_count == 2
    assert [s[:2] for s in seen] == [(0, 2), (1, 2)]


def test_process_folder_continues_after_a_bad_file(tmp_path: Path) -> None:
    source_dir = tmp_path / "in"
    source_dir.mkdir()
    _write_panorama(source_dir / "good.jpg", 3000, 1250)
    (source_dir / "broken.jpg").write_text("not an image")

    result = pipeline.process_folder(source_dir, tmp_path / "out")

    assert len(result.written) == 1 + 3
    assert result.succeeded_count == 1
    assert len(result.failed) == 1
    failed_path, message = result.failed[0]
    assert failed_path.name == "broken.jpg"
    assert message
    assert result.last_prefix == tmp_path / "out" / "good"
    assert result.last_count == 3


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
    assert result.last_count is None


def test_process_folder_continues_past_a_non_oserror_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # PIL.Image.DecompressionBombError subclasses Exception directly, not
    # OSError or ValueError -- exactly what a huge panorama triggers. A
    # narrow except tuple here would abort the whole batch, which is the
    # one thing process_folder's docstring promises it prevents.
    source_dir = tmp_path / "in"
    source_dir.mkdir()
    _write_panorama(source_dir / "good.jpg", 3000, 1250)
    _write_panorama(source_dir / "huge.jpg", 3000, 1250)

    real_process_image = pipeline.process_image

    def fake_process_image(
        input_path: Path,
        output_prefix: Path,
        ratio: pipeline.AspectRatio = pipeline.DEFAULT_RATIO,
    ) -> list[Path]:
        if Path(input_path).name == "huge.jpg":
            raise Image.DecompressionBombError("synthetic bomb")
        return real_process_image(input_path, output_prefix, ratio)

    monkeypatch.setattr(pipeline, "process_image", fake_process_image)

    result = pipeline.process_folder(source_dir, tmp_path / "out")

    assert result.succeeded_count == 1
    assert len(result.failed) == 1
    assert result.failed[0][0].name == "huge.jpg"
    assert "synthetic bomb" in result.failed[0][1]


def test_portrait_input_is_recorded_as_a_failure_not_an_abort(tmp_path: Path) -> None:
    source_dir = tmp_path / "in"
    source_dir.mkdir()
    _write_panorama(source_dir / "good.jpg", 3000, 1250)
    _write_panorama(source_dir / "tall.jpg", 800, 3000)

    result = pipeline.process_folder(source_dir, tmp_path / "out")

    assert result.succeeded_count == 1
    assert [p.name for p, _ in result.failed] == ["tall.jpg"]
    assert "portrait" in result.failed[0][1]


def test_batch_result_counts_sources_not_files(tmp_path: Path) -> None:
    source_dir = tmp_path / "in"
    source_dir.mkdir()
    _write_panorama(source_dir / "a.jpg", 3000, 1250)
    _write_panorama(source_dir / "b.jpg", 3000, 1250)

    result = pipeline.process_folder(source_dir, tmp_path / "out")

    assert result.succeeded_count == 2
    assert result.total_count == 2
    assert result.last_count == 3
