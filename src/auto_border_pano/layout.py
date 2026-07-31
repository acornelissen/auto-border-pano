"""Automatic layout for composites.

Pure arithmetic on aspect ratios: no images are opened here, and nothing
touches the filesystem. A layout is a small tree of rows and columns whose
leaves are the supplied images, in order.

The central trick is that every node can state its width as an affine
function of its height, `width = A * height + B`. That holds for a leaf
(width is aspect times height), for a row (widths add, gutters are a
constant), and for a column (heights add, which inverts into the same
form). So one bottom-up pass gives the root its coefficients, the root is
fitted to the available box, and one top-down pass assigns rectangles.

Nothing is ever cropped: a box always has its image's own aspect ratio, and
whatever space that leaves over becomes border.
"""

import math
from collections.abc import Iterator, Sequence
from dataclasses import dataclass

from auto_border_pano.geometry import AspectRatio

GUTTER = 40


@dataclass(frozen=True)
class Box:
    """A panel's rectangle in output-frame pixel coordinates."""

    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class Layout:
    """A solved arrangement: which candidate won, where the panels go."""

    name: str
    boxes: tuple[Box, ...]
    score: float


@dataclass(frozen=True)
class Leaf:
    index: int


@dataclass(frozen=True)
class Row:
    children: tuple["Node", ...]


@dataclass(frozen=True)
class Column:
    children: tuple["Node", ...]


Node = Leaf | Row | Column


def candidates(count: int) -> Iterator[tuple[str, Node]]:
    """Every arrangement considered, in tie-break order.

    Order is fixed and never permuted -- panel 0 always holds image 0.
    """
    if count == 2:
        a, b = Leaf(0), Leaf(1)
        yield "row", Row((a, b))
        yield "column", Column((a, b))
        return
    if count == 3:
        a, b, c = Leaf(0), Leaf(1), Leaf(2)
        yield "row", Row((a, b, c))
        yield "column", Column((a, b, c))
        yield "row-one-then-two", Row((a, Column((b, c))))
        yield "row-two-then-one", Row((Column((a, b)), c))
        yield "column-one-then-two", Column((a, Row((b, c))))
        yield "column-two-then-one", Column((Row((a, b)), c))
        return
    raise ValueError(f"expected 2 or 3 images, got {count}")


def _coefficients(node: Node, aspects: Sequence[float], gutter: int) -> tuple[float, float]:
    """Return (A, B) such that this node's width = A * height + B."""
    if isinstance(node, Leaf):
        return aspects[node.index], 0.0

    parts = [_coefficients(child, aspects, gutter) for child in node.children]
    spacing = gutter * (len(node.children) - 1)

    if isinstance(node, Row):
        # Children share a height; their widths and the gutters add up.
        return sum(a for a, _ in parts), sum(b for _, b in parts) + spacing

    # Column: children share a width w, and their heights sum to the node's
    # height minus gutters. Inverting each child gives height = (w - B) / A.
    inverse = sum(1.0 / a for a, _ in parts)
    offset = sum(b / a for a, b in parts)
    return 1.0 / inverse, (offset - spacing) / inverse


def _place(
    node: Node,
    x: float,
    y: float,
    width: float,
    height: float,
    aspects: Sequence[float],
    gutter: int,
    out: dict[int, Box],
) -> bool:
    """Assign a concrete rectangle to every leaf under this node.

    Returns False, without mutating `out` further, if any leaf would round
    to less than 1px on either axis. A clamp there would silently distort
    that image (its box aspect would no longer match its source aspect),
    which breaks the no-crop guarantee the whole feature rests on -- so a
    candidate that can't place every leaf at >=1px loses instead.
    """
    if isinstance(node, Leaf):
        w = math.floor(width + 0.5)
        h = math.floor(height + 0.5)
        if w < 1 or h < 1:
            return False
        out[node.index] = Box(math.floor(x + 0.5), math.floor(y + 0.5), w, h)
        return True

    if isinstance(node, Row):
        offset = x
        for child in node.children:
            a, b = _coefficients(child, aspects, gutter)
            child_width = a * height + b
            if not _place(child, offset, y, child_width, height, aspects, gutter, out):
                return False
            offset += child_width + gutter
        return True

    offset = y
    for child in node.children:
        a, b = _coefficients(child, aspects, gutter)
        child_height = (width - b) / a
        if not _place(child, x, offset, width, child_height, aspects, gutter, out):
            return False
        offset += child_height + gutter
    return True


def evaluate(
    node: Node,
    name: str,
    aspects: Sequence[float],
    ratio: AspectRatio,
    padding: int,
    gutter: int,
) -> Layout | None:
    """Solve one candidate, or return None if it cannot fit sensibly."""
    available_width = ratio.width - 2 * padding
    available_height = ratio.height - 2 * padding
    if available_width <= 0 or available_height <= 0:
        return None

    # `a` is a sum (or reciprocal-sum) of the leaves' aspects, so it is
    # positive as long as every aspect is positive and finite -- a
    # precondition `solve` enforces before calling here. A non-positive or
    # non-finite leaf aspect fails earlier, inside `_coefficients`, with a
    # ZeroDivisionError or a garbage float rather than reaching this point,
    # so there is no honest `a <= 0` case left to guard against here.
    a, b = _coefficients(node, aspects, gutter)

    height = min(available_height, (available_width - b) / a)
    if height <= 0:
        return None
    width = a * height + b
    if width <= 0:
        return None

    # Centre the assembled block in the available box.
    x = padding + (available_width - width) / 2
    y = padding + (available_height - height) / 2

    placed: dict[int, Box] = {}
    if not _place(node, x, y, width, height, aspects, gutter, placed):
        return None
    boxes = tuple(placed[i] for i in range(len(aspects)))

    covered = sum(box.width * box.height for box in boxes)
    score = covered / (available_width * available_height)
    return Layout(name, boxes, score)


def solve(
    aspects: Sequence[float],
    ratio: AspectRatio,
    padding: int,
    gutter: int = GUTTER,
) -> Layout:
    """Choose the arrangement that fills the frame best without cropping.

    Every candidate keeps each panel at its own aspect ratio, so the choice
    is purely about which one wastes the least white space.
    """
    for index, aspect in enumerate(aspects):
        if not math.isfinite(aspect) or aspect <= 0:
            raise ValueError(f"aspect at index {index} must be finite and positive, got {aspect!r}")

    best: Layout | None = None
    for name, node in candidates(len(aspects)):
        solved = evaluate(node, name, aspects, ratio, padding, gutter)
        if solved is None:
            continue
        if best is None or solved.score > best.score:
            best = solved
    if best is None:
        raise ValueError(f"no usable layout for aspects {list(aspects)} at {ratio.name}")
    return best
