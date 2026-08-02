"""Tests for the pure layout solver.

Everything here is arithmetic on aspect ratios -- no images are opened, so
these run in milliseconds and can cover shapes that would be tedious to
build as real files.
"""

import itertools

import pytest

from maskingframe import geometry, layout
from maskingframe.geometry import DEFAULT_STYLE, FrameStyle

STYLE = FrameStyle(border_percent=9.0, gutter_percent=4.0)


def _node_named(name: str, count: int) -> layout.Node:
    for candidate_name, node in layout.candidates(count):
        if candidate_name == name:
            return node
    raise AssertionError(f"no candidate named {name}")


def _names_within(tolerance: float, aspects: list[float], ratio: geometry.AspectRatio) -> list[str]:
    """Every candidate scoring within `tolerance` of the best."""
    scored = {}
    for name, node in layout.candidates(len(aspects)):
        solved = layout.evaluate(node, name, aspects, ratio, geometry.DEFAULT_STYLE)
        if solved is not None:
            scored[name] = solved.score
    best = max(scored.values())
    return [name for name, score in scored.items() if best - score <= tolerance]


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
    assert solved.name == "C(1,2)"
    assert len(solved.boxes) == 2


def test_three_panoramas_stack_at_portrait() -> None:
    solved = layout.solve([2.33, 2.33, 2.33], geometry.PORTRAIT, STYLE)
    assert solved.name == "C(1,2,3)"
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


def test_only_counts_in_the_supported_range_are_accepted() -> None:
    with pytest.raises(ValueError):
        layout.solve([1.0], geometry.SQUARE, STYLE)
    with pytest.raises(ValueError):
        layout.solve([1.0] * 7, geometry.SQUARE, STYLE)


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
    solved = layout.evaluate(node, "C(1,2,3)", [2.33, 2.33, 2.33], geometry.PORTRAIT, STYLE)
    assert solved is not None
    pairs = list(zip(solved.boxes, solved.boxes[1:], strict=False))
    for gutter, (above, below) in zip(solved.gutters, pairs, strict=True):
        assert gutter.y <= above.y + above.height
        assert gutter.y + gutter.height >= below.y
        assert gutter.x <= above.x
        assert gutter.x + gutter.width >= above.x + above.width


def test_a_row_gutter_leaves_no_gap_on_either_side() -> None:
    node = layout.Row((layout.Leaf(0), layout.Leaf(1), layout.Leaf(2)))
    solved = layout.evaluate(node, "R(1,2,3)", [0.5, 0.5, 0.5], geometry.LANDSCAPE, STYLE)
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


def test_candidate_counts_are_the_one_level_arrangements() -> None:
    """Compositions of n into two or more consecutive blocks, times two
    orientations: 2^(n-1) - 1 doubled. Worked by hand rather than read off
    the implementation, so a change in the recursion fails here."""
    counts = {n: len(list(layout.candidates(n))) for n in range(2, 7)}
    assert counts == {2: 2, 3: 6, 4: 14, 5: 30, 6: 62}


def test_every_candidate_name_is_unique() -> None:
    for count in range(2, 7):
        names = [name for name, _ in layout.candidates(count)]
        assert len(set(names)) == len(names)


def test_the_three_panel_set_is_what_the_hand_written_list_gave() -> None:
    """The old list, renamed. Nothing at the current ceiling may move."""
    assert {name for name, _ in layout.candidates(3)} == {
        "R(1,2,3)",
        "C(1,2,3)",
        "R(1,C(2,3))",
        "R(C(1,2),3)",
        "C(1,R(2,3))",
        "C(R(1,2),3)",
    }


def test_the_two_panel_set_is_the_pair() -> None:
    assert {name for name, _ in layout.candidates(2)} == {"R(1,2)", "C(1,2)"}


def test_a_six_panel_grid_is_offered() -> None:
    names = {name for name, _ in layout.candidates(6)}
    assert "C(R(1,2,3),R(4,5,6))" in names
    assert "R(C(1,2),C(3,4),C(5,6))" in names
    assert "R(1,2,3,4,5,6)" in names


def _leaves(node: layout.Node) -> list[int]:
    if isinstance(node, layout.Leaf):
        return [node.index]
    return [index for child in node.children for index in _leaves(child)]


def test_every_candidate_uses_each_image_once_in_order() -> None:
    for count in range(2, 7):
        for name, node in layout.candidates(count):
            assert _leaves(node) == list(range(count)), name


def test_no_candidate_nests_more_than_one_level() -> None:
    for count in range(2, 7):
        for name, node in layout.candidates(count):
            assert layout.node_depth(node) <= 2, name


def test_a_group_never_repeats_its_parent_orientation() -> None:
    """R(R(1,2),3) and R(1,2,3) are the same picture. The alternation is
    what stops both being generated, so it is asserted directly."""
    for count in range(2, 7):
        for name, node in layout.candidates(count):
            assert not isinstance(node, layout.Leaf)
            for child in node.children:
                assert not isinstance(child, type(node)), name


@pytest.mark.parametrize("count", [0, 1, 7, 12])
def test_a_count_outside_the_range_is_refused_by_number(count: int) -> None:
    with pytest.raises(ValueError, match=f"got {count}"):
        list(layout.candidates(count))


def test_a_name_reads_the_tree_with_images_numbered_from_one() -> None:
    node = layout.Row((layout.Leaf(0), layout.Column((layout.Leaf(1), layout.Leaf(2)))))
    assert layout.name_of(node) == "R(1,C(2,3))"
    assert layout.name_of(layout.Leaf(3)) == "4"


def test_node_depth_counts_levels_of_grouping() -> None:
    assert layout.node_depth(layout.Leaf(0)) == 0
    assert layout.node_depth(layout.Row((layout.Leaf(0), layout.Leaf(1)))) == 1
    assert (
        layout.node_depth(
            layout.Row((layout.Leaf(0), layout.Column((layout.Leaf(1), layout.Leaf(2)))))
        )
        == 2
    )


def test_a_tie_is_won_by_the_shallowest_then_the_first_name() -> None:
    """Six frames from one camera share an aspect, so several arrangements
    fill the frame identically and something has to choose between them.

    The ordering asserted here is the whole rule, both terms at once, on
    the tie set worked out independently of `solve`. It is written this way
    rather than as a flat-beats-nested assertion because no such case
    exists: a sweep over every aspect combination in this file's pool, at
    every ratio and every count, finds no tie whose members differ in
    depth. Two arrangements that group their panels differently assemble to
    different shapes, so they do not fill the frame to within 1e-9 of each
    other. Depth is a guard against a tie that has never yet occurred, and
    the name is what actually decides the ties that do.
    """
    solved = layout.solve([1.0] * 6, geometry.RATIOS["1:1"])
    tied = _names_within(1e-9, [1.0] * 6, geometry.RATIOS["1:1"])

    assert len(tied) > 1, "no tie to break -- the test proves nothing"
    assert solved.name == min(
        tied, key=lambda name: (layout.node_depth(_node_named(name, 6)), name)
    )


def test_no_tie_has_ever_been_found_between_two_depths() -> None:
    """Pins the claim the test above rests on. If a cross-depth tie ever
    does appear, this fails and that docstring needs rewriting -- which is
    the point: the claim is checked rather than remembered."""
    pool = [1.0, 1.5, 0.6667, 2.0]
    for count in (2, 3, 4):
        for ratio in geometry.RATIOS.values():
            for combo in itertools.product(pool, repeat=count):
                scored = [
                    (solved.score, layout.node_depth(node))
                    for name, node in layout.candidates(count)
                    if (solved := layout.evaluate(node, name, combo, ratio, STYLE)) is not None
                ]
                if not scored:
                    continue
                best = max(score for score, _ in scored)
                depths = {depth for score, depth in scored if best - score <= layout.TIE_TOLERANCE}
                assert len(depths) == 1, (count, ratio.name, combo)


def test_a_tie_at_equal_depth_is_won_by_the_first_name() -> None:
    aspects = [1.0] * 4
    ratio = geometry.RATIOS["1:1"]
    solved = layout.solve(aspects, ratio)
    shallowest = min(
        layout.node_depth(_node_named(name, 4)) for name in _names_within(1e-9, aspects, ratio)
    )
    rivals = sorted(
        name
        for name in _names_within(1e-9, aspects, ratio)
        if layout.node_depth(_node_named(name, 4)) == shallowest
    )
    assert solved.name == rivals[0]


def test_a_clear_win_on_score_beats_a_shallower_arrangement() -> None:
    """Depth only ever breaks a tie. A flat row of six 3:2 frames at 4:5
    fills 5% of the frame; it must not win over a grid filling 88%."""
    solved = layout.solve([1.5] * 6, geometry.RATIOS["4:5"])
    assert solved.name != "R(1,2,3,4,5,6)"
    assert solved.score > 0.5
