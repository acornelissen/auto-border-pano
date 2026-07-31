"""Tests for rendering a split in memory, without writing it.

The Split tab offers a Preview alongside its primary action, so a user can
see what a ratio does to a panorama before committing frames to disk.
"""

from pathlib import Path

import pytest

from auto_border_pano import pipeline
from tests.conftest import synthetic_panorama


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
