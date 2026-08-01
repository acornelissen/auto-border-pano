"""Tests for the pure layout solver.

Everything here is arithmetic on aspect ratios -- no images are opened, so
these run in milliseconds and can cover shapes that would be tedious to
build as real files.
"""

import pytest

from maskingframe import geometry, layout
from maskingframe.geometry import DEFAULT_STYLE, FrameStyle

STYLE = FrameStyle(border_percent=9.0, gutter_percent=4.0)


def _touching_or_overlapping(a: layout.Box, b: layout.Box) -> bool:
    return not (
        a.x + a.width < b.x or b.x + b.width < a.x or a.y + a.height < b.y or b.y + b.height < a.y
    )


def _box_aspect(box: layout.Box) -> float:
    return box.width / box.height


def test_two_equal_panoramas_stack_at_portrait() -> None:
    # Two 2.33:1 panoramas in a 1080x1350 frame: a column wins easily,
    # because a row would make each panel about 0.9:1.
    solved = layout.solve([2.33, 2.33], geometry.PORTRAIT, STYLE)
    assert solved.name == "column"
    assert len(solved.boxes) == 2


def test_three_panoramas_stack_at_portrait() -> None:
    solved = layout.solve([2.33, 2.33, 2.33], geometry.PORTRAIT, STYLE)
    assert solved.name == "column"
    assert len(solved.boxes) == 3


def test_panels_keep_their_source_aspect_ratio() -> None:
    # The no-cropping guarantee, stated as an assertion. Every box must
    # match the aspect of the image it will hold.
    aspects = [3.0, 1.0, 0.67]
    for ratio in geometry.RATIOS.values():
        solved = layout.solve(aspects, ratio, STYLE)
        for aspect, box in zip(aspects, solved.boxes, strict=True):
            assert abs(_box_aspect(box) - aspect) < 0.02, (ratio.name, aspect, box)


def test_boxes_never_overlap() -> None:
    aspects = [3.0, 1.0, 0.67]
    for ratio in geometry.RATIOS.values():
        boxes = layout.solve(aspects, ratio, STYLE).boxes
        for i, a in enumerate(boxes):
            for b in boxes[i + 1 :]:
                overlap_x = min(a.x + a.width, b.x + b.width) - max(a.x, b.x)
                overlap_y = min(a.y + a.height, b.y + b.height) - max(a.y, b.y)
                assert overlap_x <= 0 or overlap_y <= 0, (ratio.name, a, b)


def test_boxes_stay_inside_the_padded_frame() -> None:
    aspects = [3.0, 1.0, 0.67]
    for ratio in geometry.RATIOS.values():
        padding = STYLE.border_px(ratio)
        for box in layout.solve(aspects, ratio, STYLE).boxes:
            assert box.x >= padding - 1, (ratio.name, box)
            assert box.y >= padding - 1, (ratio.name, box)
            assert box.x + box.width <= ratio.width - padding + 1, (ratio.name, box)
            assert box.y + box.height <= ratio.height - padding + 1, (ratio.name, box)


def test_block_is_centred_in_the_frame() -> None:
    aspects = [2.33, 2.33, 2.33]
    boxes = layout.solve(aspects, geometry.PORTRAIT, STYLE).boxes
    left = min(b.x for b in boxes)
    right = geometry.PORTRAIT.width - max(b.x + b.width for b in boxes)
    top = min(b.y for b in boxes)
    bottom = geometry.PORTRAIT.height - max(b.y + b.height for b in boxes)
    assert abs(left - right) <= 1, (left, right)
    assert abs(top - bottom) <= 1, (top, bottom)


def test_order_is_never_permuted() -> None:
    # Box 0 must hold image 0. With a column layout that means boxes are
    # top to bottom; with a row, left to right.
    solved = layout.solve([3.0, 0.5], geometry.SQUARE, STYLE)
    assert abs(_box_aspect(solved.boxes[0]) - 3.0) < 0.02
    assert abs(_box_aspect(solved.boxes[1]) - 0.5) < 0.02


def test_extreme_aspects_still_produce_valid_boxes() -> None:
    # A box that's only 1-2px on its short axis has an unavoidable rounding
    # error (half-up rounding can move a dimension by up to 0.5px, which is
    # a large fraction of a 1px box). What must never happen is the old
    # clamp bug: a box forced up from below 1px, silently landing far from
    # its source aspect no matter how big the box is. So each surviving box
    # must match its source aspect within a tolerance derived from that
    # rounding bound; a candidate that cannot place every leaf at >=1px
    # should be rejected, and if every candidate is rejected `solve` must
    # raise rather than return a distorted layout.
    for aspects in (
        [20.0, 20.0],
        [0.05, 0.05],
        [20.0, 0.05, 1.0],
        # This one is not tame: at LANDSCAPE with 100px padding, the 100:1
        # panel's ideal box genuinely rounds under 1px in several
        # candidates. It is the exact case that demonstrated the original
        # max(1, ...) clamp bug (a 100:1 image squashed into a 3:1 box) and
        # is what actually exercises the rejection path in _place/evaluate.
        [0.01, 100.0, 1.0],
    ):
        for ratio in geometry.RATIOS.values():
            try:
                solved = layout.solve(aspects, ratio, STYLE)
            except ValueError:
                continue
            for aspect, box in zip(aspects, solved.boxes, strict=True):
                assert box.width >= 1, (aspects, ratio.name, box)
                assert box.height >= 1, (aspects, ratio.name, box)
                # Twice the theoretical 0.5px-per-dimension rounding bound,
                # as a safety margin -- not an arbitrary loosening.
                tolerance = (1.0 / box.width + 1.0 / box.height) * aspect
                assert abs(_box_aspect(box) - aspect) <= tolerance, (
                    aspects,
                    ratio.name,
                    aspect,
                    box,
                )


def test_no_usable_layout_raises() -> None:
    # Two extremely thin panels at a wide landscape frame: every candidate
    # (row and column) would need a leaf dimension under 0.5px, so every
    # candidate is rejected and evaluate() returns None for each. solve()
    # must surface that as a ValueError rather than degrading a box.
    with pytest.raises(ValueError):
        layout.solve([0.001, 0.001], geometry.LANDSCAPE, STYLE)

    for name, node in layout.candidates(2):
        thin = [0.001, 0.001]
        other = layout.evaluate(node, name, thin, geometry.LANDSCAPE, STYLE)
        assert other is None


def test_default_gutter_is_four_percent() -> None:
    assert DEFAULT_STYLE.gutter_percent == 4.0


def test_nested_candidates_preserve_order() -> None:
    # Only the two-image winner is exercised by test_order_is_never_permuted.
    # The three-image nested shapes (a panel beside a stacked pair) have
    # their own leaf-to-index wiring, so check each one directly rather
    # than trusting that the simple row/column cases generalise.
    aspects = [3.0, 0.2, 1.5]
    for name, node in layout.candidates(3):
        solved = layout.evaluate(node, name, aspects, geometry.PORTRAIT, STYLE)
        assert solved is not None, name
        for index, (aspect, box) in enumerate(zip(aspects, solved.boxes, strict=True)):
            # The tolerance follows the box's own size rather than being a
            # flat 0.02: the 0.2:1 panel squeezes its neighbours down to a
            # few tens of pixels in the nested candidates, where half-up
            # rounding of each dimension is worth several percent on its own.
            tolerance = (1.0 / box.width + 1.0 / box.height) * aspect
            assert abs(_box_aspect(box) - aspect) <= tolerance, (name, index, aspect, box)


def test_score_is_a_fraction_of_the_available_box() -> None:
    solved = layout.solve([2.33, 2.33], geometry.PORTRAIT, STYLE)
    assert 0.0 < solved.score <= 1.0
    # Pinned regression value: two equal 2.33:1 panels stacked in a column
    # inside a 1080x1350 frame with the default 9% border (97px at 4:5) and
    # a 43px gutter (4% of the short side). If this drifts, the scoring formula (or the coefficient
    # maths feeding it) changed -- not just the "somewhere between 0 and 1"
    # shape of it.
    assert solved.score == pytest.approx(0.657439446366782)


def test_winning_candidate_fills_at_least_as_much_as_the_alternatives() -> None:
    # Whatever the solver picked must score at least as well as every other
    # candidate it considered.
    aspects = [3.0, 1.0, 0.67]
    for ratio in geometry.RATIOS.values():
        solved = layout.solve(aspects, ratio, STYLE)
        for name, candidate in layout.candidates(len(aspects)):
            other = layout.evaluate(candidate, name, aspects, ratio, STYLE)
            if other is not None:
                assert solved.score >= other.score - 1e-9, (ratio.name, name)


def test_only_two_or_three_images_are_supported() -> None:
    with pytest.raises(ValueError):
        layout.solve([1.0], geometry.SQUARE, STYLE)
    with pytest.raises(ValueError):
        layout.solve([1.0, 1.0, 1.0, 1.0], geometry.SQUARE, STYLE)


def test_two_panels_get_one_gutter() -> None:
    solved = layout.solve([1.5, 1.5], geometry.PORTRAIT, STYLE)
    assert len(solved.gutters) == 1


def test_three_panels_get_two_gutters() -> None:
    solved = layout.solve([1.5, 1.5, 1.5], geometry.PORTRAIT, STYLE)
    assert len(solved.gutters) == 2


def test_a_zero_gutter_produces_no_rectangles() -> None:
    style = FrameStyle(border_percent=9.0, gutter_percent=0.0)
    solved = layout.solve([1.5, 1.5], geometry.PORTRAIT, style)
    assert solved.gutters == ()


def test_each_gutter_separates_two_panels() -> None:
    solved = layout.solve([1.5, 1.5], geometry.PORTRAIT, STYLE)
    gutter = solved.gutters[0]
    assert gutter.width > 0 and gutter.height > 0
    # It sits between the panels: touching both, and no panel contains it.
    assert all(_touching_or_overlapping(gutter, box) for box in solved.boxes)


def test_a_column_gutter_leaves_no_gap_on_either_side() -> None:
    # The whole point of the rectangle: every pixel between two adjacent
    # panels is covered by it, with nothing left uncoloured on either side.
    node = layout.Column((layout.Leaf(0), layout.Leaf(1), layout.Leaf(2)))
    solved = layout.evaluate(node, "column", [2.33, 2.33, 2.33], geometry.PORTRAIT, STYLE)
    assert solved is not None
    pairs = list(zip(solved.boxes, solved.boxes[1:], strict=False))
    for gutter, (above, below) in zip(solved.gutters, pairs, strict=True):
        assert gutter.y <= above.y + above.height
        assert gutter.y + gutter.height >= below.y
        assert gutter.x <= above.x
        assert gutter.x + gutter.width >= above.x + above.width


def test_a_row_gutter_leaves_no_gap_on_either_side() -> None:
    node = layout.Row((layout.Leaf(0), layout.Leaf(1), layout.Leaf(2)))
    solved = layout.evaluate(node, "row", [0.5, 0.5, 0.5], geometry.LANDSCAPE, STYLE)
    assert solved is not None
    pairs = list(zip(solved.boxes, solved.boxes[1:], strict=False))
    for gutter, (before, after) in zip(solved.gutters, pairs, strict=True):
        assert gutter.x <= before.x + before.width
        assert gutter.x + gutter.width >= after.x
        assert gutter.y <= before.y
        assert gutter.y + gutter.height >= before.y + before.height


def test_gutters_stay_inside_the_border() -> None:
    ratio = geometry.PORTRAIT
    solved = layout.solve([1.5, 1.5, 1.5], ratio, STYLE)
    border = STYLE.border_px(ratio)
    # One pixel of slack: the gutter is deliberately inflated along its own
    # axis so no hairline of the wrong colour can show between two panels.
    for gutter in solved.gutters:
        assert gutter.x >= border - 1
        assert gutter.y >= border - 1
        assert gutter.x + gutter.width <= ratio.width - border + 1
        assert gutter.y + gutter.height <= ratio.height - border + 1


def test_gutter_width_tracks_the_style() -> None:
    ratio = geometry.PORTRAIT
    wide = layout.solve([1.5, 1.5], ratio, FrameStyle(gutter_percent=10.0))
    narrow = layout.solve([1.5, 1.5], ratio, FrameStyle(gutter_percent=1.0))
    assert wide.gutters[0].width > narrow.gutters[0].width or (
        wide.gutters[0].height > narrow.gutters[0].height
    )
