# Diptych and Triptych Compositor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A second GUI tab that composes two or three photographs into one frame at any supported aspect ratio, choosing the arrangement automatically from the images themselves.

**Architecture:** A pure-arithmetic solver (`layout.py`) represents a layout as a small tree of rows and columns, states each node's width as an affine function of its height, solves the root against the available box, and scores candidates on how much of the frame they fill. `compose.py` renders the winning boxes onto a canvas. `pipeline.py` handles file I/O. The GUI becomes a package with a notebook shell and two tabs sharing one preview widget.

**Tech Stack:** Python 3.13, Pillow, pytest, ruff, mypy strict, tkinter, mise + uv.

## Global Constraints

- **Nothing is ever cropped.** Every panel keeps its full composition. This is what makes "works for all image sizes and aspect ratios" true, and it is the constraint most likely to be quietly violated by a well-meaning "fill the frame" tweak.
- Image order is preserved exactly as given. Candidates never permute the inputs.
- Outer margin is `geometry.SIDE_PADDING` (100 output pixels). Gutter is 40 output pixels.
- Output canvas is exactly `(ratio.width, ratio.height)`; the assembled block is centred.
- Composites accept **2 or 3** images. Any other count raises `ValueError`.
- Portrait images are valid input here, unlike the splitter. Mixing orientations is the point.
- Use half-up rounding via `math.floor(x + 0.5)`, never Python's `round()`, which is banker's rounding.
- Resampling is `Image.Resampling.LANCZOS`. JPEG quality is 95.
- `cli.py` and `gui/` must not import `geometry` directly — `pipeline.py` re-exports `AspectRatio`, `RATIOS`, `DEFAULT_RATIO` for them.
- THREADING INVARIANT: no worker thread may read or write any tkinter object. Values are read on the main thread and passed as plain data; `root.after` is the only crossing back. This was a real bug fixed twice in this project.
- Conventional commits, imperative mood. **No Claude/AI attribution or Co-Authored-By trailers** — a git hook rejects them.
- Existing behaviour must not change: the splitter's golden hashes in `tests/test_pipeline.py` must not move.

---

## File Structure

| File | Responsibility |
| ---- | -------------- |
| `src/maskingframe/layout.py` | Pure layout solver. No PIL, no I/O |
| `src/maskingframe/compose.py` | Renders solved boxes onto a canvas. PIL in, PIL out |
| `src/maskingframe/pipeline.py` | Gains `compose_images` and `CompositeResult` |
| `src/maskingframe/gui/__init__.py` | Re-exports `run`, `PanoramaSplitterGUI`, `preview_titles` |
| `src/maskingframe/gui/app.py` | Notebook shell; owns the root window |
| `src/maskingframe/gui/split_tab.py` | Today's splitter UI, moved |
| `src/maskingframe/gui/compose_tab.py` | The new tab |
| `src/maskingframe/gui/preview.py` | Thumbnail pane grid, shared by both tabs |
| `tests/test_layout.py` | Solver tests — the bulk of the value |
| `tests/test_compose.py` | Rendering tests |
| `tests/test_pipeline.py` | Gains composite I/O and golden tests |
| `tests/test_gui.py` | Gains compose-tab tests |
| `README.md`, `CLAUDE.md` | Document the tab and the solver rule |

---

### Task 1: The layout solver

This is the feature. It is pure arithmetic, so it can be tested exhaustively without opening a single image.

**Files:**
- Create: `src/maskingframe/layout.py`
- Create: `tests/test_layout.py`

**Interfaces:**
- Consumes: `geometry.AspectRatio` (has `.name`, `.width`, `.height`, `.value`, `.label`, `.display`)
- Produces:
  - `Box` frozen dataclass: `x: int`, `y: int`, `width: int`, `height: int`
  - `Layout` frozen dataclass: `name: str`, `boxes: tuple[Box, ...]`, `score: float`
  - `GUTTER: int = 40`
  - `solve(aspects: Sequence[float], ratio: AspectRatio, padding: int, gutter: int = GUTTER) -> Layout`

- [ ] **Step 1: Write the failing tests**

`tests/test_layout.py`:

```python
"""Tests for the pure layout solver.

Everything here is arithmetic on aspect ratios -- no images are opened, so
these run in milliseconds and can cover shapes that would be tedious to
build as real files.
"""

import pytest

from maskingframe import geometry, layout

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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `mise exec -- uv run pytest tests/test_layout.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'maskingframe.layout'`

- [ ] **Step 3: Write the implementation**

`src/maskingframe/layout.py`:

```python
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

from maskingframe.geometry import AspectRatio

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
    aspect: float


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
        a, b = Leaf(0, 0.0), Leaf(1, 0.0)
        yield "row", Row((a, b))
        yield "column", Column((a, b))
        return
    if count == 3:
        a, b, c = Leaf(0, 0.0), Leaf(1, 0.0), Leaf(2, 0.0)
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
) -> None:
    """Assign a concrete rectangle to every leaf under this node."""
    if isinstance(node, Leaf):
        out[node.index] = Box(
            math.floor(x + 0.5),
            math.floor(y + 0.5),
            max(1, math.floor(width + 0.5)),
            max(1, math.floor(height + 0.5)),
        )
        return

    if isinstance(node, Row):
        offset = x
        for child in node.children:
            a, b = _coefficients(child, aspects, gutter)
            child_width = a * height + b
            _place(child, offset, y, child_width, height, aspects, gutter, out)
            offset += child_width + gutter
        return

    offset = y
    for child in node.children:
        a, b = _coefficients(child, aspects, gutter)
        child_height = (width - b) / a
        _place(child, x, offset, width, child_height, aspects, gutter, out)
        offset += child_height + gutter


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

    a, b = _coefficients(node, aspects, gutter)
    if a <= 0:
        return None

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
    _place(node, x, y, width, height, aspects, gutter, placed)
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `mise run check`
Expected: all pass, ruff and mypy clean.

If `test_two_equal_panoramas_stack_at_portrait` reports `row-two-then-one` or similar rather than `column`, do not weaken the assertion — print the score of every candidate and work out whether the coefficient maths is wrong. A row of two 2.33:1 panels in a 1080x1350 frame genuinely fills far less than a column.

- [ ] **Step 5: Commit**

```bash
git add src/maskingframe/layout.py tests/test_layout.py
git commit -m "feat(layout): solve composite arrangements automatically

Each node states its width as an affine function of its height, so one
bottom-up pass gives the root its coefficients and one top-down pass
assigns rectangles. Panels always keep their own aspect ratio, so no image
is ever cropped and the choice is purely about wasted space."
```

---

### Task 2: Render the composite

**Files:**
- Create: `src/maskingframe/compose.py`
- Create: `tests/test_compose.py`

**Interfaces:**
- Consumes: `layout.Layout`, `layout.Box`, `geometry.AspectRatio`, `geometry.BACKGROUND`
- Produces: `render(images: Sequence[Image.Image], solved: Layout, ratio: AspectRatio) -> Image.Image`

- [ ] **Step 1: Write the failing tests**

`tests/test_compose.py`:

```python
"""Tests for composite rendering."""

import pytest
from PIL import Image

from maskingframe import compose, geometry, layout

PADDING = geometry.SIDE_PADDING


def _image(width: int, height: int, colour: tuple[int, int, int]) -> Image.Image:
    return Image.new("RGB", (width, height), colour)


def test_composite_is_exactly_the_target_size() -> None:
    images = [_image(900, 300, (255, 0, 0)), _image(900, 300, (0, 255, 0))]
    aspects = [im.width / im.height for im in images]
    for ratio in geometry.RATIOS.values():
        solved = layout.solve(aspects, ratio, PADDING)
        result = compose.render(images, solved, ratio)
        assert result.size == (ratio.width, ratio.height), ratio.name


def test_background_is_white() -> None:
    images = [_image(900, 300, (255, 0, 0)), _image(900, 300, (0, 255, 0))]
    aspects = [im.width / im.height for im in images]
    solved = layout.solve(aspects, geometry.PORTRAIT, PADDING)
    result = compose.render(images, solved, geometry.PORTRAIT)
    assert result.getpixel((0, 0)) == (255, 255, 255)


def test_every_panel_lands_where_the_layout_said() -> None:
    # Distinct flat colours make each panel identifiable by pixel probe.
    images = [_image(900, 300, (255, 0, 0)), _image(300, 900, (0, 0, 255))]
    aspects = [im.width / im.height for im in images]
    solved = layout.solve(aspects, geometry.SQUARE, PADDING)
    result = compose.render(images, solved, geometry.SQUARE)
    for box, colour in zip(solved.boxes, [(255, 0, 0), (0, 0, 255)], strict=True):
        centre = (box.x + box.width // 2, box.y + box.height // 2)
        assert result.getpixel(centre) == colour, (box, colour)


def test_render_rejects_a_layout_that_would_distort_a_panel() -> None:
    # A box whose aspect disagrees with its image means the solver is
    # broken; rendering must fail loudly rather than stretch the photo.
    images = [_image(900, 300, (255, 0, 0)), _image(900, 300, (0, 255, 0))]
    bad = layout.Layout(
        "bad",
        (layout.Box(100, 100, 400, 400), layout.Box(100, 600, 400, 400)),
        0.5,
    )
    with pytest.raises(ValueError, match="aspect"):
        compose.render(images, bad, geometry.SQUARE)


def test_render_requires_one_box_per_image() -> None:
    images = [_image(900, 300, (255, 0, 0))]
    solved = layout.Layout(
        "bad", (layout.Box(0, 0, 10, 10), layout.Box(20, 0, 10, 10)), 0.5
    )
    with pytest.raises(ValueError):
        compose.render(images, solved, geometry.SQUARE)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `mise exec -- uv run pytest tests/test_compose.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'maskingframe.compose'`

- [ ] **Step 3: Write the implementation**

`src/maskingframe/compose.py`:

```python
"""Render a solved layout into a single image.

Like geometry.py this works in PIL images and never touches the
filesystem. The layout has already decided every rectangle; this module
only scales and pastes.
"""

import math
from collections.abc import Sequence

from PIL import Image

from maskingframe.geometry import BACKGROUND, AspectRatio
from maskingframe.layout import Layout

# A box comes from the image's own aspect ratio, so the two should agree to
# within integer rounding. More than this means the solver is wrong, and
# rendering anyway would silently stretch the photograph.
ASPECT_TOLERANCE_PX = 2


def render(
    images: Sequence[Image.Image], solved: Layout, ratio: AspectRatio
) -> Image.Image:
    """Scale each image into its box and paste onto a white canvas."""
    if len(images) != len(solved.boxes):
        raise ValueError(
            f"layout has {len(solved.boxes)} boxes for {len(images)} images"
        )

    canvas = Image.new("RGB", (ratio.width, ratio.height), BACKGROUND)
    for image, box in zip(images, solved.boxes, strict=True):
        expected = math.floor(box.height * (image.width / image.height) + 0.5)
        if abs(box.width - expected) > ASPECT_TOLERANCE_PX:
            raise ValueError(
                f"box aspect {box.width}x{box.height} does not match image "
                f"{image.width}x{image.height}; refusing to distort it"
            )
        panel = image.resize((box.width, box.height), Image.Resampling.LANCZOS)
        canvas.paste(panel, (box.x, box.y))
    return canvas
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `mise run check`
Expected: all pass, ruff and mypy clean.

- [ ] **Step 5: Commit**

```bash
git add src/maskingframe/compose.py tests/test_compose.py
git commit -m "feat(compose): render a solved layout onto a white canvas

Refuses a box whose aspect disagrees with its image, so a solver bug
surfaces as a loud failure rather than a subtly stretched photograph."
```

---

### Task 3: Composite file I/O

**Files:**
- Modify: `src/maskingframe/pipeline.py`
- Modify: `tests/test_pipeline.py`
- Create: `tests/fixtures/compose_wide.jpg`, `tests/fixtures/compose_square.jpg`, `tests/fixtures/compose_tall.jpg`

**Interfaces:**
- Consumes: `layout.solve`, `layout.GUTTER`, `compose.render`, `geometry.SIDE_PADDING`
- Produces:
  - `CompositeResult` frozen dataclass: `path: Path`, `layout_name: str`
  - `COMPOSITE_SUFFIXES: dict[int, str]` = `{2: "_diptych.jpg", 3: "_triptych.jpg"}`
  - `compose_images(input_paths: Sequence[Path | str], output_prefix: Path | str, ratio: AspectRatio = DEFAULT_RATIO) -> CompositeResult`

- [ ] **Step 1: Create the fixtures**

Three small images of clearly different shapes, so the golden test exercises a real mix rather than three copies of the same thing.

```bash
mise exec -- uv run python -c "
from PIL import Image
specs = {'compose_wide': (600, 250), 'compose_square': (400, 400), 'compose_tall': (300, 450)}
for name, (w, h) in specs.items():
    img = Image.new('RGB', (w, h))
    px = img.load()
    for x in range(w):
        for y in range(h):
            px[x, y] = (x % 256, y % 256, (x + y) % 256)
    img.save(f'tests/fixtures/{name}.jpg', 'JPEG', quality=95)
    print('wrote', name, img.size)
"
```

- [ ] **Step 2: Write the failing tests**

Add to `tests/test_pipeline.py`:

```python
COMPOSE_FIXTURES = [
    Path(__file__).parent / "fixtures" / name
    for name in ("compose_wide.jpg", "compose_square.jpg", "compose_tall.jpg")
]


def test_compose_two_images_writes_a_diptych(tmp_path: Path) -> None:
    result = pipeline.compose_images(COMPOSE_FIXTURES[:2], tmp_path / "out")
    assert result.path.name == "out_diptych.jpg"
    assert result.path.exists()
    assert result.layout_name


def test_compose_three_images_writes_a_triptych(tmp_path: Path) -> None:
    result = pipeline.compose_images(COMPOSE_FIXTURES, tmp_path / "out")
    assert result.path.name == "out_triptych.jpg"
    assert result.path.exists()


def test_composite_is_exactly_the_target_size(tmp_path: Path) -> None:
    for ratio in pipeline.RATIOS.values():
        result = pipeline.compose_images(
            COMPOSE_FIXTURES, tmp_path / ratio.name.replace(":", "-"), ratio
        )
        with Image.open(result.path) as img:
            assert img.size == (ratio.width, ratio.height), ratio.name


def test_compose_rejects_wrong_image_counts(tmp_path: Path) -> None:
    import pytest

    with pytest.raises(ValueError):
        pipeline.compose_images(COMPOSE_FIXTURES[:1], tmp_path / "out")
    with pytest.raises(ValueError):
        pipeline.compose_images(COMPOSE_FIXTURES * 2, tmp_path / "out")


def test_compose_accepts_portrait_images(tmp_path: Path) -> None:
    # Unlike the splitter, a composite has no notion of a panorama and
    # mixing orientations is the point of the feature.
    tall = COMPOSE_FIXTURES[2]
    result = pipeline.compose_images([tall, tall], tmp_path / "out")
    assert result.path.exists()


def test_compose_creates_the_output_directory(tmp_path: Path) -> None:
    result = pipeline.compose_images(
        COMPOSE_FIXTURES[:2], tmp_path / "nested" / "deeper" / "out"
    )
    assert result.path.exists()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `mise exec -- uv run pytest tests/test_pipeline.py -k compose -v`
Expected: FAIL with `AttributeError: module 'maskingframe.pipeline' has no attribute 'compose_images'`

- [ ] **Step 4: Write the implementation**

Add to `src/maskingframe/pipeline.py`, importing `compose` and `layout` alongside the existing `geometry` import:

```python
COMPOSITE_SUFFIXES = {2: "_diptych.jpg", 3: "_triptych.jpg"}


@dataclass(frozen=True)
class CompositeResult:
    """Where a composite was written, and which arrangement won.

    The layout name is carried back so the GUI can show the automatic
    decision rather than leaving it mysterious.
    """

    path: Path
    layout_name: str


def compose_images(
    input_paths: Sequence[Path | str],
    output_prefix: Path | str,
    ratio: AspectRatio = DEFAULT_RATIO,
) -> CompositeResult:
    """Compose two or three images into one frame at the target ratio."""
    paths = [Path(p) for p in input_paths]
    if len(paths) not in COMPOSITE_SUFFIXES:
        raise ValueError(f"expected 2 or 3 images, got {len(paths)}")

    images = []
    for path in paths:
        with Image.open(path) as opened:
            images.append(opened.convert("RGB"))

    aspects = [image.width / image.height for image in images]
    solved = layout.solve(aspects, ratio, geometry.SIDE_PADDING, layout.GUTTER)
    canvas = compose.render(images, solved, ratio)

    prefix = Path(output_prefix)
    target = prefix.with_name(prefix.name + COMPOSITE_SUFFIXES[len(paths)])
    target.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(target, "JPEG", quality=JPEG_QUALITY)
    return CompositeResult(target, solved.name)
```

Add `from collections.abc import Callable, Sequence` to the imports if `Sequence` is not already there.

- [ ] **Step 5: Run tests to verify they pass**

Run: `mise run check`
Expected: all pass. Confirm the splitter's existing golden hashes are untouched:

```bash
git diff --stat tests/test_pipeline.py
mise exec -- uv run pytest tests/test_pipeline.py -k golden -v
```

- [ ] **Step 6: Add a composite golden test**

Add to `tests/test_pipeline.py`, generating the hashes with:

```bash
mise exec -- uv run python -c "
import hashlib, tempfile
from pathlib import Path
from maskingframe import pipeline
fixtures = [Path('tests/fixtures') / n for n in ('compose_wide.jpg','compose_square.jpg','compose_tall.jpg')]
with tempfile.TemporaryDirectory() as tmp:
    for name, ratio in pipeline.RATIOS.items():
        r = pipeline.compose_images(fixtures, Path(tmp) / name.replace(':','-'), ratio)
        print(f'    {name!r}: {hashlib.sha256(r.path.read_bytes()).hexdigest()!r},')
"
```

```python
# Byte-identity guard for composites, matching the splitter's convention.
# Tied to the installed Pillow version's JPEG encoder; regenerate with the
# command in the plan if a deliberate Pillow upgrade changes encoding.
COMPOSITE_GOLDEN_HASHES: dict[str, str] = {
    # <-- paste the generated lines here
}


def test_composite_outputs_are_byte_identical(tmp_path: Path) -> None:
    import hashlib

    for name, expected in COMPOSITE_GOLDEN_HASHES.items():
        result = pipeline.compose_images(
            COMPOSE_FIXTURES, tmp_path / name.replace(":", "-"), pipeline.RATIOS[name]
        )
        actual = hashlib.sha256(result.path.read_bytes()).hexdigest()
        assert actual == expected, f"composite changed at {name}"
```

Prove it can fail: temporarily change `layout.GUTTER` to 41, confirm this test fails, restore 40, confirm it passes. Paste both outcomes in your report.

- [ ] **Step 7: Commit**

```bash
git add src/maskingframe/pipeline.py tests/test_pipeline.py tests/fixtures
git commit -m "feat(pipeline): write diptych and triptych composites

Carries the winning layout's name back to the caller so the UI can show
which arrangement was chosen automatically."
```

---

### Task 4: Split the GUI into a package

A pure move plus one extraction. **No behaviour changes.** The existing GUI tests must pass unchanged apart from nothing at all — they import `from maskingframe import gui` and use `gui.PanoramaSplitterGUI` and `gui.preview_titles`, both of which the package must keep exporting.

**Files:**
- Create: `src/maskingframe/gui/__init__.py`, `gui/app.py`, `gui/split_tab.py`, `gui/preview.py`
- Delete: `src/maskingframe/gui.py`

**Interfaces:**
- Consumes: `pipeline` only. No module here may import `geometry`.
- Produces:
  - `gui.run() -> None` — unchanged entry point used by `cli.gui_main`
  - `gui.PanoramaSplitterGUI` — re-exported from `split_tab`
  - `gui.preview_titles(count: int) -> list[str]` — re-exported from `split_tab`
  - `preview.PreviewPanes` with `frame`, `rebuild(titles)`, `show_paths(paths)`, `show_images(images)`

- [ ] **Step 1: Create the package skeleton and move the code**

```bash
mkdir -p src/maskingframe/gui
git mv src/maskingframe/gui.py src/maskingframe/gui/split_tab.py
```

`src/maskingframe/gui/__init__.py`:

```python
"""tkinter front end.

Importing this package raises ImportError when tkinter is missing; the
friendly message lives in cli.gui_main.
"""

from maskingframe.gui.app import run
from maskingframe.gui.split_tab import PanoramaSplitterGUI, preview_titles

__all__ = ["PanoramaSplitterGUI", "preview_titles", "run"]
```

`src/maskingframe/gui/app.py`:

```python
"""The application shell.

Owns the root window and the notebook; the tabs own everything inside
themselves.
"""

import tkinter as tk

from maskingframe.gui.split_tab import PanoramaSplitterGUI


def run() -> None:
    root = tk.Tk()
    root.title("Panorama Splitter")
    root.geometry("900x700")
    PanoramaSplitterGUI(root)
    root.mainloop()
```

- [ ] **Step 2: Make the splitter constructible from any parent**

In `split_tab.py`, `PanoramaSplitterGUI.__init__` currently calls `self.root.title(...)` and `self.root.geometry(...)`. Those move to `app.run()` (already shown above), because a notebook tab must not retitle the window. Delete those two lines from `__init__` and leave everything else alone.

Keep the parameter named `root` and keep storing it as `self.root` — `root.after` is the threading crossing and every worker uses it. A `ttk.Frame` also has `.after`, so this keeps working when the parent becomes a notebook page in Task 5.

- [ ] **Step 3: Extract the preview panes**

`src/maskingframe/gui/preview.py`:

```python
"""A row of thumbnail panes that rebuilds as the count changes.

Shared by both tabs. This is the fiddliest widget code in the project: the
pane count varies between runs, so stale panes and stale grid weights both
have to be cleared, and PhotoImage references have to be held or Tk renders
blanks.
"""

import tkinter as tk
from collections.abc import Sequence
from pathlib import Path
from tkinter import ttk

from PIL import Image, ImageTk

PREVIEW_MAX_PX = 150


class PreviewPanes:
    def __init__(self, parent: tk.Misc, title: str = "Preview") -> None:
        self.frame = ttk.LabelFrame(parent, text=title, padding="10")
        self.frame.rowconfigure(0, weight=1)
        self.labels: list[ttk.Label] = []
        self._images: list[ImageTk.PhotoImage] = []
        self._max_columns = 0

    def rebuild(self, titles: Sequence[str]) -> None:
        """Recreate the cells. Main thread only."""
        for child in self.frame.winfo_children():
            child.destroy()
        self.labels = []

        for column, title in enumerate(titles):
            self.frame.columnconfigure(column, weight=1)
            cell = ttk.Frame(self.frame)
            cell.grid(row=0, column=column, padx=5, pady=5, sticky=(tk.N, tk.S, tk.E, tk.W))
            ttk.Label(cell, text=title, font=("Arial", 10, "bold")).pack()
            label = ttk.Label(cell, text="No preview", relief="sunken", anchor="center")
            label.pack(expand=True, fill="both")
            self.labels.append(label)

        # Drop stale column weights from any previous, longer run, up to the
        # highest column count this instance has ever built.
        for column in range(len(titles), self._max_columns + 1):
            self.frame.columnconfigure(column, weight=0)
        self._max_columns = max(self._max_columns, len(titles))

    def show_paths(self, paths: Sequence[Path]) -> None:
        """Load thumbnails from files, one per existing pane."""
        images: list[ImageTk.PhotoImage] = []
        for label, path in zip(self.labels, paths, strict=True):
            if not path.exists():
                label.config(image="", text="No preview")
                continue
            try:
                with Image.open(path) as img:
                    img.thumbnail((PREVIEW_MAX_PX, PREVIEW_MAX_PX), Image.Resampling.LANCZOS)
                    photo = ImageTk.PhotoImage(img)
            except Exception as error:
                label.config(image="", text=f"Error: {error}")
                continue
            images.append(photo)
            label.config(image=photo, text="")
        self._images = images

    def show_images(self, images: Sequence[Image.Image]) -> None:
        """Show already-loaded images, one per existing pane."""
        photos: list[ImageTk.PhotoImage] = []
        for label, image in zip(self.labels, images, strict=True):
            thumbnail = image.copy()
            thumbnail.thumbnail((PREVIEW_MAX_PX, PREVIEW_MAX_PX), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(thumbnail)
            photos.append(photo)
            label.config(image=photo, text="")
        self._images = photos
```

Then in `split_tab.py`, replace the inline preview code with this widget: delete `_rebuild_preview_panes`, `self.preview_labels`, `self._preview_images`, `self._max_preview_columns` and the `PREVIEW_MAX_PX` constant, construct `self.previews = PreviewPanes(main, "Preview (Last Processed)")` where `self.preview_frame` was built, grid `self.previews.frame` in the same cell with the same options, and rewrite `update_preview` as:

```python
    def update_preview(self, output_prefix: str, count: int) -> None:
        self.previews.rebuild(preview_titles(count))
        self.previews.show_paths(pipeline.output_paths(output_prefix, count))
```

- [ ] **Step 4: Fix the existing GUI tests' expectations, if any broke**

Run: `mise exec -- uv run pytest tests/test_gui.py -v`

Tests referencing `app.preview_labels` or `app._rebuild_preview_panes` now need `app.previews.labels` and `app.previews.rebuild(...)`. Update the test bodies but **not** their assertions — the point of this task is that behaviour is identical. If an assertion needs weakening to pass, stop: something moved that should not have.

- [ ] **Step 5: Verify the whole tree**

Run: `mise run check`
Expected: green, with the same test count as before this task.

Also confirm the entry point still resolves:

```bash
mise exec -- uv run python -c "
from maskingframe.gui import run, PanoramaSplitterGUI, preview_titles
print('exports OK', run.__module__, PanoramaSplitterGUI.__module__)
"
```

- [ ] **Step 6: Commit**

```bash
git add -A src/maskingframe/gui tests/test_gui.py
git commit -m "refactor(gui): split into a package and extract the preview panes

A second tab would push a single module past 500 lines. The preview grid
is extracted because both tabs need it, and it is the trickiest widget
code here -- varying pane counts, stale grid weights, PhotoImage lifetime.

Pure move: no behaviour changes."
```

---

### Task 5: The notebook shell and the compose tab

**Files:**
- Create: `src/maskingframe/gui/compose_tab.py`
- Modify: `src/maskingframe/gui/app.py`
- Modify: `tests/test_gui.py`

**Interfaces:**
- Consumes: `pipeline.compose_images`, `pipeline.CompositeResult`, `pipeline.RATIOS`, `pipeline.DEFAULT_RATIO`, `preview.PreviewPanes`
- Produces: `ComposeTab` class with `frame`, `images: list[str]`, `add_image()`, `move_up()`, `move_down()`, `remove()`, `compose()`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_gui.py`:

```python
def test_compose_tab_requires_two_or_three_images() -> None:
    from maskingframe.gui import compose_tab

    tab = compose_tab.ComposeTab.__new__(compose_tab.ComposeTab)
    tab.images = ["a.jpg"]
    assert not tab.can_compose()
    tab.images = ["a.jpg", "b.jpg"]
    assert tab.can_compose()
    tab.images = ["a.jpg", "b.jpg", "c.jpg"]
    assert tab.can_compose()
    tab.images = ["a.jpg", "b.jpg", "c.jpg", "d.jpg"]
    assert not tab.can_compose()


def test_compose_tab_reordering_changes_the_order() -> None:
    from maskingframe.gui import compose_tab

    tab = compose_tab.ComposeTab.__new__(compose_tab.ComposeTab)
    tab.images = ["a.jpg", "b.jpg", "c.jpg"]
    tab._selection = 2
    tab._swap(2, 1)
    assert tab.images == ["a.jpg", "c.jpg", "b.jpg"]


def test_compose_worker_reports_the_layout_name(tmp_path: Path) -> None:
    # The worker runs off the main thread and must hand everything back
    # through root.after -- the same discipline as the splitter's workers.
    from maskingframe.gui import compose_tab

    fixtures = Path(__file__).parent / "fixtures"
    sources = [str(fixtures / "compose_wide.jpg"), str(fixtures / "compose_square.jpg")]

    calls: list[tuple[Any, ...]] = []

    class StubRoot:
        def after(self, _delay: int, func: Any, *args: Any) -> None:
            calls.append(args)
            func(*args)

    tab = compose_tab.ComposeTab.__new__(compose_tab.ComposeTab)
    tab.root = StubRoot()
    tab._finish = lambda *args: calls.append(args)  # type: ignore[method-assign]

    tab._run_compose(sources, str(tmp_path / "out"), "4:5")

    assert calls, "worker never reported back through root.after"
    assert (tmp_path / "out_diptych.jpg").exists()


def test_compose_worker_reports_failure_without_dying(tmp_path: Path) -> None:
    from maskingframe.gui import compose_tab

    calls: list[tuple[Any, ...]] = []

    class StubRoot:
        def after(self, _delay: int, func: Any, *args: Any) -> None:
            calls.append(args)
            func(*args)

    tab = compose_tab.ComposeTab.__new__(compose_tab.ComposeTab)
    tab.root = StubRoot()
    tab._finish = lambda *args: calls.append(args)  # type: ignore[method-assign]

    tab._run_compose(["/does/not/exist.jpg", "/nor/this.jpg"], str(tmp_path / "out"), "4:5")

    assert calls, "worker died silently instead of reporting the error"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `mise exec -- uv run pytest tests/test_gui.py -k compose -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'maskingframe.gui.compose_tab'`

- [ ] **Step 3: Write the compose tab**

`src/maskingframe/gui/compose_tab.py`:

```python
"""The diptych and triptych tab.

Pick two or three images, choose a target ratio, and the arrangement is
solved automatically from the images' own shapes.
"""

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image

from maskingframe import pipeline
from maskingframe.gui.preview import PreviewPanes

MIN_IMAGES = 2
MAX_IMAGES = 3

_RATIO_BY_DISPLAY: dict[str, str] = {r.display: r.name for r in pipeline.RATIOS.values()}


class ComposeTab:
    def __init__(self, parent: tk.Misc) -> None:
        self.root = parent
        self.frame = ttk.Frame(parent, padding="10")
        self.images: list[str] = []
        self._selection: int | None = None

        self.output_path = tk.StringVar()
        self.ratio = tk.StringVar(value=pipeline.DEFAULT_RATIO.display)
        self.status = tk.StringVar(value="Add two or three images")

        self._build_ui()

    def can_compose(self) -> bool:
        return MIN_IMAGES <= len(self.images) <= MAX_IMAGES

    def _build_ui(self) -> None:
        self.frame.columnconfigure(0, weight=1)

        listbox_row = ttk.Frame(self.frame)
        listbox_row.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=5)
        listbox_row.columnconfigure(0, weight=1)

        self.listbox = tk.Listbox(listbox_row, height=4)
        self.listbox.grid(row=0, column=0, sticky=(tk.W, tk.E))
        self.listbox.bind("<<ListboxSelect>>", self._on_select)

        buttons = ttk.Frame(listbox_row)
        buttons.grid(row=0, column=1, padx=5)
        ttk.Button(buttons, text="Add", command=self.add_image).pack(fill="x")
        ttk.Button(buttons, text="Up", command=self.move_up).pack(fill="x")
        ttk.Button(buttons, text="Down", command=self.move_down).pack(fill="x")
        ttk.Button(buttons, text="Remove", command=self.remove).pack(fill="x")

        ratio_row = ttk.Frame(self.frame)
        ratio_row.grid(row=1, column=0, sticky=tk.W, pady=5)
        ttk.Label(ratio_row, text="Aspect ratio:").pack(side="left")
        ttk.Combobox(
            ratio_row,
            textvariable=self.ratio,
            values=[r.display for r in pipeline.RATIOS.values()],
            state="readonly",
            width=18,
        ).pack(side="left", padx=8)

        output_row = ttk.Frame(self.frame)
        output_row.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=5)
        output_row.columnconfigure(1, weight=1)
        ttk.Label(output_row, text="Output:").grid(row=0, column=0)
        ttk.Entry(output_row, textvariable=self.output_path).grid(
            row=0, column=1, sticky=(tk.W, tk.E), padx=5
        )
        ttk.Button(output_row, text="Browse", command=self.browse_output).grid(row=0, column=2)

        self.compose_btn = ttk.Button(self.frame, text="Compose", command=self.compose)
        self.compose_btn.grid(row=3, column=0, pady=10)

        ttk.Label(self.frame, textvariable=self.status).grid(row=4, column=0, sticky=tk.W)

        self.previews = PreviewPanes(self.frame, "Composite")
        self.previews.frame.grid(row=5, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=10)
        self.frame.rowconfigure(5, weight=1)

    def _refresh_list(self) -> None:
        self.listbox.delete(0, tk.END)
        for path in self.images:
            self.listbox.insert(tk.END, Path(path).name)
        self.status.set(
            f"{len(self.images)} image(s)"
            if self.can_compose()
            else "Add two or three images"
        )

    def _on_select(self, _event: object) -> None:
        selection = self.listbox.curselection()
        self._selection = int(selection[0]) if selection else None

    def add_image(self) -> None:
        if len(self.images) >= MAX_IMAGES:
            messagebox.showinfo("Limit", f"At most {MAX_IMAGES} images")
            return
        filename = filedialog.askopenfilename(
            title="Select Image",
            filetypes=[("Image files", "*.jpg *.jpeg *.JPG *.JPEG"), ("All files", "*.*")],
        )
        if not filename:
            return
        self.images.append(filename)
        if not self.output_path.get():
            self.output_path.set(str(Path(filename).with_suffix("")) + "_composite")
        self._refresh_list()

    def _swap(self, first: int, second: int) -> None:
        self.images[first], self.images[second] = self.images[second], self.images[first]

    def move_up(self) -> None:
        index = self._selection
        if index is None or index == 0:
            return
        self._swap(index, index - 1)
        self._selection = index - 1
        self._refresh_list()
        self.listbox.selection_set(self._selection)

    def move_down(self) -> None:
        index = self._selection
        if index is None or index >= len(self.images) - 1:
            return
        self._swap(index, index + 1)
        self._selection = index + 1
        self._refresh_list()
        self.listbox.selection_set(self._selection)

    def remove(self) -> None:
        index = self._selection
        if index is None or index >= len(self.images):
            return
        del self.images[index]
        self._selection = None
        self._refresh_list()

    def browse_output(self) -> None:
        folder = filedialog.askdirectory(title="Select Output Folder")
        if folder:
            self.output_path.set(str(Path(folder) / "composite"))

    def _finish(self, message: str, path: str | None, error: str | None) -> None:
        """Runs on the main thread. All widget mutation happens here."""
        self.status.set(message)
        try:
            if path is not None:
                self.previews.rebuild(["Composite"])
                with Image.open(path) as img:
                    self.previews.show_images([img.copy()])
        finally:
            self.compose_btn.config(state="normal")
        if error is not None:
            messagebox.showerror("Error", error)
        else:
            messagebox.showinfo("Success", message)

    def _run_compose(self, sources: list[str], prefix: str, ratio_name: str) -> None:
        try:
            result = pipeline.compose_images(sources, prefix, pipeline.RATIOS[ratio_name])
        except Exception as error:
            self.root.after(0, self._finish, "Failed", None, str(error))
            return
        self.root.after(
            0,
            self._finish,
            f"Wrote {result.path.name} using the {result.layout_name} layout",
            str(result.path),
            None,
        )

    def compose(self) -> None:
        if not self.can_compose():
            messagebox.showerror("Error", f"Select {MIN_IMAGES} or {MAX_IMAGES} images")
            return
        prefix = self.output_path.get()
        if not prefix:
            messagebox.showerror("Error", "Please choose an output prefix")
            return
        ratio_name = _RATIO_BY_DISPLAY.get(self.ratio.get(), pipeline.DEFAULT_RATIO.name)
        sources = list(self.images)
        self.compose_btn.config(state="disabled")
        self.status.set("Working...")
        threading.Thread(
            target=self._run_compose, args=(sources, prefix, ratio_name), daemon=True
        ).start()
```

- [ ] **Step 4: Wire the notebook**

Replace `src/maskingframe/gui/app.py` with:

```python
"""The application shell.

Owns the root window and the notebook; the tabs own everything inside
themselves.
"""

import tkinter as tk
from tkinter import ttk

from maskingframe.gui.compose_tab import ComposeTab
from maskingframe.gui.split_tab import PanoramaSplitterGUI


def run() -> None:
    root = tk.Tk()
    root.title("Panorama Splitter")
    root.geometry("900x700")
    root.columnconfigure(0, weight=1)
    root.rowconfigure(0, weight=1)

    notebook = ttk.Notebook(root)
    notebook.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

    split_page = ttk.Frame(notebook)
    split_page.columnconfigure(0, weight=1)
    split_page.rowconfigure(0, weight=1)
    PanoramaSplitterGUI(split_page)
    notebook.add(split_page, text="Split")

    compose = ComposeTab(notebook)
    notebook.add(compose.frame, text="Diptych / Triptych")

    root.mainloop()
```

- [ ] **Step 5: Run the tests**

Run: `mise run check`
Expected: green.

- [ ] **Step 6: Verify both tabs build under real Tk**

```bash
mise exec -- uv run python -c "
import tkinter
from tkinter import ttk
from maskingframe.gui.split_tab import PanoramaSplitterGUI
from maskingframe.gui.compose_tab import ComposeTab
root = tkinter.Tk(); root.withdraw()
notebook = ttk.Notebook(root)
page = ttk.Frame(notebook)
PanoramaSplitterGUI(page)
notebook.add(page, text='Split')
tab = ComposeTab(notebook)
notebook.add(tab.frame, text='Diptych / Triptych')
assert len(notebook.tabs()) == 2
print('both tabs build under a notebook')
root.destroy()
"
```

- [ ] **Step 7: End-to-end drive of the compose tab**

Build the GUI with a withdrawn root, set `tab.images` to two real fixtures, set `tab.output_path` to a temp prefix, call `tab.compose()`, then run `root.mainloop()` with a `root.after` timer that quits once the worker has finished. Assert the output file exists and that `tab.status.get()` names the chosen layout. Stub `messagebox.showinfo`/`showerror` in the driver script only — a real modal dialog blocks a headless run with nobody to click OK. Paste the output in your report.

- [ ] **Step 8: Commit**

```bash
git add src/maskingframe/gui tests/test_gui.py
git commit -m "feat(gui): add the diptych and triptych tab

The window becomes a notebook with the splitter on one tab and the
compositor on the other. The chosen arrangement is named in the status
line, so the automatic decision is visible rather than mysterious."
```

---

### Task 6: Documentation

**Files:**
- Modify: `README.md`, `CLAUDE.md`

**Interfaces:**
- Consumes: everything above
- Produces: accurate docs

- [ ] **Step 1: Try it on real photographs**

`samples/` holds 18 of the user's real scans (gitignored). Compose a few combinations at each ratio and record which layout wins:

```bash
mise exec -- uv run python -c "
from pathlib import Path
from maskingframe import pipeline
sets = [
    ['samples/horizons3-hp5-4.jpg', 'samples/horizons3-hp5-5.jpg'],
    ['samples/horizons3-hp5-4.jpg', 'samples/horizons3-hp5-5.jpg', 'samples/horizons3-hp5-6.jpg'],
    ['samples/DSCF6771.jpg', 'samples/horizons3-hp5-4.jpg'],
]
for images in sets:
    for name, ratio in pipeline.RATIOS.items():
        r = pipeline.compose_images(images, f'/tmp/compose/{len(images)}-{name.replace(\":\",\"-\")}', ratio)
        print(f'{len(images)} images at {name:>7}: {r.layout_name}')
"
```

Two 2.33:1 panoramas and three of them should choose the column at 4:5 and 1:1. The mixed portrait-plus-panorama set is the interesting one — record what it picks. Note that `DSCF6771.jpg` is portrait, which the splitter rejects but the compositor accepts; confirm it composes rather than erroring.

Record the actual results in your report. Do not adjust the docs to claim something the run did not produce.

- [ ] **Step 2: Update README.md**

Add a section after the aspect-ratio one:

```markdown
## Diptychs and triptychs

The second tab composes two or three photographs into a single frame at any
of the three ratios.

The layout is chosen for you. The tool tries each sensible arrangement — a
row, a column, and for three images the variants with one large panel beside
two stacked ones — and keeps whichever fills the frame best. Panels are never
cropped: each keeps its own aspect ratio, and whatever space is left over
becomes white border. That is what lets a 6x17 panorama, a square 6x6 and a
35mm frame sit in one composite without any of them losing content.

Images stay in the order you arrange them. Use Up and Down to change it.

Unlike the splitter, portrait images are fine here — mixing orientations is
much of the point.
```

Also update any part of the README that describes the GUI as a single screen.

- [ ] **Step 3: Update CLAUDE.md**

Add to the Architecture section:

- `layout.py` — pure arithmetic, no PIL and no I/O. Solves composite arrangements by expressing each node's width as an affine function of its height, then scoring candidates on frame fill. Never crops, never permutes input order.
- `compose.py` — PIL in, PIL out, like `geometry.py`. Renders solved boxes; refuses a box whose aspect disagrees with its image rather than distorting it.
- `gui/` is now a package: `app.py` (notebook shell), `split_tab.py`, `compose_tab.py`, `preview.py` (the shared pane grid). `gui/__init__.py` re-exports `run`, `PanoramaSplitterGUI` and `preview_titles`; `cli.gui_main` imports `run` from the package, so those names must keep working.

State the dependency direction explicitly: `geometry` and `layout` are leaves; `compose` uses both; `pipeline` uses all three; `cli` and `gui/` use only `pipeline`.

- [ ] **Step 4: Full verification from a clean state**

```bash
rm -rf .venv
mise run setup
mise run check
```

- [ ] **Step 5: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs: document the diptych and triptych tab

Records that the layout is solved automatically and that panels are never
cropped, which is what makes any mix of formats composable."
```

---

## Self-Review

**Spec coverage:**

| Spec requirement | Task |
| ---------------- | ---- |
| Layout tree, 2 and 6 candidates | 1 |
| Affine solve, bottom-up then top-down | 1 |
| Fill scoring, deterministic ties | 1 |
| Never crop | 1 (boxes), 2 (render refuses) |
| Order never permuted | 1 |
| Block centred | 1 |
| Render onto exact-size white canvas | 2 |
| Refuse distorting a panel | 2 |
| `compose_images`, `CompositeResult` | 3 |
| Diptych/triptych naming | 3 |
| 2 or 3 only; portrait accepted | 3 |
| Composite goldens | 3 |
| GUI package split | 4 |
| Shared preview widget | 4 |
| Notebook shell | 5 |
| Compose tab, reordering, ratio selector | 5 |
| Layout name visible in the UI | 5 |
| Threading invariant preserved | 5 |
| Docs | 6 |
| Real-photograph check | 6 |

**Placeholder scan:** one intentional gap — `COMPOSITE_GOLDEN_HASHES` in Task 3 Step 6 is filled from the generator command in that step, because hashes depend on the installed Pillow build.

**Type consistency:** `Box`, `Layout`, `Leaf`, `Row`, `Column`, `Node`, `candidates`, `evaluate`, `solve`, `GUTTER`, `render`, `CompositeResult`, `COMPOSITE_SUFFIXES`, `compose_images`, `PreviewPanes`, `ComposeTab` are spelled identically everywhere. `solve` takes `(aspects, ratio, padding, gutter=GUTTER)` in both its definition and all call sites. `evaluate` takes `(node, name, aspects, ratio, padding, gutter)` in its definition and in Task 1's `test_winning_candidate_fills_at_least_as_much_as_the_alternatives`.

**Risk note.** Task 4 is a pure move and is where a silent regression is most likely, because the preview extraction touches the widget code that has already produced two real bugs in this project. Its verification step is deliberately "same test count, no assertion weakened" rather than "tests pass".
