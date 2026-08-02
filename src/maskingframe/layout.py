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

from maskingframe.geometry import DEFAULT_STYLE, AspectRatio, FrameStyle


@dataclass(frozen=True)
class Box:
    """A panel's rectangle in output-frame pixel coordinates."""

    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class Layout:
    """A solved arrangement: which candidate won, where the panels go.

    `gutters` holds the exact rectangles between adjacent panels, so the
    renderer can paint them a second colour without re-deriving any of the
    arithmetic that produced them.
    """

    name: str
    boxes: tuple[Box, ...]
    gutters: tuple[Box, ...]
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


MIN_PANELS = 2
MAX_PANELS = 6


def name_of(node: Node) -> str:
    """This arrangement's canonical name, images numbered from one.

    `R(1,C(2,3))` is image 1 beside images 2 and 3 stacked. The numbering
    matches the numerals the sources list draws, so a name read off the
    interface points at the panels it names. Generated rather than written
    down: at six panels there are 62 of these.
    """
    if isinstance(node, Leaf):
        return str(node.index + 1)
    letter = "R" if isinstance(node, Row) else "C"
    return f"{letter}({','.join(name_of(child) for child in node.children)})"


def node_depth(node: Node) -> int:
    """How many levels of grouping this arrangement has. A leaf is 0."""
    if isinstance(node, Leaf):
        return 0
    return 1 + max(node_depth(child) for child in node.children)


def _blocks(count: int) -> Iterator[tuple[int, ...]]:
    """Every way to cut `count` ordered images into two or more blocks.

    These are the compositions of `count`, less the single-block one:
    2^(count-1) - 1 of them.
    """

    def walk(remaining: int, taken: tuple[int, ...]) -> Iterator[tuple[int, ...]]:
        if remaining == 0:
            if len(taken) >= 2:
                yield taken
            return
        for size in range(1, remaining + 1):
            yield from walk(remaining - size, (*taken, size))

    yield from walk(count, ())


def candidates(count: int) -> Iterator[tuple[str, Node]]:
    """Every arrangement considered, generated rather than listed.

    An arrangement is one root -- a row or a column -- whose parts are
    consecutive blocks of the images in input order. A block of one image is
    a leaf; a block of more is a group of the *opposite* orientation holding
    only leaves. There is no third level.

    The alternation is what makes the set canonical: without it `R(R(1,2),3)`
    and `R(1,2,3)` would both be generated for the same picture.

    One level is a restriction, not a consequence. Deeper trees exist -- 394
    of them at six panels rather than 62 -- and they fill the frame better,
    by up to 13 points. They are left out because the arrangements they win
    with, `C(R(C(R(1,C(2,3)),4),5),6)` and its like, are not ones anybody
    would lay out. The two- and three-panel sets are unaffected: every
    arrangement the old hand-written list held has one level of grouping.
    """
    if not MIN_PANELS <= count <= MAX_PANELS:
        raise ValueError(f"expected {MIN_PANELS} to {MAX_PANELS} images, got {count}")
    for root, inner in ((Row, Column), (Column, Row)):
        for sizes in _blocks(count):
            parts: list[Node] = []
            start = 0
            for size in sizes:
                leaves = tuple(Leaf(index) for index in range(start, start + size))
                parts.append(leaves[0] if size == 1 else inner(leaves))
                start += size
            node = root(tuple(parts))
            yield name_of(node), node


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
    gutters: list[Box],
) -> bool:
    """Assign a concrete rectangle to every leaf under this node.

    Returns False, without mutating `out` further, if any leaf would round
    to less than 1px on either axis. A clamp there would silently distort
    that image (its box aspect would no longer match its source aspect),
    which breaks the no-crop guarantee the whole feature rests on -- so a
    candidate that can't place every leaf at >=1px loses instead.

    Separator rectangles are collected alongside the leaves. Along the
    gutter axis each one is inflated by a pixel at both ends: a child's
    rounded edge can land a pixel off the rounded gutter edge, and the
    renderer paints gutters before panels, so an overlap disappears under a
    panel while a shortfall would show as a hairline of the wrong colour.
    The cross axis is not inflated -- bleeding there would put gutter
    colour into the outer border.
    """
    if isinstance(node, Leaf):
        w = math.floor(width + 0.5)
        h = math.floor(height + 0.5)
        # This floor is ">= 1px", not ">= 1px and aspect-faithful". With an
        # extreme mix of aspects (a >6:1 panel beside a <1:5 one) a panel can
        # clear this check while still rendering only a few pixels on its
        # short axis, well off its own aspect ratio -- rounding at that
        # scale can dominate the true shape. Unreachable with real
        # photographs, but do not read this guard as a quality guarantee.
        if w < 1 or h < 1:
            return False
        out[node.index] = Box(math.floor(x + 0.5), math.floor(y + 0.5), w, h)
        return True

    if isinstance(node, Row):
        top = math.floor(y + 0.5)
        band = math.floor(y + height + 0.5) - top
        offset = x
        for position, child in enumerate(node.children):
            a, b = _coefficients(child, aspects, gutter)
            child_width = a * height + b
            if not _place(child, offset, y, child_width, height, aspects, gutter, out, gutters):
                return False
            offset += child_width
            if gutter > 0 and position < len(node.children) - 1:
                left = math.floor(offset + 0.5) - 1
                right = math.floor(offset + gutter + 0.5) + 1
                gutters.append(Box(left, top, right - left, band))
            offset += gutter
        return True

    left = math.floor(x + 0.5)
    band = math.floor(x + width + 0.5) - left
    offset = y
    for position, child in enumerate(node.children):
        a, b = _coefficients(child, aspects, gutter)
        child_height = (width - b) / a
        if not _place(child, x, offset, width, child_height, aspects, gutter, out, gutters):
            return False
        offset += child_height
        if gutter > 0 and position < len(node.children) - 1:
            top = math.floor(offset + 0.5) - 1
            bottom = math.floor(offset + gutter + 0.5) + 1
            gutters.append(Box(left, top, band, bottom - top))
        offset += gutter
    return True


def evaluate(
    node: Node,
    name: str,
    aspects: Sequence[float],
    ratio: AspectRatio,
    style: FrameStyle,
) -> Layout | None:
    """Solve one candidate, or return None if it cannot fit sensibly.

    The style is a parameter rather than module state, so a preview and the
    run it previews cannot disagree about the border or the gutter.
    """
    padding = style.border_px(ratio)
    gutter = style.gutter_px(ratio)
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
    separators: list[Box] = []
    if not _place(node, x, y, width, height, aspects, gutter, placed, separators):
        return None
    boxes = tuple(placed[i] for i in range(len(aspects)))

    covered = sum(box.width * box.height for box in boxes)
    score = covered / (available_width * available_height)
    return Layout(name, boxes, tuple(separators), score)


# Two fill scores are the same score when they are this close. Exact float
# equality would let a rounding artefact one part in 10^16 decide which
# arrangement wins, which is precisely what the depth preference below
# exists to stop.
TIE_TOLERANCE = 1e-9


def solve(
    aspects: Sequence[float],
    ratio: AspectRatio,
    style: FrameStyle = DEFAULT_STYLE,
) -> Layout:
    """Choose the arrangement that fills the frame best without cropping.

    Every candidate keeps each panel at its own aspect ratio, so the first
    question is only which one wastes the least white space. Ties are
    common -- a set of frames from one camera shares an aspect ratio, and
    then whole families of arrangements fill the frame identically -- so
    they are broken by the shallower tree first and the earlier name
    second. Both are properties of the arrangement itself, so the winner
    does not depend on the order `candidates` happens to generate in.
    """
    for index, aspect in enumerate(aspects):
        if not math.isfinite(aspect) or aspect <= 0:
            raise ValueError(f"aspect at index {index} must be finite and positive, got {aspect!r}")

    ranked: list[tuple[int, str, Layout]] = []
    best_score: float | None = None
    for name, node in candidates(len(aspects)):
        solved = evaluate(node, name, aspects, ratio, style)
        if solved is None:
            continue
        ranked.append((node_depth(node), name, solved))
        if best_score is None or solved.score > best_score:
            best_score = solved.score
    if best_score is None:
        raise ValueError(f"no usable layout for aspects {list(aspects)} at {ratio.name}")

    tied = [entry for entry in ranked if best_score - entry[2].score <= TIE_TOLERANCE]
    tied.sort(key=lambda entry: (entry[0], entry[1]))
    return tied[0][2]
