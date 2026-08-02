"""Behavioural tests for the pure geometry transforms.

Covers the padded whole-panorama frame (exact output size and ratio, the
style's border on whichever axis binds -- width for a wide panorama, height
for a near-square one at a wide target ratio -- centring, and that the
panorama survives uncropped), and section cropping/scaling (bounds,
cover-scale, center-crop offsets on both axes, and exact output size) across
all registered ratios.
"""

from itertools import pairwise

import pytest
from PIL import Image, ImageChops

from maskingframe import geometry
from maskingframe.geometry import DEFAULT_STYLE, FrameStyle, parse_colour
from tests import conftest
from tests.conftest import synthetic_panorama

# LANCZOS resampling blurs a few pixels at the panorama's edge into a
# not-quite-pure-white gradient, so bounding-box measurements against a
# white reference need slack; this tolerance absorbs that blur without
# hiding a real off-by-many-pixels regression.
_BBOX_TOLERANCE = 4


def _picture_bands(frame: Image.Image, border: tuple[int, int, int]) -> list[tuple[int, int]]:
    """The top and bottom of each horizontal run of non-border rows.

    One band per row of picture, so a test can count the rows and measure
    them without knowing how the layout arithmetic works.
    """
    rows = []
    pixels = frame.convert("RGB")
    for y in range(frame.height):
        line = pixels.crop((0, y, frame.width, y + 1)).getcolors(frame.width * 2) or []
        rows.append(any(colour != border for _, colour in line))
    bands = []
    start = None
    for y, filled in enumerate(rows):
        if filled and start is None:
            start = y
        elif not filled and start is not None:
            bands.append((start, y))
            start = None
    if start is not None:
        bands.append((start, frame.height))
    return bands


def _non_white_bbox(frame: Image.Image) -> tuple[int, int, int, int]:
    white = Image.new("RGB", frame.size, DEFAULT_STYLE.border_rgb)
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
    # exactly the style's border in output pixels -- the whole point of the
    # fix. Kills a mutation that pastes at (0, 0) instead of
    # insetting/centering.
    for ratio in geometry.RATIOS.values():
        frame = geometry.make_padded_frame(synthetic_panorama(3000, 800), ratio)
        border = DEFAULT_STYLE.border_px(ratio)
        left, _top, right, _bottom = _non_white_bbox(frame)
        assert abs(left - border) <= _BBOX_TOLERANCE, ratio.name
        assert abs((frame.width - right) - border) <= _BBOX_TOLERANCE, ratio.name


def test_padded_frame_border_matches_the_style() -> None:
    # The border is a percent of the short side, so it differs per ratio;
    # whichever axis binds gets exactly that, and the other gets more.
    style = FrameStyle(border_percent=9.0)
    pano = synthetic_panorama(2400, 1000)
    for ratio in geometry.RATIOS.values():
        frame = geometry.make_padded_frame(pano, ratio, style)
        assert frame.size == (ratio.width, ratio.height)
        left, top, _right, _bottom = _non_white_bbox(frame)
        border = style.border_px(ratio)
        bound_horizontally = abs(left - border) <= _BBOX_TOLERANCE
        bound_vertically = abs(top - border) <= _BBOX_TOLERANCE
        assert bound_horizontally or bound_vertically, ratio.name
        assert left >= border - _BBOX_TOLERANCE, ratio.name
        assert top >= border - _BBOX_TOLERANCE, ratio.name


def test_padded_frame_border_tracks_the_percent() -> None:
    # A wider percent must actually push the panorama further in.
    pano = synthetic_panorama(2400, 1000)
    ratio = geometry.PORTRAIT
    narrow = geometry.make_padded_frame(pano, ratio, FrameStyle(border_percent=2.0))
    wide = geometry.make_padded_frame(pano, ratio, FrameStyle(border_percent=20.0))
    assert _non_white_bbox(narrow)[0] < _non_white_bbox(wide)[0]


def test_padded_frame_uses_the_border_colour() -> None:
    style = FrameStyle(border_percent=10.0, border_colour="#c9302a")
    pano = Image.new("RGB", (2400, 1000), "black")
    frame = geometry.make_padded_frame(pano, geometry.PORTRAIT, style)
    assert frame.getpixel((0, 0)) == (201, 48, 42)
    assert frame.getpixel((frame.width - 1, frame.height - 1)) == (201, 48, 42)


def test_padded_frame_defaults_to_white() -> None:
    pano = Image.new("RGB", (2400, 1000), "black")
    frame = geometry.make_padded_frame(pano, geometry.PORTRAIT)
    assert frame.getpixel((0, 0)) == (255, 255, 255)


def test_zero_border_fills_the_frame_edge_to_edge_on_the_binding_axis() -> None:
    style = FrameStyle(border_percent=0.0)
    pano = Image.new("RGB", (2400, 1000), "black")
    frame = geometry.make_padded_frame(pano, geometry.SQUARE, style)
    # The panorama itself, not the canvas, must reach both edges.
    left, _top, right, _bottom = _non_white_bbox(frame)
    assert left == 0
    assert right == frame.width


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
    # 1200x1000 is nearly square (1.2:1). At 1.91:1 the inset box is far
    # flatter than the panorama, so height binds: the
    # top/bottom margin comes out to exactly the border and the side
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
    border = DEFAULT_STYLE.border_px(geometry.LANDSCAPE)
    assert abs(top_margin - border) <= _BBOX_TOLERANCE
    assert abs(bottom_margin - border) <= _BBOX_TOLERANCE
    assert side_margin > border + _BBOX_TOLERANCE
    assert other_side_margin > border + _BBOX_TOLERANCE


def test_section_bounds_is_a_full_height_crop_at_the_output_aspect() -> None:
    start, end = geometry.section_bounds(2000, 1000, 0.0, geometry.PORTRAIT)
    assert (start, end) == (0, 800)


def test_section_bounds_moves_with_the_position() -> None:
    start, end = geometry.section_bounds(2000, 1000, 0.25, geometry.PORTRAIT)
    assert (start, end) == (500, 1300)


def test_section_bounds_clamps_at_the_right_edge() -> None:
    start, end = geometry.section_bounds(2000, 1000, 1.0, geometry.PORTRAIT)
    assert (start, end) == (1200, 2000)


def test_section_bounds_on_a_narrow_source_takes_the_whole_width() -> None:
    start, end = geometry.section_bounds(1500, 1000, 0.5, geometry.LANDSCAPE)
    assert (start, end) == (0, 1500)


def test_make_section_at_the_output_size() -> None:
    source = conftest.synthetic_panorama(2000, 1000)
    frame = geometry.make_section(source, 0.25, geometry.PORTRAIT)
    assert frame.size == (geometry.PORTRAIT.width, geometry.PORTRAIT.height)


def test_make_section_keeps_the_full_height_of_the_source() -> None:
    # The crop is already the output aspect, so the cover-scale discards
    # nothing: the top-left source pixel is the frame's top-left pixel.
    source = conftest.synthetic_panorama(2000, 1000)
    frame = geometry.make_section(source, 0.0, geometry.PORTRAIT)
    assert frame.getpixel((0, 0)) == source.getpixel((0, 0))


def test_two_positions_give_different_pictures() -> None:
    source = conftest.synthetic_panorama(2000, 1000)
    left = geometry.make_section(source, 0.0, geometry.PORTRAIT)
    right = geometry.make_section(source, 0.6, geometry.PORTRAIT)
    assert left.tobytes() != right.tobytes()


def test_sections_are_exactly_the_target_size() -> None:
    panorama = synthetic_panorama(7205, 2997)
    for ratio in geometry.RATIOS.values():
        count = geometry.section_count(7205, 2997, ratio)
        positions = geometry.default_positions(7205, 2997, ratio, count)
        for index, position in enumerate(positions):
            section = geometry.make_section(panorama, position, ratio)
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
    section = geometry.make_section(panorama, 0.0, geometry.PORTRAIT)
    top_left = section.getpixel((0, 0))
    assert isinstance(top_left, tuple)
    assert top_left[1] != 0, "green channel 0 means source row 0 -- offset was not applied"


def test_section_center_crop_offset_when_the_source_is_narrower_than_the_frame() -> None:
    # A source narrower than SQUARE's frame_width is clamped in
    # section_bounds to the source's own width, giving a crop narrower than
    # the target aspect -- cover-scaling then overflows vertically, exactly
    # like the unclamped case above, but only if make_section re-derives its
    # crop dimensions from the clamped bounds rather than assuming the ratio.
    # (An x-offset is no longer reachable at all: the crop's width can never
    # exceed frame_width, so its aspect can never be wider than the target's,
    # and cover-scaling can only ever overflow vertically.)
    panorama = synthetic_panorama(300, 800)
    section = geometry.make_section(panorama, 0.5, geometry.SQUARE)
    top_left = section.getpixel((0, 0))
    assert isinstance(top_left, tuple)
    assert top_left[1] != 0, "green channel 0 means source row 0 -- offset was not applied"


def test_adjacent_positions_show_different_parts_of_the_panorama() -> None:
    # Kills a mutation that ignores `position` and always crops the same region.
    panorama = synthetic_panorama(3000, 800)
    first = geometry.make_section(panorama, 0.0, geometry.SQUARE)
    second = geometry.make_section(panorama, 0.5, geometry.SQUARE)
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


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("#ffffff", "#ffffff"),
        ("#FFF", "#ffffff"),
        ("ffffff", "#ffffff"),
        ("#C9302A", "#c9302a"),
        ("  #c9302a  ", "#c9302a"),
    ],
)
def test_parse_colour_normalises(given: str, expected: str) -> None:
    assert parse_colour(given) == expected


@pytest.mark.parametrize("given", ["", "#", "#gggggg", "#ffff", "white", "#ffffff00"])
def test_parse_colour_rejects_junk(given: str) -> None:
    with pytest.raises(ValueError, match="colour"):
        parse_colour(given)


def test_frame_style_defaults() -> None:
    assert DEFAULT_STYLE.border_percent == 9.0
    assert DEFAULT_STYLE.gutter_percent == 4.0
    assert DEFAULT_STYLE.border_colour == "#ffffff"
    assert DEFAULT_STYLE.gutter_colour == "#ffffff"
    assert DEFAULT_STYLE.border_detail_frames is False


def test_frame_style_normalises_colours() -> None:
    style = FrameStyle(border_colour="#FFF", gutter_colour="C9302A")
    assert style.border_colour == "#ffffff"
    assert style.gutter_colour == "#c9302a"


@pytest.mark.parametrize("percent", [-0.1, 40.1, float("nan"), float("inf")])
def test_frame_style_rejects_out_of_range_percent(percent: float) -> None:
    with pytest.raises(ValueError, match="percent"):
        FrameStyle(border_percent=percent)
    with pytest.raises(ValueError, match="percent"):
        FrameStyle(gutter_percent=percent)


def test_frame_style_rejects_bad_colour() -> None:
    with pytest.raises(ValueError, match="colour"):
        FrameStyle(border_colour="chartreuse")


def test_percent_resolves_against_the_short_side() -> None:
    style = FrameStyle(border_percent=9.0, gutter_percent=4.0)
    # 4:5 is 1080x1350, short side 1080; 1:1 is 1080x1080; 1.91:1 is 1080x566.
    assert style.border_px(geometry.PORTRAIT) == 97
    assert style.border_px(geometry.SQUARE) == 97
    assert style.border_px(geometry.LANDSCAPE) == 51
    assert style.gutter_px(geometry.PORTRAIT) == 43
    assert style.gutter_px(geometry.LANDSCAPE) == 23


def test_zero_percent_resolves_to_zero_pixels() -> None:
    style = FrameStyle(border_percent=0.0, gutter_percent=0.0)
    assert style.border_px(geometry.PORTRAIT) == 0
    assert style.gutter_px(geometry.PORTRAIT) == 0


def test_rgb_is_a_three_tuple() -> None:
    assert FrameStyle(border_colour="#c9302a").border_rgb == (201, 48, 42)
    assert FrameStyle(gutter_colour="#000000").gutter_rgb == (0, 0, 0)


def test_section_is_full_bleed_by_default() -> None:
    pano = Image.new("RGB", (3000, 1000), "black")
    frame = geometry.make_section(pano, 0.0, geometry.PORTRAIT)
    assert frame.size == (geometry.PORTRAIT.width, geometry.PORTRAIT.height)
    assert frame.getpixel((0, 0)) == (0, 0, 0)


def test_section_gets_a_border_when_the_style_asks_for_one() -> None:
    style = geometry.FrameStyle(
        border_percent=10.0, border_colour="#c9302a", border_detail_frames=True
    )
    pano = Image.new("RGB", (3000, 1000), "black")
    ratio = geometry.PORTRAIT
    frame = geometry.make_section(pano, 0.0, ratio, style)
    border = style.border_px(ratio)

    assert frame.size == (ratio.width, ratio.height)
    assert frame.getpixel((0, 0)) == (201, 48, 42)
    assert frame.getpixel((border - 1, ratio.height // 2)) == (201, 48, 42)
    assert frame.getpixel((border + 1, ratio.height // 2)) == (0, 0, 0)
    assert frame.getpixel((ratio.width - border, ratio.height // 2)) == (201, 48, 42)


def test_bordered_section_with_a_zero_border_is_full_bleed() -> None:
    style = geometry.FrameStyle(border_percent=0.0, border_detail_frames=True)
    pano = Image.new("RGB", (3000, 1000), "black")
    frame = geometry.make_section(pano, 0.0, geometry.PORTRAIT, style)
    assert frame.getpixel((0, 0)) == (0, 0, 0)


def test_frame_width_is_the_output_aspect_at_full_source_height() -> None:
    # 1000px tall at 1.91:1 -> 1000 * (1080/566) = 1908.1 -> 1908
    assert geometry.frame_width(1000, geometry.LANDSCAPE) == 1908
    # 1000px tall at 1:1 is exactly 1000
    assert geometry.frame_width(1000, geometry.SQUARE) == 1000
    # 1000px tall at 4:5 -> 1000 * (1080/1350) = 800
    assert geometry.frame_width(1000, geometry.PORTRAIT) == 800


def test_frame_width_never_collapses_to_zero() -> None:
    assert geometry.frame_width(1, geometry.PORTRAIT) == 1


def test_travel_is_what_is_left_after_one_frame() -> None:
    # 800-wide frame in a 2000-wide panorama leaves 1200 of travel.
    assert geometry.position_travel(2000, 1000, geometry.PORTRAIT) == pytest.approx(0.6)


def test_travel_collapses_when_the_source_is_narrower_than_one_frame() -> None:
    # 1500x1000 at 1.91:1 wants a 1908-wide frame: wider than the source.
    assert geometry.position_travel(1500, 1000, geometry.LANDSCAPE) == 0.0


def test_clamp_holds_a_position_inside_the_travel() -> None:
    assert geometry.clamp_position(-0.5, 2000, 1000, geometry.PORTRAIT) == 0.0
    assert geometry.clamp_position(0.9, 2000, 1000, geometry.PORTRAIT) == pytest.approx(0.6)
    assert geometry.clamp_position(0.25, 2000, 1000, geometry.PORTRAIT) == pytest.approx(0.25)


def test_clamp_on_a_narrow_source_pins_every_position_to_zero() -> None:
    assert geometry.clamp_position(0.4, 1500, 1000, geometry.LANDSCAPE) == 0.0


def test_normalise_keeps_positions_ascending_without_reordering_them() -> None:
    # Frame 2 has been dragged past frame 3; it stops at frame 3 rather than
    # swapping with it, so the carousel never runs backwards.
    got = geometry.normalise_positions([0.1, 0.5, 0.3], 2000, 1000, geometry.PORTRAIT)
    assert got == pytest.approx((0.1, 0.5, 0.5))


def test_normalise_allows_overlap() -> None:
    # Two tight crops on the same subject is a legitimate choice.
    got = geometry.normalise_positions([0.20, 0.22], 2000, 1000, geometry.PORTRAIT)
    assert got == pytest.approx((0.20, 0.22))


def test_moving_a_frame_stops_at_its_neighbour_instead_of_pushing_it() -> None:
    # The whole point of the shared rule: frame 2 dragged to the far right
    # stops where frame 3 stands, and frames 3 and 4 stay where they were.
    got = geometry.move_position((0.0, 0.2, 0.4, 0.6), 1, 5.0, 3000, 1000, geometry.PORTRAIT)
    assert got == pytest.approx((0.0, 0.4, 0.4, 0.6))


def test_moving_a_frame_stops_at_the_neighbour_below_it() -> None:
    got = geometry.move_position((0.2, 0.5), 1, -1.0, 3000, 1000, geometry.PORTRAIT)
    assert got == pytest.approx((0.2, 0.2))


def test_moving_the_last_frame_stops_at_the_right_edge() -> None:
    travel = geometry.position_travel(3000, 1000, geometry.PORTRAIT)
    got = geometry.move_position((0.0, 0.2), 1, 5.0, 3000, 1000, geometry.PORTRAIT)
    assert got == pytest.approx((0.0, travel))


def test_moving_a_frame_that_is_not_there_changes_nothing() -> None:
    # Reachable from a drag whose plan has since shrunk; it must not raise.
    assert geometry.move_position((0.0, 0.2), 7, 0.5, 3000, 1000, geometry.PORTRAIT) == (0.0, 0.2)


def test_default_positions_span_the_whole_panorama() -> None:
    got = geometry.default_positions(2000, 1000, geometry.PORTRAIT, count=3)
    assert got[0] == 0.0
    assert got[-1] == pytest.approx(geometry.position_travel(2000, 1000, geometry.PORTRAIT))
    assert got == pytest.approx((0.0, 0.3, 0.6))


def test_default_positions_use_the_derived_count_when_none_is_given() -> None:
    count = geometry.section_count(2000, 1000, geometry.PORTRAIT)
    assert len(geometry.default_positions(2000, 1000, geometry.PORTRAIT)) == count


def test_default_positions_never_divide_by_zero_at_one_frame() -> None:
    assert geometry.default_positions(2000, 1000, geometry.PORTRAIT, count=1) == (0.0,)


def test_default_positions_on_a_narrow_source_are_all_zero() -> None:
    got = geometry.default_positions(1500, 1000, geometry.LANDSCAPE, count=2)
    assert got == (0.0, 0.0)


def test_insert_lands_in_the_widest_uncovered_stretch() -> None:
    # 2000x1000 at 4:5 -> an 800px frame, 0.4 of the width. Frames at 0.0
    # and 0.6 cover 0.0-0.4 and 0.6-1.0, leaving 0.4-0.6 uncovered. The new
    # frame is centred there: midpoint 0.5, minus half a frame = 0.3.
    got = geometry.insert_position((0.0, 0.6), 2000, 1000, geometry.PORTRAIT)
    assert got == pytest.approx((0.0, 0.3, 0.6))


def test_insert_keeps_the_tuple_ascending() -> None:
    got = geometry.insert_position((0.0, 0.6), 2000, 1000, geometry.PORTRAIT)
    assert list(got) == sorted(got)


def test_insert_falls_back_to_the_widest_gap_when_everything_is_covered() -> None:
    # Frames at 0.0, 0.3 and 0.6 cover the whole width with no hole in it,
    # so the new frame goes midway between the two furthest-apart edges.
    got = geometry.insert_position((0.0, 0.3, 0.6), 2000, 1000, geometry.PORTRAIT)
    assert len(got) == 4
    assert list(got) == sorted(got)
    assert 0.0 < got[1] < 0.6


def test_insert_on_a_narrow_source_adds_another_zero() -> None:
    got = geometry.insert_position((0.0, 0.0), 1500, 1000, geometry.LANDSCAPE)
    assert got == (0.0, 0.0, 0.0)


def test_drop_takes_the_last_frame() -> None:
    assert geometry.drop_position((0.0, 0.3, 0.6)) == pytest.approx((0.0, 0.3))


def test_drop_refuses_to_go_below_the_minimum() -> None:
    with pytest.raises(ValueError, match="two"):
        geometry.drop_position((0.0, 0.6))


def test_default_positions_are_recognised_as_even() -> None:
    positions = geometry.default_positions(3000, 1000, geometry.PORTRAIT)
    assert geometry.positions_are_even(positions, 3000, 1000, geometry.PORTRAIT)


def test_a_moved_frame_makes_the_positions_uneven() -> None:
    positions = geometry.default_positions(3000, 1000, geometry.PORTRAIT)
    moved = geometry.move_position(positions, 1, positions[1] + 0.05, 3000, 1000, geometry.PORTRAIT)

    assert moved != positions
    assert not geometry.positions_are_even(moved, 3000, 1000, geometry.PORTRAIT)


def test_evenness_is_judged_at_the_current_count() -> None:
    """Reset spaces out the frames you have; it does not put back the count
    the opening guess would have chosen. So a plan with a frame added is
    even again once those frames are evenly spread."""
    four = geometry.default_positions(3000, 1000, geometry.PORTRAIT, count=4)
    seven = geometry.default_positions(3000, 1000, geometry.PORTRAIT, count=7)

    assert geometry.positions_are_even(four, 3000, 1000, geometry.PORTRAIT)
    assert geometry.positions_are_even(seven, 3000, 1000, geometry.PORTRAIT)
    assert len(four) != len(seven)


def test_a_source_with_no_travel_is_always_even() -> None:
    """Every position clamps to zero when the source is narrower than one
    output tile, so there is nothing to space out and nothing to offer."""
    positions = geometry.default_positions(1000, 800, geometry.LANDSCAPE, count=3)

    assert positions == (0.0, 0.0, 0.0)
    assert geometry.positions_are_even(positions, 1000, 800, geometry.LANDSCAPE)


def test_no_positions_count_as_even() -> None:
    assert geometry.positions_are_even((), 3000, 1000, geometry.PORTRAIT)


def test_frame_one_border_follows_the_shared_one_by_default() -> None:
    style = geometry.FrameStyle(border_percent=12.0)

    assert style.padded_border_percent is None
    for ratio in geometry.RATIOS.values():
        assert style.padded_border_px(ratio) == style.border_px(ratio)


def test_frame_one_border_resolves_on_its_own_when_set() -> None:
    style = geometry.FrameStyle(border_percent=12.0, padded_border_percent=2.0)

    for ratio in geometry.RATIOS.values():
        assert style.padded_border_px(ratio) != style.border_px(ratio)
        assert style.padded_border_px(ratio) == geometry.FrameStyle(border_percent=2.0).border_px(
            ratio
        )


def test_setting_frame_one_to_the_shared_width_changes_nothing() -> None:
    """The None case and the equal case must be the same picture, or the
    checkbox in the rail would move the frame the moment it was ticked."""
    source = synthetic_panorama(2330, 1000)
    following = geometry.make_padded_frame(source, geometry.PORTRAIT, geometry.FrameStyle())
    spelled = geometry.make_padded_frame(
        source, geometry.PORTRAIT, geometry.FrameStyle(padded_border_percent=9.0)
    )

    assert following.tobytes() == spelled.tobytes()


def test_frame_one_border_leaves_the_detail_frames_alone() -> None:
    """The whole point: turning frame 1's border down must not touch what
    the border means anywhere else."""
    source = synthetic_panorama(2330, 1000)
    shared = geometry.FrameStyle(border_detail_frames=True)
    narrowed = geometry.FrameStyle(border_detail_frames=True, padded_border_percent=0.0)

    assert geometry.make_section(source, 0.0, geometry.PORTRAIT, shared).tobytes() == (
        geometry.make_section(source, 0.0, geometry.PORTRAIT, narrowed).tobytes()
    )
    assert geometry.make_padded_frame(source, geometry.PORTRAIT, shared).tobytes() != (
        geometry.make_padded_frame(source, geometry.PORTRAIT, narrowed).tobytes()
    )


def test_the_measured_ceiling_at_portrait() -> None:
    """The claim the whole feature rests on: at 4:5, a 2.33:1 panorama fills
    34.3% of frame 1 with no border at all, and no setting goes further,
    because the shape mismatch is what leaves the space. If this moves, the
    spec's table is wrong and so is the reason for the feature."""
    ratio = geometry.PORTRAIT
    style = geometry.FrameStyle(padded_border_percent=0.0)
    pano = 2.33

    inset = ratio.width - 2 * style.padded_border_px(ratio)
    assert inset == ratio.width
    covered = inset * (inset / pano)
    assert covered / (ratio.width * ratio.height) == pytest.approx(0.343, abs=0.001)


def test_a_frame_one_border_out_of_range_is_refused() -> None:
    with pytest.raises(ValueError):
        geometry.FrameStyle(padded_border_percent=-1.0)
    with pytest.raises(ValueError):
        geometry.FrameStyle(padded_border_percent=geometry.MAX_PERCENT + 1)


# --- frame 1 as stacked rows -------------------------------------------------


def test_the_strips_tile_the_panorama_exactly() -> None:
    """Nothing lost to rounding and nothing shown twice: the cuts have to
    meet, start at 0 and finish on the last column."""
    for width in (2330, 2331, 999, 1000):
        for rows in range(1, geometry.MAX_ROWS + 1):
            cuts = geometry.row_bounds(width, rows)
            assert len(cuts) == rows
            assert cuts[0][0] == 0
            assert cuts[-1][1] == width
            for (_, end), (start, _) in pairwise(cuts):
                assert start == end
            assert all(end > start for start, end in cuts)


def test_one_row_is_the_whole_panorama() -> None:
    assert geometry.row_bounds(2330, 1) == ((0, 2330),)


def test_rows_of_one_are_byte_identical_to_the_field_being_absent() -> None:
    source = synthetic_panorama(2330, 1000)
    for ratio in geometry.RATIOS.values():
        plain = geometry.make_padded_frame(source, ratio, geometry.FrameStyle())
        spelled = geometry.make_padded_frame(source, ratio, geometry.FrameStyle(padded_rows=1))
        assert plain.tobytes() == spelled.tobytes(), ratio.name


def test_rows_are_all_the_same_size_and_shape() -> None:
    source = synthetic_panorama(2330, 1000)
    style = geometry.FrameStyle(padded_rows=3)
    frame = geometry.make_padded_frame(source, geometry.PORTRAIT, style)

    # Each row is a band of non-border pixels; there must be three of equal
    # height, separated by the gap.
    bands = _picture_bands(frame, style.border_rgb)
    assert len(bands) == 3
    heights = {bottom - top for top, bottom in bands}
    assert len(heights) == 1


def test_a_row_keeps_the_aspect_of_the_strip_it_holds() -> None:
    source = synthetic_panorama(2400, 1000)
    for rows in (2, 3, 4):
        style = geometry.FrameStyle(padded_rows=rows)
        frame = geometry.make_padded_frame(source, geometry.PORTRAIT, style)
        left, _top, right, _bottom = _non_white_bbox(frame)
        bands = _picture_bands(frame, style.border_rgb)
        band_height = bands[0][1] - bands[0][0]
        wanted = (2400 / rows) / 1000
        assert (right - left) / band_height == pytest.approx(wanted, rel=0.02), rows


def test_rows_never_leave_the_inset_box() -> None:
    source = synthetic_panorama(2330, 1000)
    for ratio in geometry.RATIOS.values():
        for rows in range(1, geometry.MAX_ROWS + 1):
            style = geometry.FrameStyle(padded_rows=rows)
            border = style.padded_border_px(ratio)
            left, top, right, bottom = _non_white_bbox(
                geometry.make_padded_frame(source, ratio, style)
            )
            assert left >= border - 1, (ratio.name, rows)
            assert top >= border - 1, (ratio.name, rows)
            assert right <= ratio.width - border + 1, (ratio.name, rows)
            assert bottom <= ratio.height - border + 1, (ratio.name, rows)


def test_frame_ones_own_border_still_governs_the_rows() -> None:
    source = synthetic_panorama(2330, 1000)
    wide = geometry.make_padded_frame(
        source, geometry.PORTRAIT, geometry.FrameStyle(padded_rows=2, padded_border_percent=20.0)
    )
    narrow = geometry.make_padded_frame(
        source, geometry.PORTRAIT, geometry.FrameStyle(padded_rows=2, padded_border_percent=1.0)
    )

    assert _non_white_bbox(narrow)[0] < _non_white_bbox(wide)[0]


@pytest.mark.parametrize("rows", [0, -1, geometry.MAX_ROWS + 1])
def test_a_row_count_out_of_range_is_refused(rows: int) -> None:
    with pytest.raises(ValueError):
        geometry.FrameStyle(padded_rows=rows)


@pytest.mark.parametrize(
    ("pano", "ratio_name", "expected"),
    [
        (2.33, "4:5", (0.231, 0.495, 0.203, 0.105)),
        (2.33, "1:1", (0.289, 0.355, 0.142, 0.072)),
        (2.33, "1.91:1", (0.672, 0.185, 0.074, 0.037)),
        (3.0, "4:5", (0.179, 0.637, 0.262, 0.136)),
        (6.0, "4:5", (0.090, 0.359, 0.524, 0.271)),
        (6.0, "1.91:1", (0.261, 0.477, 0.191, 0.096)),
    ],
)
def test_the_spec_table_is_what_the_arithmetic_says(
    pano: float, ratio_name: str, expected: tuple[float, ...]
) -> None:
    """The design's own justification. If these move, the reason for the
    feature has moved with them and the spec is wrong."""
    ratio = geometry.RATIOS[ratio_name]
    height = 1000
    width = round(pano * height)
    got = tuple(
        geometry.padded_rows_fill(width, height, ratio, geometry.FrameStyle(), rows)
        for rows in range(1, 5)
    )
    assert got == pytest.approx(expected, abs=0.002)


def test_the_advertised_fill_is_the_one_that_renders() -> None:
    """The number in the rail is what a user acts on, so it is checked
    against the actual picture rather than against a second copy of the
    formula that produced it."""
    source = synthetic_panorama(2330, 1000)
    for ratio in geometry.RATIOS.values():
        for rows in range(1, geometry.MAX_ROWS + 1):
            style = geometry.FrameStyle(padded_rows=rows)
            frame = geometry.make_padded_frame(source, ratio, style)
            covered = sum(bottom - top for top, bottom in _picture_bands(frame, style.border_rgb))
            left, _, right, _ = _non_white_bbox(frame)
            drawn = covered * (right - left) / (ratio.width * ratio.height)

            promised = geometry.padded_rows_fill(2330, 1000, ratio, style, rows)

            assert drawn == pytest.approx(promised, abs=0.01), (ratio.name, rows)
