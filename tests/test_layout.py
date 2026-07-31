"""Tests for the pure layout solver.

Everything here is arithmetic on aspect ratios -- no images are opened, so
these run in milliseconds and can cover shapes that would be tedious to
build as real files.
"""

import pytest

from auto_border_pano import geometry, layout

PADDING = geometry.SIDE_PADDING


def _box_aspect(box: layout.Box) -> float:
    return box.width / box.height


def test_two_equal_panoramas_stack_at_portrait() -> None:
    # Two 2.33:1 panoramas in a 1080x1350 frame: a column wins easily,
    # because a row would make each panel about 0.9:1.
    solved = layout.solve([2.33, 2.33], geometry.PORTRAIT, PADDING)
    assert solved.name == "column"
    assert len(solved.boxes) == 2


def test_three_panoramas_stack_at_portrait() -> None:
    solved = layout.solve([2.33, 2.33, 2.33], geometry.PORTRAIT, PADDING)
    assert solved.name == "column"
    assert len(solved.boxes) == 3


def test_panels_keep_their_source_aspect_ratio() -> None:
    # The no-cropping guarantee, stated as an assertion. Every box must
    # match the aspect of the image it will hold.
    aspects = [3.0, 1.0, 0.67]
    for ratio in geometry.RATIOS.values():
        solved = layout.solve(aspects, ratio, PADDING)
        for aspect, box in zip(aspects, solved.boxes, strict=True):
            assert abs(_box_aspect(box) - aspect) < 0.02, (ratio.name, aspect, box)


def test_boxes_never_overlap() -> None:
    aspects = [3.0, 1.0, 0.67]
    for ratio in geometry.RATIOS.values():
        boxes = layout.solve(aspects, ratio, PADDING).boxes
        for i, a in enumerate(boxes):
            for b in boxes[i + 1 :]:
                overlap_x = min(a.x + a.width, b.x + b.width) - max(a.x, b.x)
                overlap_y = min(a.y + a.height, b.y + b.height) - max(a.y, b.y)
                assert overlap_x <= 0 or overlap_y <= 0, (ratio.name, a, b)


def test_boxes_stay_inside_the_padded_frame() -> None:
    aspects = [3.0, 1.0, 0.67]
    for ratio in geometry.RATIOS.values():
        for box in layout.solve(aspects, ratio, PADDING).boxes:
            assert box.x >= PADDING - 1, (ratio.name, box)
            assert box.y >= PADDING - 1, (ratio.name, box)
            assert box.x + box.width <= ratio.width - PADDING + 1, (ratio.name, box)
            assert box.y + box.height <= ratio.height - PADDING + 1, (ratio.name, box)


def test_block_is_centred_in_the_frame() -> None:
    aspects = [2.33, 2.33, 2.33]
    boxes = layout.solve(aspects, geometry.PORTRAIT, PADDING).boxes
    left = min(b.x for b in boxes)
    right = geometry.PORTRAIT.width - max(b.x + b.width for b in boxes)
    top = min(b.y for b in boxes)
    bottom = geometry.PORTRAIT.height - max(b.y + b.height for b in boxes)
    assert abs(left - right) <= 1, (left, right)
    assert abs(top - bottom) <= 1, (top, bottom)


def test_order_is_never_permuted() -> None:
    # Box 0 must hold image 0. With a column layout that means boxes are
    # top to bottom; with a row, left to right.
    solved = layout.solve([3.0, 0.5], geometry.SQUARE, PADDING)
    assert abs(_box_aspect(solved.boxes[0]) - 3.0) < 0.02
    assert abs(_box_aspect(solved.boxes[1]) - 0.5) < 0.02


def test_extreme_aspects_still_produce_valid_boxes() -> None:
    for aspects in ([20.0, 20.0], [0.05, 0.05], [20.0, 0.05, 1.0]):
        for ratio in geometry.RATIOS.values():
            for box in layout.solve(aspects, ratio, PADDING).boxes:
                assert box.width >= 1, (aspects, ratio.name, box)
                assert box.height >= 1, (aspects, ratio.name, box)


def test_score_is_a_fraction_of_the_available_box() -> None:
    solved = layout.solve([2.33, 2.33], geometry.PORTRAIT, PADDING)
    assert 0.0 < solved.score <= 1.0


def test_winning_candidate_fills_at_least_as_much_as_the_alternatives() -> None:
    # Whatever the solver picked must score at least as well as every other
    # candidate it considered.
    aspects = [3.0, 1.0, 0.67]
    for ratio in geometry.RATIOS.values():
        solved = layout.solve(aspects, ratio, PADDING)
        for name, candidate in layout.candidates(len(aspects)):
            other = layout.evaluate(candidate, name, aspects, ratio, PADDING, layout.GUTTER)
            if other is not None:
                assert solved.score >= other.score - 1e-9, (ratio.name, name)


def test_only_two_or_three_images_are_supported() -> None:
    with pytest.raises(ValueError):
        layout.solve([1.0], geometry.SQUARE, PADDING)
    with pytest.raises(ValueError):
        layout.solve([1.0, 1.0, 1.0, 1.0], geometry.SQUARE, PADDING)
