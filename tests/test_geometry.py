"""Characterisation tests for the pure geometry transforms.

These lock in current behaviour exactly, including the padding quirk where
the vertical padding constant only influences canvas size and the panorama
ends up vertically centered.
"""

import pytest

from auto_border_pano import geometry
from tests.conftest import synthetic_panorama


def test_padded_frame_is_exactly_the_target_ratio() -> None:
    for ratio in geometry.RATIOS.values():
        frame = geometry.make_padded_frame(synthetic_panorama(3000, 800), ratio)
        assert abs(frame.width / frame.height - ratio.value) < 0.01, ratio.name


def test_padded_frame_keeps_side_padding() -> None:
    frame = geometry.make_padded_frame(synthetic_panorama(3000, 800), geometry.SQUARE)
    assert frame.width == 3000 + 2 * geometry.SIDE_PADDING


def test_padded_frame_pastes_at_side_padding_not_zero() -> None:
    # Kills a mutation that pastes at (0, 0) or at (SIDE_PADDING, VERTICAL_PADDING)
    # instead of centering.
    frame = geometry.make_padded_frame(synthetic_panorama(3000, 800), geometry.SQUARE)
    mid_y = frame.height // 2
    assert frame.getpixel((geometry.SIDE_PADDING - 1, mid_y)) == (255, 255, 255)
    assert frame.getpixel((geometry.SIDE_PADDING + 1, mid_y)) != (255, 255, 255)


def test_padded_frame_centers_vertically() -> None:
    frame = geometry.make_padded_frame(synthetic_panorama(3000, 800), geometry.SQUARE)
    top_gap = (frame.height - 800) // 2
    mid_x = frame.width // 2
    assert frame.getpixel((mid_x, top_gap - 1)) == (255, 255, 255)
    assert frame.getpixel((mid_x, top_gap + 1)) != (255, 255, 255)


def test_padded_frame_grows_when_ratio_would_clip_the_panorama() -> None:
    # A tall-ish input at 1.91:1: deriving height from width would leave the
    # panorama taller than the canvas, so the canvas is sized from height.
    frame = geometry.make_padded_frame(synthetic_panorama(400, 2000), geometry.LANDSCAPE)
    assert frame.height >= 2000 + 2 * geometry.VERTICAL_PADDING
    assert abs(frame.width / frame.height - geometry.LANDSCAPE.value) < 0.01


def test_section_bounds_split_on_integer_division() -> None:
    assert geometry.section_bounds(3001, 0, 3) == (0, 1000)
    assert geometry.section_bounds(3001, 1, 3) == (1000, 2000)
    assert geometry.section_bounds(3001, 2, 3) == (2000, 3000)


def test_section_bounds_validates_index() -> None:
    with pytest.raises(ValueError):
        geometry.section_bounds(3000, 3, 3)


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
