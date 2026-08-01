"""Tests for the cheap, read-only inspection the GUI does before committing.

Both tabs need to tell the user the consequence of their choices *before*
they press the button: how many frames this ratio will cut, and how these
sources will be arranged. Both answers exist in `geometry` and `layout`,
but `gui` may only import `pipeline`, so `pipeline` exposes them.
"""

from pathlib import Path

import pytest
from PIL import Image

from maskingframe import pipeline
from tests import conftest
from tests.conftest import synthetic_panorama


def test_facts_report_the_pixels_and_the_native_ratio(tmp_path: Path) -> None:
    source = tmp_path / "pano.jpg"
    synthetic_panorama(3000, 1000).save(source, "JPEG", quality=95)

    facts = pipeline.inspect_source(source)

    assert (facts.width, facts.height) == (3000, 1000)
    assert facts.native_ratio == "3.00:1"


def test_facts_round_the_native_ratio_to_two_places(tmp_path: Path) -> None:
    """At the size of the user's real scans. A flat fill rather than the
    gradient helper: this only reads the header, and generating 132M pixels
    in Python to check a rounding rule cost eight seconds of every run."""
    source = tmp_path / "pano.jpg"
    Image.new("RGB", (19921, 6607), "grey").save(source, "JPEG", quality=95)

    assert pipeline.inspect_source(source).native_ratio == "3.02:1"


def test_facts_count_every_frame_including_the_whole_panorama(tmp_path: Path) -> None:
    """The button says `Cut N frames`, and N has to be the number of files
    that appear on disk -- not the detail count, which is one fewer."""
    source = tmp_path / "pano.jpg"
    synthetic_panorama(3000, 1000).save(source, "JPEG", quality=95)

    for ratio in pipeline.RATIOS.values():
        facts = pipeline.inspect_source(source, ratio)
        written = pipeline.process_image(source, tmp_path / f"out_{ratio.name}", ratio)

        assert facts.frame_count == len(written), f"{ratio.name} disagreed"


def test_facts_never_promise_fewer_than_three_frames(tmp_path: Path) -> None:
    """`section_count` floors at two details, so the total floors at three."""
    source = tmp_path / "square.jpg"
    synthetic_panorama(1000, 900).save(source, "JPEG", quality=95)

    assert pipeline.inspect_source(source).frame_count >= 3


def test_inspecting_does_not_decode_the_whole_image(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """This runs on every file selection, against files that can be 132MP.
    Reading the header is the point; a full decode would stall the GUI."""
    source = tmp_path / "pano.jpg"
    synthetic_panorama(3000, 1000).save(source, "JPEG", quality=95)

    loaded: list[str] = []
    original = Image.Image.load

    def spy(self: Image.Image) -> object:
        loaded.append("decoded")
        return original(self)

    monkeypatch.setattr(Image.Image, "load", spy)

    pipeline.inspect_source(source)

    assert loaded == [], "inspect_source decoded pixel data it does not need"


def test_inspecting_a_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(OSError):
        pipeline.inspect_source(tmp_path / "nope.jpg")


def test_the_solved_arrangement_can_be_named_without_rendering_it(tmp_path: Path) -> None:
    """The Compose rail names the arrangement live, as the list changes. It
    must not have to render a full composite to do that."""
    sources = []
    for index, size in enumerate(((2000, 1000), (1000, 1000), (900, 1200))):
        path = tmp_path / f"n{index}.jpg"
        Image.new("RGB", size, "grey").save(path, "JPEG", quality=95)
        sources.append(path)

    named = pipeline.name_layout(sources, pipeline.DEFAULT_RATIO)
    _, rendered_name = pipeline.compose_preview(sources, pipeline.DEFAULT_RATIO)

    assert named == rendered_name


def test_naming_a_layout_matches_the_rendered_one_for_two_images(tmp_path: Path) -> None:
    sources = []
    for index, size in enumerate(((2000, 1000), (900, 1200))):
        path = tmp_path / f"n{index}.jpg"
        Image.new("RGB", size, "grey").save(path, "JPEG", quality=95)
        sources.append(path)

    named = pipeline.name_layout(sources, pipeline.DEFAULT_RATIO)
    _, rendered_name = pipeline.compose_preview(sources, pipeline.DEFAULT_RATIO)

    assert named == rendered_name


def test_naming_a_layout_rejects_a_count_it_cannot_arrange(tmp_path: Path) -> None:
    path = tmp_path / "one.jpg"
    Image.new("RGB", (100, 100), "grey").save(path, "JPEG", quality=95)

    with pytest.raises(ValueError):
        pipeline.name_layout([path], pipeline.DEFAULT_RATIO)


def test_facts_carry_the_default_positions(tmp_path: Path) -> None:
    source = tmp_path / "pano.jpg"
    conftest.synthetic_panorama(2000, 1000).save(source, "JPEG", quality=95)

    facts = pipeline.inspect_source(source, pipeline.RATIOS["4:5"])

    # frame_count counts the padded frame too, so there is one fewer position.
    assert len(facts.positions) == facts.frame_count - 1
    assert facts.positions[0] == 0.0
    assert facts.window_fraction == pytest.approx(0.4)


def test_facts_positions_follow_the_ratio(tmp_path: Path) -> None:
    source = tmp_path / "pano.jpg"
    conftest.synthetic_panorama(2000, 1000).save(source, "JPEG", quality=95)

    portrait = pipeline.inspect_source(source, pipeline.RATIOS["4:5"])
    landscape = pipeline.inspect_source(source, pipeline.RATIOS["1.91:1"])

    assert portrait.window_fraction < landscape.window_fraction


def test_the_gui_can_reach_the_position_model_without_importing_geometry() -> None:
    # gui/ may import only pipeline, so these have to be re-exported.
    for name in (
        "default_positions",
        "normalise_positions",
        "insert_position",
        "drop_position",
        "frame_width",
        "position_travel",
    ):
        assert callable(getattr(pipeline, name)), name


def test_ribbon_thumbnail_is_bounded_and_keeps_its_shape(tmp_path: Path) -> None:
    source = tmp_path / "pano.jpg"
    conftest.synthetic_panorama(4000, 800).save(source, "JPEG", quality=95)

    thumb = pipeline.ribbon_thumbnail(source, max_width=1200)

    assert thumb.width <= 1200
    assert thumb.width / thumb.height == pytest.approx(5.0, rel=0.01)
