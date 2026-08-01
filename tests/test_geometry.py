"""Behavioural tests for the pure geometry transforms.

Covers the padded whole-panorama frame (exact output size and ratio, exact
SIDE_PADDING on whichever axis binds -- width for a wide panorama, height
for a near-square one at a wide target ratio -- centring, and that the
panorama survives uncropped), and section cropping/scaling (bounds,
cover-scale, center-crop offsets on both axes, and exact output size) across
all registered ratios.
"""

import pytest
from PIL import Image, ImageChops

from maskingframe import geometry
from tests.conftest import synthetic_panorama

# LANCZOS resampling blurs a few pixels at the panorama's edge into a
# not-quite-pure-white gradient, so bounding-box measurements against a
# white reference need slack; this tolerance absorbs that blur without
# hiding a real off-by-many-pixels regression.
_BBOX_TOLERANCE = 4


def _non_white_bbox(frame: Image.Image) -> tuple[int, int, int, int]:
    white = Image.new("RGB", frame.size, geometry.BACKGROUND)
    diff = ImageChops.difference(frame, white)
    bbox = diff.getbbox()
    assert bbox is not None, "frame is entirely white"
    return bbox


def test_padded_frame_is_exactly_the_target_ratio() -> None:
    for ratio in geometry.RATIOS.values():
        frame = geometry.make_padded_frame(synthetic_panorama(3000, 800), ratio)
        assert abs(frame.width / frame.height - ratio.value) < 0.01, ratio.name


def test_padded_frame_is_exactly_the_target_size() -> None:
    # Frame 1 must match the detail frames' pixel size exactly, not just
    # their ratio -- otherwise a large-format scan produces a whole-panorama
    # frame at full source resolution beside sub-megabyte detail frames.
    for ratio in geometry.RATIOS.values():
        frame = geometry.make_padded_frame(synthetic_panorama(3000, 800), ratio)
        assert frame.size == (ratio.width, ratio.height), ratio.name


def test_padded_frame_keeps_exact_side_padding_for_a_wide_panorama() -> None:
    # A wide panorama binds on width, so the left/right margin must be
    # exactly SIDE_PADDING output pixels -- the whole point of the fix.
    # Kills a mutation that pastes at (0, 0) instead of insetting/centering.
    for ratio in geometry.RATIOS.values():
        frame = geometry.make_padded_frame(synthetic_panorama(3000, 800), ratio)
        left, _top, right, _bottom = _non_white_bbox(frame)
        assert abs(left - geometry.SIDE_PADDING) <= _BBOX_TOLERANCE, ratio.name
        assert abs((frame.width - right) - geometry.SIDE_PADDING) <= _BBOX_TOLERANCE, ratio.name


def test_padded_frame_centers_the_panorama() -> None:
    # Kills a mutation that skips centring (e.g. pastes at a fixed corner):
    # left gap must equal right gap and top gap must equal bottom gap.
    #
    # Two panoramas: 3000x800 binds on width at every ratio; 1200x1000 is
    # nearly square (1.2:1) so at 1.91:1 -- whose inset box is 2.4:1 -- it
    # binds on HEIGHT instead. Without the second case a mutation that drops
    # the height term from the fit-scale calculation still passes here, since
    # a width-binding case can't exercise the height branch at all.
    for pano_width, pano_height in ((3000, 800), (1200, 1000)):
        for ratio in geometry.RATIOS.values():
            frame = geometry.make_padded_frame(synthetic_panorama(pano_width, pano_height), ratio)
            left, top, right, bottom = _non_white_bbox(frame)
            right_gap = frame.width - right
            bottom_gap = frame.height - bottom
            assert abs(left - right_gap) <= _BBOX_TOLERANCE, (pano_width, pano_height, ratio.name)
            assert abs(top - bottom_gap) <= _BBOX_TOLERANCE, (pano_width, pano_height, ratio.name)


def test_padded_frame_preserves_the_whole_panorama_uncropped() -> None:
    # The panorama must be fitted, never cropped: its aspect ratio in the
    # output frame must match the source aspect ratio.
    #
    # Same two panoramas as the centring test, and for the same reason: a
    # near-square source is needed to exercise the height-binding branch at
    # 1.91:1, which a purely wide source never reaches.
    for pano_width, pano_height in ((3000, 800), (1200, 1000)):
        source_ratio = pano_width / pano_height
        for ratio in geometry.RATIOS.values():
            frame = geometry.make_padded_frame(synthetic_panorama(pano_width, pano_height), ratio)
            left, top, right, bottom = _non_white_bbox(frame)
            out_width = right - left
            out_height = bottom - top
            assert abs(out_width / out_height - source_ratio) < 0.02, (
                pano_width,
                pano_height,
                ratio.name,
            )


def test_padded_frame_keeps_exact_top_padding_when_height_binds() -> None:
    # 1200x1000 is nearly square (1.2:1). At 1.91:1 the inset box is
    # 880x366 (2.4:1), flatter than the panorama, so height binds: the
    # top/bottom margin comes out to exactly SIDE_PADDING and the side
    # margins are larger. This is the mirror image of the width-binding
    # case exercised elsewhere in this file, and it's the only case in the
    # suite that would catch a fit-scale calculation that silently drops
    # the height term (e.g. `scale = box_width / pano_width`) -- do not
    # "simplify" this back to a width-binding input.
    pano_width, pano_height = 1200, 1000
    panorama = synthetic_panorama(pano_width, pano_height)
    frame = geometry.make_padded_frame(panorama, geometry.LANDSCAPE)
    left, top, right, bottom = _non_white_bbox(frame)
    side_margin = left
    other_side_margin = frame.width - right
    top_margin = top
    bottom_margin = frame.height - bottom
    assert abs(top_margin - geometry.SIDE_PADDING) <= _BBOX_TOLERANCE
    assert abs(bottom_margin - geometry.SIDE_PADDING) <= _BBOX_TOLERANCE
    assert side_margin > geometry.SIDE_PADDING + _BBOX_TOLERANCE
    assert other_side_margin > geometry.SIDE_PADDING + _BBOX_TOLERANCE


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


def test_ratio_labels_and_display() -> None:
    assert geometry.PORTRAIT.label == "Portrait"
    assert geometry.SQUARE.label == "Square"
    assert geometry.LANDSCAPE.label == "Landscape"
    assert geometry.PORTRAIT.display == "Portrait (4:5)"
    assert geometry.SQUARE.display == "Square (1:1)"
    assert geometry.LANDSCAPE.display == "Landscape (1.91:1)"


def test_ratios_are_ordered_narrowest_to_widest_not_alphabetical() -> None:
    # Alphabetically "1.91:1" sorts first; presentation order must instead be
    # Portrait, Square, Landscape, matching increasing width/height value.
    assert list(geometry.RATIOS) == ["4:5", "1:1", "1.91:1"]
    values = [r.value for r in geometry.RATIOS.values()]
    assert values == sorted(values)


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
