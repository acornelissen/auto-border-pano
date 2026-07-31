"""Behavioural tests for the pure geometry transforms.

Covers padded-frame sizing at any target ratio (including the fallback that
grows the canvas from height when width-derived sizing would clip the
panorama), and section cropping/scaling (bounds, cover-scale, center-crop
offsets on both axes, and exact output size) across all registered ratios.
"""

import pytest

from auto_border_pano import geometry
from tests.conftest import synthetic_panorama


def test_padded_frame_is_exactly_the_target_ratio() -> None:
    for ratio in geometry.RATIOS.values():
        frame = geometry.make_padded_frame(synthetic_panorama(3000, 800), ratio)
        assert abs(frame.width / frame.height - ratio.value) < 0.01, ratio.name


def test_padded_frame_size_keeps_side_padding() -> None:
    # padded_frame_size (the pre-downscale composition maths) is unchanged
    # by the resize in make_padded_frame; this pins that directly rather
    # than reading it off the (now downscaled) output pixels.
    width, _ = geometry.padded_frame_size(3000, 800, geometry.SQUARE)
    assert width == 3000 + 2 * geometry.SIDE_PADDING


def _is_white(pixel: object) -> bool:
    assert isinstance(pixel, tuple)
    return all(channel > 250 for channel in pixel)


def test_padded_frame_pastes_at_side_padding_not_zero() -> None:
    # Kills a mutation that pastes at (0, 0) or at (SIDE_PADDING, VERTICAL_PADDING)
    # instead of centering. Coordinates are scaled: make_padded_frame downscales
    # the composed canvas to the output size, so the padding boundary in output
    # pixels is proportional, not literally SIDE_PADDING. Margins are generous
    # to stay clear of LANCZOS edge blur at the boundary.
    pano_width, pano_height = 3000, 800
    frame = geometry.make_padded_frame(synthetic_panorama(pano_width, pano_height), geometry.SQUARE)
    canvas_width, _ = geometry.padded_frame_size(pano_width, pano_height, geometry.SQUARE)
    scale = geometry.SQUARE.width / canvas_width
    boundary = geometry.SIDE_PADDING * scale
    mid_y = frame.height // 2
    assert _is_white(frame.getpixel((max(0, int(boundary) - 20), mid_y)))
    assert not _is_white(frame.getpixel((int(boundary) + 20, mid_y)))


def test_padded_frame_centers_vertically() -> None:
    pano_width, pano_height = 3000, 800
    frame = geometry.make_padded_frame(synthetic_panorama(pano_width, pano_height), geometry.SQUARE)
    _canvas_width, canvas_height = geometry.padded_frame_size(
        pano_width, pano_height, geometry.SQUARE
    )
    scale = geometry.SQUARE.height / canvas_height
    top_gap = (canvas_height - pano_height) // 2
    boundary = top_gap * scale
    mid_x = frame.width // 2
    assert _is_white(frame.getpixel((mid_x, max(0, int(boundary) - 20))))
    assert not _is_white(frame.getpixel((mid_x, int(boundary) + 20)))


def test_padded_frame_is_exactly_the_target_size() -> None:
    # Frame 1 must match the detail frames' pixel size exactly, not just
    # their ratio -- otherwise a large-format scan produces a whole-panorama
    # frame at full source resolution beside sub-megabyte detail frames.
    for ratio in geometry.RATIOS.values():
        frame = geometry.make_padded_frame(synthetic_panorama(3000, 800), ratio)
        assert frame.size == (ratio.width, ratio.height), ratio.name


def test_padded_frame_grows_when_ratio_would_clip_the_panorama() -> None:
    # A tall-ish input at 1.91:1: deriving height from width would leave the
    # panorama taller than the canvas, so the canvas is sized from height.
    # Tested against padded_frame_size directly -- the pre-downscale
    # composition maths that make_padded_frame's output no longer exposes,
    # since the final image is always exactly ratio.width x ratio.height.
    width, height = geometry.padded_frame_size(400, 2000, geometry.LANDSCAPE)
    assert height >= 2000 + 2 * geometry.VERTICAL_PADDING
    assert abs(width / height - geometry.LANDSCAPE.value) < 0.01


def test_section_bounds_split_on_integer_division() -> None:
    assert geometry.section_bounds(3001, 0, 3) == (0, 1000)
    assert geometry.section_bounds(3001, 1, 3) == (1000, 2000)
    assert geometry.section_bounds(3001, 2, 3) == (2000, 3000)


def test_section_bounds_validates_index() -> None:
    with pytest.raises(ValueError):
        geometry.section_bounds(3000, 3, 3)
    with pytest.raises(ValueError):
        geometry.section_bounds(3000, -1, 3)


def test_sections_are_exactly_the_target_size() -> None:
    panorama = synthetic_panorama(7205, 2997)
    for ratio in geometry.RATIOS.values():
        count = geometry.section_count(7205, 2997, ratio)
        for index in range(count):
            section = geometry.make_section(panorama, index, count, ratio)
            assert section.size == (ratio.width, ratio.height), (ratio.name, index)


def test_section_center_crop_uses_the_computed_offset_not_zero() -> None:
    # The gradient fixture is (x % 256, y % 256, (x + y) % 256), so a pixel's
    # red channel identifies its source column and green its source row.
    # A section scaled to cover and center-cropped must NOT start at the very
    # top of the source; offset 0 would put source row 0 at output row 0.
    #
    # This crop (300x900, 3 sections -> 100x900 per section) is narrower
    # relative to its height than PORTRAIT (0.8), so scaling to cover binds
    # on the width axis and overflows vertically, making the y-offset
    # nonzero. A 3000x800 panorama split into 2 does NOT exercise this: the
    # height axis binds exactly, giving a legitimately-zero offset.
    panorama = synthetic_panorama(300, 900)
    section = geometry.make_section(panorama, 0, 3, geometry.PORTRAIT)
    top_left = section.getpixel((0, 0))
    assert isinstance(top_left, tuple)
    assert top_left[1] != 0, "green channel 0 means source row 0 -- offset was not applied"


def test_section_center_crop_uses_the_computed_x_offset_not_zero() -> None:
    # Wide crop: cover-scaling binds on height and overflows horizontally,
    # so the x-offset must be nonzero. Red channel encodes the source column.
    panorama = synthetic_panorama(3000, 800)
    section = geometry.make_section(panorama, 0, 3, geometry.SQUARE)
    top_left = section.getpixel((0, 0))
    assert isinstance(top_left, tuple)
    assert top_left[0] != 0, "red channel 0 means source column 0 -- x offset was not applied"


def test_adjacent_sections_show_different_parts_of_the_panorama() -> None:
    # Kills a mutation that ignores `index` and always crops the same region.
    panorama = synthetic_panorama(3000, 800)
    first = geometry.make_section(panorama, 0, 3, geometry.SQUARE)
    second = geometry.make_section(panorama, 1, 3, geometry.SQUARE)
    assert first.getpixel((0, 0)) != second.getpixel((0, 0))


def test_ratio_output_sizes_are_exact() -> None:
    assert (geometry.SQUARE.width, geometry.SQUARE.height) == (1080, 1080)
    assert (geometry.PORTRAIT.width, geometry.PORTRAIT.height) == (1080, 1350)
    assert (geometry.LANDSCAPE.width, geometry.LANDSCAPE.height) == (1080, 566)


def test_ratios_are_registered_by_name() -> None:
    assert set(geometry.RATIOS) == {"1:1", "4:5", "1.91:1"}
    assert geometry.RATIOS["4:5"] is geometry.PORTRAIT
    assert geometry.DEFAULT_RATIO is geometry.PORTRAIT


def test_typical_panorama_counts_match_real_samples() -> None:
    # 2.40:1 is the most common aspect across the user's real scans.
    width, height = 7205, 2997
    assert geometry.section_count(width, height, geometry.LANDSCAPE) == 2
    assert geometry.section_count(width, height, geometry.SQUARE) == 2
    assert geometry.section_count(width, height, geometry.PORTRAIT) == 3


def test_large_format_panorama_counts_match_real_samples() -> None:
    # 3.02:1, the two 617 scans.
    width, height = 19921, 6607
    assert geometry.section_count(width, height, geometry.LANDSCAPE) == 2
    assert geometry.section_count(width, height, geometry.SQUARE) == 3
    assert geometry.section_count(width, height, geometry.PORTRAIT) == 4


def test_count_is_floored_at_two() -> None:
    # Tiling alone wants 1 here; the floor is what makes the frames a zoom
    # rather than a restatement of the whole-panorama frame.
    assert geometry.section_count(2400, 1000, geometry.LANDSCAPE) == 2


def test_count_floors_at_two_even_when_narrower_than_one_tile() -> None:
    assert geometry.section_count(500, 1000, geometry.PORTRAIT) == 2


def test_count_rounds_half_up_not_bankers() -> None:
    # tile = 1000 * 1.0 = 1000; 2500/1000 = 2.5 exactly.
    # Python's round() would give 2 (banker's rounding); we want 3.
    assert geometry.section_count(2500, 1000, geometry.SQUARE) == 3


def test_section_count_differs_by_ratio_for_the_golden_fixture() -> None:
    # Repoints what used to be a self-referential golden-hash-count check at
    # the production function it was meant to guard. golden_wide.jpg is
    # 600x250.
    width, height = 600, 250
    counts = {
        ratio.name: geometry.section_count(width, height, ratio)
        for ratio in geometry.RATIOS.values()
    }
    assert counts["4:5"] > counts["1:1"], counts
    assert counts["1:1"] >= counts["1.91:1"], counts
