"""Tests for rendering a split in memory, without writing it.

The Split tab offers a Preview alongside its primary action, so a user can
see what a ratio does to a panorama before committing frames to disk.
"""

from pathlib import Path

import pytest
from PIL import Image

from maskingframe import geometry, pipeline
from tests.conftest import synthetic_panorama


@pytest.fixture(autouse=True)
def _empty_cache() -> None:
    """No test here may inherit another's decoded source."""
    pipeline.clear_preview_cache()


def test_preview_renders_every_frame_the_run_would_write(tmp_path: Path) -> None:
    """Preview and the real run must not disagree about what they produce,
    or the preview is worse than showing nothing."""
    source = tmp_path / "pano.jpg"
    synthetic_panorama(3000, 1000).save(source, "JPEG", quality=95)

    for ratio in pipeline.RATIOS.values():
        frames = pipeline.preview_frames(source, ratio)
        written = pipeline.process_image(source, tmp_path / f"out_{ratio.name}", ratio)

        assert len(frames) == len(written), f"{ratio.name} disagreed on the count"


def test_preview_frames_come_out_at_the_target_size(tmp_path: Path) -> None:
    source = tmp_path / "pano.jpg"
    synthetic_panorama(3000, 1000).save(source, "JPEG", quality=95)
    ratio = pipeline.DEFAULT_RATIO

    frames = pipeline.preview_frames(source, ratio)

    for frame in frames:
        assert frame.size == (ratio.width, ratio.height)


def test_preview_writes_nothing(tmp_path: Path) -> None:
    source = tmp_path / "pano.jpg"
    synthetic_panorama(3000, 1000).save(source, "JPEG", quality=95)
    before = set(tmp_path.iterdir())

    pipeline.preview_frames(source)

    assert set(tmp_path.iterdir()) == before


def test_preview_rejects_portrait_input_the_same_way_a_run_does(tmp_path: Path) -> None:
    """Failing only once the user commits would be a worse discovery."""
    source = tmp_path / "tall.jpg"
    synthetic_panorama(800, 2000).save(source, "JPEG", quality=95)

    with pytest.raises(ValueError, match="portrait"):
        pipeline.preview_frames(source)


# --- the cached decode, which is what makes a re-render bearable -------------


def _counted_open(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record every file the pipeline decodes, in order."""
    opened: list[str] = []
    real = Image.open

    def spy(fp: object, *args: object, **kwargs: object) -> Image.Image:
        opened.append(str(fp))
        return real(fp, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Image, "open", spy)
    return opened


def test_a_cached_preview_reads_the_source_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A slider release must not cost a fresh decode of a 132MP scan."""
    source = tmp_path / "pano.jpg"
    synthetic_panorama(1200, 400).save(source, "JPEG", quality=95)
    opened = _counted_open(monkeypatch)

    pipeline.preview_frames(source, cached=True)
    pipeline.preview_frames(source, pipeline.RATIOS["1:1"], cached=True)

    assert opened == [str(source)]


def test_an_uncached_preview_reads_the_source_every_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "pano.jpg"
    synthetic_panorama(1200, 400).save(source, "JPEG", quality=95)
    opened = _counted_open(monkeypatch)

    pipeline.preview_frames(source)
    pipeline.preview_frames(source)

    assert len(opened) == 2


def test_the_cache_is_dropped_when_the_source_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = tmp_path / "one.jpg"
    second = tmp_path / "two.jpg"
    synthetic_panorama(1200, 400).save(first, "JPEG", quality=95)
    synthetic_panorama(900, 300).save(second, "JPEG", quality=95)
    opened = _counted_open(monkeypatch)

    pipeline.preview_frames(first, cached=True)
    pipeline.preview_frames(second, cached=True)
    pipeline.preview_frames(first, cached=True)

    assert opened == [str(first), str(second), str(first)]


def test_the_cache_is_dropped_when_the_file_is_rewritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same path, different picture. Keying on the name alone would show
    the old one for as long as the app stayed open."""
    source = tmp_path / "pano.jpg"
    synthetic_panorama(1200, 400).save(source, "JPEG", quality=95)
    pipeline.preview_frames(source, cached=True)

    synthetic_panorama(1500, 500).save(source, "JPEG", quality=95)
    opened = _counted_open(monkeypatch)
    frames = pipeline.preview_frames(source, cached=True)

    assert opened == [str(source)]
    assert len(frames) == len(pipeline.preview_frames(source))


def test_a_cached_preview_matches_an_uncached_one(tmp_path: Path) -> None:
    """A source inside the bound is cached untouched, so the two paths are
    the same picture -- not merely the same shape."""
    source = tmp_path / "pano.jpg"
    synthetic_panorama(1200, 400).save(source, "JPEG", quality=95)

    cached = pipeline.preview_frames(source, cached=True)
    plain = pipeline.preview_frames(source)

    assert [frame.tobytes() for frame in cached] == [frame.tobytes() for frame in plain]


def test_the_cached_copy_is_bounded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Never a full decode of a scan the pipeline itself lifts Pillow's
    guard for."""
    monkeypatch.setattr(pipeline, "PREVIEW_MAX_PIXELS", 60_000)
    source = tmp_path / "pano.jpg"
    synthetic_panorama(1200, 400).save(source, "JPEG", quality=95)

    pipeline.preview_frames(source, cached=True)
    cached = pipeline.cached_preview_source(source)

    assert cached.width * cached.height <= 60_000
    assert cached.size != (1200, 400)


def test_the_bound_never_softens_a_detail_frame() -> None:
    """A detail frame is cut from the source and scaled *up* to the ratio's
    full width, so a copy bounded too hard would visibly soften it. Every
    frame count the geometry actually produces must come out of the bounded
    copy at least as wide as it will be printed."""
    for aspect in (2.0, 2.33, 3.0, 5.0, 8.0, 13.0):
        width, height = pipeline.preview_source_size(
            round(30_000 * aspect), 30_000
        )  # a scan far above the bound
        for ratio in pipeline.RATIOS.values():
            count = geometry.section_count(width, height, ratio)
            assert width // count >= ratio.width, f"{aspect}:1 at {ratio.name}"
            assert height >= ratio.height, f"{aspect}:1 at {ratio.name}"


def test_a_written_run_ignores_the_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The one that protects output quality. Whatever the preview holds, a
    file on disk is cut from the full-resolution original."""
    source = tmp_path / "pano.jpg"
    synthetic_panorama(1200, 400).save(source, "JPEG", quality=95)

    reference = pipeline.process_image(source, tmp_path / "reference")
    expected = [path.read_bytes() for path in reference]

    # A bound small enough that using the cache could not possibly go
    # unnoticed: the copy is a fraction of the source's width.
    monkeypatch.setattr(pipeline, "PREVIEW_MAX_PIXELS", 60_000)
    pipeline.preview_frames(source, cached=True)
    assert pipeline.cached_preview_source(source).width < 1200

    written = pipeline.process_image(source, tmp_path / "after")

    assert [path.read_bytes() for path in written] == expected
