# Configurable Border Width and Colour Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user set the border width and colour on the padded panorama frame, and independently set the outer border and the inter-panel gutter (each with its own colour) on composites, from both the CLI and the GUI.

**Architecture:** A frozen `FrameStyle` dataclass in `geometry.py` replaces the three constants `SIDE_PADDING`, `GUTTER` and `BACKGROUND`. Widths are a percent of the frame's short side, resolved to pixels against an `AspectRatio`. The style is threaded through the call chain as a parameter with a default, never held as module state. `layout` learns to report the exact rectangles between panels so `compose` can paint them a second colour.

**Tech Stack:** Python 3, Pillow, PySide6, pytest, ruff, mypy --strict, uv, mise.

## Global Constraints

- `mise run check` (ruff lint, ruff format, mypy --strict, pytest) must pass before every commit. It is the single gate.
- Dependency direction is one-way and must not change: `geometry` and `layout` are leaves that import nothing else in the package; `compose` imports `geometry` and `layout`; `pipeline` imports all three; `cli` and `gui/` import `pipeline` only, never `geometry`, `layout` or `compose`.
- `pipeline` re-exports names specifically so `cli` and `gui` can stay off `geometry`. Add `FrameStyle` and `DEFAULT_STYLE` to those re-exports. Do not "simplify" them away.
- TDD: write the failing test, run it and see it fail, write the minimal code, run it and see it pass, commit. No production code without a test that demanded it.
- Conventional commits, imperative mood, one logical change per commit. No Claude attribution trailers — a pre-commit hook rejects them.
- British spelling in user-facing copy and in new identifiers: `colour`, not `color`. The CLI accepts `--border-color` and `--gutter-color` as hidden aliases only.
- Every new module-level and public function gets a docstring saying *why*, matching the existing house style in this repo.
- GUI: no rounded corners, no drop shadows, no animation. `CHINAGRAPH` is reserved for the primary action and errors; never use it for a new control. Every new control is keyboard reachable and carries an accessible name.
- Percent values are floats in the closed range 0.0 to 40.0. Colours are `#rrggbb` strings, normalised lowercase.
- Pixel rounding is half-up via `math.floor(v + 0.5)`, matching the rest of the codebase. Never use Python's `round()`, which is banker's rounding.

---

### Task 1: `FrameStyle` and colour parsing

**Files:**
- Modify: `src/maskingframe/geometry.py`
- Test: `tests/test_geometry.py`

**Interfaces:**
- Consumes: `geometry.AspectRatio`, `geometry.PORTRAIT`, `geometry.SQUARE`, `geometry.LANDSCAPE` (already exist).
- Produces:
  - `geometry.parse_colour(value: str) -> str` — normalises to lowercase `#rrggbb`, raises `ValueError`.
  - `geometry.FrameStyle` — frozen dataclass with fields `border_percent: float = 9.0`, `border_colour: str = "#ffffff"`, `gutter_percent: float = 4.0`, `gutter_colour: str = "#ffffff"`, `border_detail_frames: bool = False`; methods `border_px(ratio: AspectRatio) -> int` and `gutter_px(ratio: AspectRatio) -> int`.
  - `geometry.DEFAULT_STYLE: FrameStyle`.
  - `geometry.MAX_PERCENT: float = 40.0`.

This task only adds. `SIDE_PADDING`, `GUTTER` and `BACKGROUND` are still in place and still used; they are removed in Tasks 2, 4 and 5.

- [x] **Step 1: Write the failing tests**

Append to `tests/test_geometry.py`:

```python
import pytest

from maskingframe.geometry import DEFAULT_STYLE, FrameStyle, parse_colour


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
```

- [x] **Step 2: Run the tests and verify they fail**

Run: `uv run pytest tests/test_geometry.py -v`
Expected: FAIL, `ImportError: cannot import name 'DEFAULT_STYLE' from 'maskingframe.geometry'`.

- [x] **Step 3: Write the implementation**

Add to `src/maskingframe/geometry.py`, after the `RATIOS` / `DEFAULT_RATIO` block:

```python
import re

MAX_PERCENT = 40.0

_HEX = re.compile(r"\A#(?:[0-9a-f]{3}|[0-9a-f]{6})\Z")


def parse_colour(value: str) -> str:
    """Normalise a colour to lowercase `#rrggbb`.

    One parser, shared by `FrameStyle`, the CLI and the GUI's settings
    loader, so a colour is validated once at the boundary and can never
    reach PIL malformed. Accepts an optional leading `#` and the three-digit
    shorthand, because both are what people actually type.
    """
    text = str(value).strip().lower()
    if text and not text.startswith("#"):
        text = "#" + text
    if not _HEX.match(text):
        raise ValueError(f"invalid colour {value!r}: expected a hex colour like #ffffff")
    if len(text) == 4:
        text = "#" + "".join(character * 2 for character in text[1:])
    return text


def _check_percent(name: str, value: float) -> float:
    number = float(value)
    if not math.isfinite(number) or not 0.0 <= number <= MAX_PERCENT:
        raise ValueError(f"{name} percent must be between 0 and {MAX_PERCENT:g}, got {value!r}")
    return number


@dataclass(frozen=True)
class FrameStyle:
    """How much border to leave, and what colour to leave it.

    Widths are a percent of the frame's *short* side rather than absolute
    pixels, so one setting looks the same at 4:5 and at 1.91:1 -- a fixed
    100px border is a modest edge on a 1350px-tall frame and a heavy one on
    a 566px-tall frame. The style is always passed as an argument, never
    read from module state, so a batch run and a preview cannot disagree
    about it.
    """

    border_percent: float = 9.0
    border_colour: str = "#ffffff"
    gutter_percent: float = 4.0
    gutter_colour: str = "#ffffff"
    border_detail_frames: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "border_percent", _check_percent("border", self.border_percent))
        object.__setattr__(self, "gutter_percent", _check_percent("gutter", self.gutter_percent))
        object.__setattr__(self, "border_colour", parse_colour(self.border_colour))
        object.__setattr__(self, "gutter_colour", parse_colour(self.gutter_colour))

    def _resolve(self, percent: float, ratio: AspectRatio) -> int:
        return math.floor(percent / 100 * min(ratio.width, ratio.height) + 0.5)

    def border_px(self, ratio: AspectRatio) -> int:
        """The border, in output pixels, for this ratio."""
        return self._resolve(self.border_percent, ratio)

    def gutter_px(self, ratio: AspectRatio) -> int:
        """The gap between adjacent composite panels, in output pixels."""
        return self._resolve(self.gutter_percent, ratio)

    @property
    def border_rgb(self) -> tuple[int, int, int]:
        return _to_rgb(self.border_colour)

    @property
    def gutter_rgb(self) -> tuple[int, int, int]:
        return _to_rgb(self.gutter_colour)


def _to_rgb(colour: str) -> tuple[int, int, int]:
    return (int(colour[1:3], 16), int(colour[3:5], 16), int(colour[5:7], 16))


DEFAULT_STYLE = FrameStyle()
```

- [x] **Step 4: Run the tests and verify they pass**

Run: `uv run pytest tests/test_geometry.py -v`
Expected: PASS.

- [x] **Step 5: Run the full gate**

Run: `mise run check`
Expected: clean.

- [x] **Step 6: Commit**

```bash
git add src/maskingframe/geometry.py tests/test_geometry.py
git commit -m "feat(geometry): add FrameStyle, the border width and colour model

Widths are a percent of the frame's short side rather than absolute
pixels, so one setting reads the same at 4:5 and at 1.91:1. Nothing uses
it yet; the constants it replaces are removed as each caller moves over."
```

---

### Task 2: `make_padded_frame` takes a style

**Files:**
- Modify: `src/maskingframe/geometry.py:75-105`
- Test: `tests/test_geometry.py`

**Interfaces:**
- Consumes: `FrameStyle`, `DEFAULT_STYLE` from Task 1.
- Produces: `geometry.make_padded_frame(image, ratio, style: FrameStyle = DEFAULT_STYLE) -> Image.Image`. `geometry.SIDE_PADDING` and `geometry.BACKGROUND` are **deleted** in this task; `layout.py` and `compose.py` still reference them, so this task also updates those two call sites to pass `DEFAULT_STYLE`-derived values as a temporary bridge (Tasks 4 and 5 replace the bridge properly).

Bridge detail, so the tree keeps building: in `pipeline.py`, replace `geometry.SIDE_PADDING` with `geometry.DEFAULT_STYLE.border_px(ratio)` and `layout.GUTTER` stays as-is for now. In `compose.py`, replace `BACKGROUND` with `geometry.DEFAULT_STYLE.border_colour`.

- [x] **Step 1: Rewrite the existing padding tests against the percent contract**

In `tests/test_geometry.py`, replace every use of `geometry.SIDE_PADDING` with a style-derived value, and replace `geometry.BACKGROUND` with `geometry.DEFAULT_STYLE.border_colour`. The existing test bodies stay; only the expected margin changes:

```python
def test_padded_frame_border_matches_the_style() -> None:
    style = geometry.FrameStyle(border_percent=9.0)
    pano = Image.new("RGB", (2400, 1000), "black")
    for ratio in geometry.RATIOS.values():
        frame = geometry.make_padded_frame(pano, ratio, style)
        assert frame.size == (ratio.width, ratio.height)
        left, top, right, bottom = frame.getbbox()
        border = style.border_px(ratio)
        # Whichever axis binds gets exactly the border; the other gets more.
        bound_horizontally = abs(left - border) <= _BBOX_TOLERANCE
        bound_vertically = abs(top - border) <= _BBOX_TOLERANCE
        assert bound_horizontally or bound_vertically, ratio.name
        assert left >= border - _BBOX_TOLERANCE, ratio.name
        assert top >= border - _BBOX_TOLERANCE, ratio.name


def test_padded_frame_uses_the_border_colour() -> None:
    style = geometry.FrameStyle(border_percent=10.0, border_colour="#c9302a")
    pano = Image.new("RGB", (2400, 1000), "black")
    frame = geometry.make_padded_frame(pano, geometry.PORTRAIT, style)
    assert frame.getpixel((0, 0)) == (201, 48, 42)
    assert frame.getpixel((frame.width - 1, frame.height - 1)) == (201, 48, 42)


def test_padded_frame_defaults_to_white() -> None:
    pano = Image.new("RGB", (2400, 1000), "black")
    frame = geometry.make_padded_frame(pano, geometry.PORTRAIT)
    assert frame.getpixel((0, 0)) == (255, 255, 255)


def test_zero_border_fills_the_frame_edge_to_edge_on_the_binding_axis() -> None:
    style = geometry.FrameStyle(border_percent=0.0)
    pano = Image.new("RGB", (2400, 1000), "black")
    frame = geometry.make_padded_frame(pano, geometry.SQUARE, style)
    left, _top, right, _bottom = frame.getbbox()
    assert left == 0
    assert right == frame.width
```

- [x] **Step 2: Run the tests and verify they fail**

Run: `uv run pytest tests/test_geometry.py -v`
Expected: FAIL, `make_padded_frame() takes 2 positional arguments but 3 were given`.

- [x] **Step 3: Write the implementation**

Delete `SIDE_PADDING = 100` and `BACKGROUND = "white"` from `geometry.py`. Change the signature and body of `make_padded_frame`:

```python
def make_padded_frame(
    image: Image.Image,
    ratio: AspectRatio,
    style: FrameStyle = DEFAULT_STYLE,
) -> Image.Image:
    """Fit a panorama inside a canvas of the target ratio, inset by the style's border.

    The border describes the finished frame, in output pixels, on whichever
    axis binds -- not the source image. The panorama is scaled (preserving
    its own aspect ratio) to fit inside a box inset by that border on all
    four sides, then centred on the full-size canvas.

    For a normal wide panorama the width binds, so the left and right
    margins are exactly the border and the vertical gap is whatever is left
    over -- usually much larger. That asymmetry is inherent: the panorama's
    aspect ratio does not match the frame's, and frame 1 must show the whole
    panorama uncropped, so the border cannot be made even without cropping
    content away.

    Scaling straight to the fitted size (rather than compositing at source
    scale and downscaling) also avoids building a huge intermediate canvas,
    which matters on multi-hundred-megapixel scans.
    """
    border = style.border_px(ratio)
    pano_width, pano_height = image.size
    box_width = max(1, ratio.width - 2 * border)
    box_height = max(1, ratio.height - 2 * border)
    scale = min(box_width / pano_width, box_height / pano_height)
    fitted_width = max(1, math.floor(pano_width * scale + 0.5))
    fitted_height = max(1, math.floor(pano_height * scale + 0.5))

    fitted = image.resize((fitted_width, fitted_height), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (ratio.width, ratio.height), style.border_rgb)
    canvas.paste(fitted, ((ratio.width - fitted_width) // 2, (ratio.height - fitted_height) // 2))
    return canvas
```

Then fix the two bridge call sites so the tree still builds:
- `src/maskingframe/compose.py`: change the import to `from maskingframe.geometry import DEFAULT_STYLE, AspectRatio` and the canvas fill to `DEFAULT_STYLE.border_rgb`.
- `src/maskingframe/pipeline.py:226` and `:293`: change `geometry.SIDE_PADDING` to `geometry.DEFAULT_STYLE.border_px(ratio)`.
- `tests/test_compose.py:8` and `tests/test_layout.py:12`: change `PADDING = geometry.SIDE_PADDING` to `PADDING = geometry.DEFAULT_STYLE.border_px(geometry.PORTRAIT)`.

- [x] **Step 4: Run the tests and verify they pass**

Run: `uv run pytest -v`
Expected: PASS.

- [x] **Step 5: Run the full gate**

Run: `mise run check`

- [x] **Step 6: Commit**

```bash
git add -A
git commit -m "feat(geometry): pad the panorama frame from the style

Replaces the SIDE_PADDING and BACKGROUND constants. The border on a
landscape frame drops from 100px to 51px, which is the point: a percent
of the short side reads the same at every ratio."
```

---

### Task 3: Optional border on detail frames

**Files:**
- Modify: `src/maskingframe/geometry.py:121-147`
- Test: `tests/test_geometry.py`

**Interfaces:**
- Consumes: `FrameStyle`, `DEFAULT_STYLE`.
- Produces: `geometry.make_section(image, index, count, ratio, style: FrameStyle = DEFAULT_STYLE) -> Image.Image`.

- [x] **Step 1: Write the failing tests**

```python
def test_section_is_full_bleed_by_default() -> None:
    pano = Image.new("RGB", (3000, 1000), "black")
    frame = geometry.make_section(pano, 0, 3, geometry.PORTRAIT)
    assert frame.size == (geometry.PORTRAIT.width, geometry.PORTRAIT.height)
    assert frame.getpixel((0, 0)) == (0, 0, 0)


def test_section_gets_a_border_when_the_style_asks_for_one() -> None:
    style = geometry.FrameStyle(
        border_percent=10.0, border_colour="#c9302a", border_detail_frames=True
    )
    pano = Image.new("RGB", (3000, 1000), "black")
    ratio = geometry.PORTRAIT
    frame = geometry.make_section(pano, 0, 3, ratio, style)
    border = style.border_px(ratio)

    assert frame.size == (ratio.width, ratio.height)
    assert frame.getpixel((0, 0)) == (201, 48, 42)
    assert frame.getpixel((border - 1, ratio.height // 2)) == (201, 48, 42)
    assert frame.getpixel((border + 1, ratio.height // 2)) == (0, 0, 0)
    assert frame.getpixel((ratio.width - border, ratio.height // 2)) == (201, 48, 42)


def test_bordered_section_with_a_zero_border_is_full_bleed() -> None:
    style = geometry.FrameStyle(border_percent=0.0, border_detail_frames=True)
    pano = Image.new("RGB", (3000, 1000), "black")
    frame = geometry.make_section(pano, 0, 3, geometry.PORTRAIT, style)
    assert frame.getpixel((0, 0)) == (0, 0, 0)
```

- [x] **Step 2: Run the tests and verify they fail**

Run: `uv run pytest tests/test_geometry.py -k section -v`
Expected: FAIL, `make_section() takes 4 positional arguments but 5 were given`.

- [x] **Step 3: Write the implementation**

Replace `make_section` in `geometry.py`. The existing cover-and-centre-crop maths is unchanged; it now targets the inset box, and the result is pasted onto a filled canvas.

```python
def make_section(
    image: Image.Image,
    index: int,
    count: int,
    ratio: AspectRatio,
    style: FrameStyle = DEFAULT_STYLE,
) -> Image.Image:
    """Crop one detail frame and scale it to fill the target ratio.

    Scales by whichever axis keeps the target fully covered, then
    centre-crops the overflow.

    A detail frame is full-bleed by default: the border is what makes frame
    1 the establishing shot, and giving every frame one flattens that
    distinction. `style.border_detail_frames` turns it on for users who want
    the carousel to read as a single object, in which case the crop targets
    the inset box and the border is drawn around it.
    """
    border = style.border_px(ratio) if style.border_detail_frames else 0
    inner_width = max(1, ratio.width - 2 * border)
    inner_height = max(1, ratio.height - 2 * border)

    width, height = image.size
    start, end = section_bounds(width, index, count)
    crop = image.crop((start, 0, end, height))
    crop_width, crop_height = crop.size

    scale = max(inner_width / crop_width, inner_height / crop_height)
    # Half-up rounding of crop_dim * scale is what actually guarantees the
    # resized image covers the target on both axes. The max(inner_*, ...)
    # here is belt-and-braces, not load-bearing: it's a floor against any
    # future rounding change, not something exercised by current inputs.
    resized = crop.resize(
        (
            max(inner_width, math.floor(crop_width * scale + 0.5)),
            max(inner_height, math.floor(crop_height * scale + 0.5)),
        ),
        Image.Resampling.LANCZOS,
    )

    x_offset = (resized.width - inner_width) // 2
    y_offset = (resized.height - inner_height) // 2
    inner = resized.crop((x_offset, y_offset, x_offset + inner_width, y_offset + inner_height))
    if border == 0:
        return inner

    canvas = Image.new("RGB", (ratio.width, ratio.height), style.border_rgb)
    canvas.paste(inner, (border, border))
    return canvas
```

- [x] **Step 4: Run the tests and verify they pass**

Run: `uv run pytest -v`

- [x] **Step 5: Run the full gate**

Run: `mise run check`

- [x] **Step 6: Commit**

```bash
git add -A
git commit -m "feat(geometry): let detail frames carry a border

Off by default, because the border is what makes frame 1 the
establishing shot. On, the whole carousel reads as one object."
```

---

### Task 4: `layout` reports the gutter rectangles

**Files:**
- Modify: `src/maskingframe/layout.py`
- Test: `tests/test_layout.py`

**Interfaces:**
- Consumes: `geometry.AspectRatio`, `geometry.FrameStyle`, `geometry.DEFAULT_STYLE`.
- Produces:
  - `layout.Layout` gains a field `gutters: tuple[Box, ...]`, declared **after** `boxes` and **before** `score`, so positional construction in tests reads `Layout(name, boxes, gutters, score)`.
  - `layout.evaluate(node, name, aspects, ratio, style: FrameStyle) -> Layout | None` — the loose `padding: int` and `gutter: int` parameters are gone.
  - `layout.solve(aspects, ratio, style: FrameStyle = DEFAULT_STYLE) -> Layout`.
  - `layout.GUTTER` is **deleted**.

**Gutter geometry.** In a `Row` every child has exactly the parent's height, and in a `Column` every child has exactly the parent's width, so the gutter's cross-axis extent is the parent's own rounded extent. Along the gutter axis the rectangle runs from the end of one child's float extent to the start of the next, each rounded half-up — then inflated by 1px at each end. The inflation exists because a child's rounded edge can land one pixel away from the rounded gutter edge, and `compose` paints gutters *before* panels, so an overlap is covered by the panel while a shortfall would show as a hairline of the wrong colour between two panels. Cross-axis extent is **not** inflated, since bleeding there would put gutter colour into the outer border.

- [x] **Step 1: Write the failing tests**

Append to `tests/test_layout.py`:

```python
from maskingframe.geometry import DEFAULT_STYLE, FrameStyle

STYLE = FrameStyle(border_percent=9.0, gutter_percent=4.0)


def _touching_or_overlapping(a: layout.Box, b: layout.Box) -> bool:
    return not (
        a.x + a.width < b.x or b.x + b.width < a.x or a.y + a.height < b.y or b.y + b.height < a.y
    )


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


def test_gutters_stay_inside_the_border() -> None:
    ratio = geometry.PORTRAIT
    solved = layout.solve([1.5, 1.5, 1.5], ratio, STYLE)
    border = STYLE.border_px(ratio)
    for gutter in solved.gutters:
        assert gutter.x >= border
        assert gutter.y >= border
        assert gutter.x + gutter.width <= ratio.width - border
        assert gutter.y + gutter.height <= ratio.height - border


def test_gutter_width_tracks_the_style() -> None:
    ratio = geometry.PORTRAIT
    wide = layout.solve([1.5, 1.5], ratio, FrameStyle(gutter_percent=10.0))
    narrow = layout.solve([1.5, 1.5], ratio, FrameStyle(gutter_percent=1.0))
    assert wide.gutters[0].width > narrow.gutters[0].width or (
        wide.gutters[0].height > narrow.gutters[0].height
    )
```

Then update the three existing call sites in `tests/test_layout.py` (lines 133, 148, 171) from `layout.evaluate(node, name, aspects, ratio, PADDING, layout.GUTTER)` to `layout.evaluate(node, name, aspects, ratio, STYLE)`, and delete `test` line 138's `assert layout.GUTTER == 40` — replace it with:

```python
def test_default_gutter_is_four_percent() -> None:
    assert DEFAULT_STYLE.gutter_percent == 4.0
```

- [x] **Step 2: Run the tests and verify they fail**

Run: `uv run pytest tests/test_layout.py -v`
Expected: FAIL, `solve() takes 2 positional arguments but 3 were given` / `AttributeError: 'Layout' object has no attribute 'gutters'`.

- [x] **Step 3: Write the implementation**

In `src/maskingframe/layout.py`:

Delete `GUTTER = 40`. Change the import to `from maskingframe.geometry import DEFAULT_STYLE, AspectRatio, FrameStyle`.

Add the field:

```python
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
```

Change `_place` to also collect gutters. Add a `gutters: list[Box]` parameter after `out`, and in each branch record the separator:

```python
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
```

Change `evaluate` and `solve` to take a style:

```python
def evaluate(
    node: Node,
    name: str,
    aspects: Sequence[float],
    ratio: AspectRatio,
    style: FrameStyle,
) -> Layout | None:
    """Solve one candidate, or return None if it cannot fit sensibly."""
    padding = style.border_px(ratio)
    gutter = style.gutter_px(ratio)
    available_width = ratio.width - 2 * padding
    available_height = ratio.height - 2 * padding
    if available_width <= 0 or available_height <= 0:
        return None

    # `a` is a sum (or reciprocal-sum) of the leaves' aspects, so it is
    # positive as long as every aspect is positive and finite -- a
    # precondition `solve` enforces before calling here.
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


def solve(
    aspects: Sequence[float],
    ratio: AspectRatio,
    style: FrameStyle = DEFAULT_STYLE,
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
        solved = evaluate(node, name, aspects, ratio, style)
        if solved is None:
            continue
        if best is None or solved.score > best.score:
            best = solved
    if best is None:
        raise ValueError(f"no usable layout for aspects {list(aspects)} at {ratio.name}")
    return best
```

Finally update the two `layout.solve(...)` call sites in `pipeline.py` (lines 226 and 293) to `layout.solve(aspects, ratio, geometry.DEFAULT_STYLE)` as a bridge — Task 6 makes them take the caller's style.

- [x] **Step 4: Run the tests and verify they pass**

Run: `uv run pytest -v`

- [x] **Step 5: Run the full gate**

Run: `mise run check`

- [x] **Step 6: Commit**

```bash
git add -A
git commit -m "feat(layout): report the rectangles between panels

The renderer needs to paint the gutters a second colour, and the
arithmetic that produces them already exists in _place. Solving from a
FrameStyle also retires the GUTTER constant."
```

---

### Task 5: `compose` paints two colours

**Files:**
- Modify: `src/maskingframe/compose.py`
- Test: `tests/test_compose.py`

**Interfaces:**
- Consumes: `geometry.FrameStyle`, `geometry.DEFAULT_STYLE`, `layout.Layout.gutters`.
- Produces: `compose.render(images, solved, ratio, style: FrameStyle = DEFAULT_STYLE) -> Image.Image`.

- [x] **Step 1: Write the failing tests**

Append to `tests/test_compose.py`:

```python
from maskingframe.geometry import FrameStyle

TWO_TONE = FrameStyle(
    border_percent=9.0,
    border_colour="#000000",
    gutter_percent=4.0,
    gutter_colour="#c9302a",
)


def _rendered(style: FrameStyle) -> tuple[Image.Image, object]:
    images = [Image.new("RGB", (1500, 1000), "white"), Image.new("RGB", (1500, 1000), "white")]
    solved = layout.solve([1.5, 1.5], geometry.PORTRAIT, style)
    return compose.render(images, solved, geometry.PORTRAIT, style), solved


def test_outer_border_takes_the_border_colour() -> None:
    canvas, _solved = _rendered(TWO_TONE)
    assert canvas.getpixel((0, 0)) == (0, 0, 0)
    assert canvas.getpixel((canvas.width - 1, canvas.height - 1)) == (0, 0, 0)


def test_the_strip_between_panels_takes_the_gutter_colour() -> None:
    canvas, solved = _rendered(TWO_TONE)
    gutter = solved.gutters[0]
    centre = (gutter.x + gutter.width // 2, gutter.y + gutter.height // 2)
    assert canvas.getpixel(centre) == (201, 48, 42)


def test_no_border_colour_leaks_between_the_panels() -> None:
    canvas, solved = _rendered(TWO_TONE)
    first, second = solved.boxes
    # Walk the line joining the two panels; every pixel is panel or gutter,
    # never the outer colour.
    if first.x + first.width <= second.x:
        row = first.y + first.height // 2
        span = range(first.x + first.width, second.x)
        pixels = [canvas.getpixel((column, row)) for column in span]
    else:
        column = first.x + first.width // 2
        span = range(first.y + first.height, second.y)
        pixels = [canvas.getpixel((column, row)) for row in span]
    assert (0, 0, 0) not in pixels


def test_a_zero_gutter_paints_nothing_extra() -> None:
    style = FrameStyle(border_colour="#000000", gutter_percent=0.0, gutter_colour="#c9302a")
    canvas, solved = _rendered(style)
    assert solved.gutters == ()
    assert (201, 48, 42) not in canvas.getdata()


def test_render_still_refuses_a_mismatched_box() -> None:
    images = [Image.new("RGB", (1500, 1000), "white"), Image.new("RGB", (1000, 1500), "white")]
    solved = layout.solve([1.5, 1.5], geometry.PORTRAIT, TWO_TONE)
    with pytest.raises(ValueError, match="refusing to distort"):
        compose.render(images, solved, geometry.PORTRAIT, TWO_TONE)
```

- [x] **Step 2: Run the tests and verify they fail**

Run: `uv run pytest tests/test_compose.py -v`
Expected: FAIL, `render() takes 3 positional arguments but 4 were given`.

- [x] **Step 3: Write the implementation**

Replace `src/maskingframe/compose.py`'s import block and `render`:

```python
from maskingframe.geometry import DEFAULT_STYLE, AspectRatio, FrameStyle
from maskingframe.layout import Layout


def render(
    images: Sequence[Image.Image],
    solved: Layout,
    ratio: AspectRatio,
    style: FrameStyle = DEFAULT_STYLE,
) -> Image.Image:
    """Scale each image into its box and paste onto the styled canvas.

    Three passes, in this order: the whole canvas takes the border colour,
    the separator rectangles take the gutter colour, then the panels land on
    top. Painting the gutters first is what lets them be inflated by a pixel
    without showing -- the panels cover the overlap.
    """
    if len(images) != len(solved.boxes):
        raise ValueError(f"layout has {len(solved.boxes)} boxes for {len(images)} images")

    canvas = Image.new("RGB", (ratio.width, ratio.height), style.border_rgb)
    gutter = Image.new("RGB", (1, 1), style.gutter_rgb)
    for box in solved.gutters:
        canvas.paste(gutter.resize((box.width, box.height)), (box.x, box.y))

    for image, box in zip(images, solved.boxes, strict=True):
        # layout._place rounds width and height independently. For a given box.height,
        # the pre-rounded height could have been anywhere in [height-0.5, height+0.5).
        # This means box.width could legitimately be anywhere in the range of widths
        # that result from those heights, plus +-1px slack for rounding on width itself.
        aspect = image.width / image.height
        min_width = math.floor((box.height - 0.5) * aspect + 0.5) - 1
        max_width = math.floor((box.height + 0.5) * aspect + 0.5) + 1
        if not (min_width <= box.width <= max_width):
            raise ValueError(
                f"box aspect {box.width}x{box.height} does not match image "
                f"{image.width}x{image.height}; refusing to distort it"
            )
        panel = image.resize((box.width, box.height), Image.Resampling.LANCZOS)
        canvas.paste(panel, (box.x, box.y))
    return canvas
```

Note: a gutter box can extend one pixel outside the canvas after inflation at the block's outer edge. `Image.paste` clips silently, so no guard is needed — but the box is still recorded un-clipped, which is what the layout tests assert against.

If `test_gutters_stay_inside_the_border` from Task 4 fails because of that 1px inflation, relax that assertion to allow one pixel of slack rather than removing the inflation.

- [x] **Step 4: Run the tests and verify they pass**

Run: `uv run pytest -v`

- [x] **Step 5: Run the full gate**

Run: `mise run check`

- [x] **Step 6: Commit**

```bash
git add -A
git commit -m "feat(compose): paint the gutters and the border separately

Canvas, then separators, then panels. The order is what lets the
separators be inflated a pixel against rounding without ever showing."
```

---

### Task 6: Thread the style through `pipeline`

**Files:**
- Modify: `src/maskingframe/pipeline.py`
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: everything from Tasks 1-5.
- Produces:
  - `pipeline.FrameStyle`, `pipeline.DEFAULT_STYLE`, `pipeline.parse_colour` and `pipeline.MAX_PERCENT` re-exports. Tasks 7 and 9 both rely on `MAX_PERCENT` and run in parallel, so it must land here.
  - `process_image(input_path, output_prefix, ratio=DEFAULT_RATIO, on_frame=None, style: FrameStyle = DEFAULT_STYLE)`
  - `preview_frames(input_path, ratio=DEFAULT_RATIO, style: FrameStyle = DEFAULT_STYLE)`
  - `name_layout(input_paths, ratio=DEFAULT_RATIO, style: FrameStyle = DEFAULT_STYLE)`
  - `compose_preview(input_paths, ratio=DEFAULT_RATIO, style: FrameStyle = DEFAULT_STYLE)`
  - `compose_images(input_paths, output_prefix, ratio=DEFAULT_RATIO, style: FrameStyle = DEFAULT_STYLE)`
  - `process_folder(input_folder, output_folder, ratio=DEFAULT_RATIO, on_progress=None, style: FrameStyle = DEFAULT_STYLE)`

`style` goes **last** in every signature, so no existing positional call breaks.

- [x] **Step 1: Write the failing tests**

Append to `tests/test_pipeline.py`:

```python
RED_STYLE = pipeline.FrameStyle(border_percent=12.0, border_colour="#c9302a")


def test_process_image_honours_the_style(tmp_path: Path) -> None:
    written = pipeline.process_image(
        PANORAMA_FIXTURE, tmp_path / "out", pipeline.DEFAULT_RATIO, None, RED_STYLE
    )
    with Image.open(written[0]) as padded:
        assert padded.convert("RGB").getpixel((0, 0)) == (201, 48, 42)


def test_process_folder_honours_the_style(tmp_path: Path) -> None:
    result = pipeline.process_folder(
        FIXTURE_FOLDER, tmp_path, pipeline.DEFAULT_RATIO, None, RED_STYLE
    )
    assert result.written
    with Image.open(result.written[0]) as padded:
        assert padded.convert("RGB").getpixel((0, 0)) == (201, 48, 42)


def test_preview_frames_honours_the_style() -> None:
    frames = pipeline.preview_frames(PANORAMA_FIXTURE, pipeline.DEFAULT_RATIO, RED_STYLE)
    assert frames[0].getpixel((0, 0)) == (201, 48, 42)


def test_compose_images_honours_the_style(tmp_path: Path) -> None:
    style = pipeline.FrameStyle(border_colour="#000000", gutter_colour="#c9302a")
    result = pipeline.compose_images(
        COMPOSE_FIXTURES[:2], tmp_path / "out", pipeline.DEFAULT_RATIO, style
    )
    with Image.open(result.path) as composite:
        assert composite.convert("RGB").getpixel((0, 0)) == (0, 0, 0)


def test_compose_preview_and_compose_images_agree_under_a_style(tmp_path: Path) -> None:
    style = pipeline.FrameStyle(border_percent=15.0, gutter_percent=8.0)
    canvas, name = pipeline.compose_preview(COMPOSE_FIXTURES, pipeline.DEFAULT_RATIO, style)
    result = pipeline.compose_images(
        COMPOSE_FIXTURES, tmp_path / "out", pipeline.DEFAULT_RATIO, style
    )
    assert result.layout_name == name
    with Image.open(result.path) as written:
        assert written.size == canvas.size


def test_name_layout_honours_the_style() -> None:
    # A large gutter can change which arrangement wins; the name must follow
    # the style the caller actually rendered with.
    name = pipeline.name_layout(COMPOSE_FIXTURES, pipeline.DEFAULT_RATIO, RED_STYLE)
    solved_name = pipeline.compose_preview(COMPOSE_FIXTURES, pipeline.DEFAULT_RATIO, RED_STYLE)[1]
    assert name == solved_name


def test_style_is_re_exported() -> None:
    assert pipeline.FrameStyle is not None
    assert pipeline.DEFAULT_STYLE.border_percent == 9.0
```

If `PANORAMA_FIXTURE` / `FIXTURE_FOLDER` are named differently in the existing file, use the existing names — read the top of `tests/test_pipeline.py` first.

- [x] **Step 2: Run the tests and verify they fail**

Run: `uv run pytest tests/test_pipeline.py -v`
Expected: FAIL, `module 'maskingframe.pipeline' has no attribute 'FrameStyle'`.

- [x] **Step 3: Write the implementation**

In `src/maskingframe/pipeline.py`, extend the re-export block:

```python
# Re-exported so cli.py and gui/ can offer ratio and border selection
# without importing geometry directly -- they depend on pipeline only.
AspectRatio = geometry.AspectRatio
RATIOS = geometry.RATIOS
DEFAULT_RATIO = geometry.DEFAULT_RATIO
FrameStyle = geometry.FrameStyle
DEFAULT_STYLE = geometry.DEFAULT_STYLE
parse_colour = geometry.parse_colour
```

Then add `style: FrameStyle = DEFAULT_STYLE` as the final parameter of the six functions listed under **Interfaces**, and pass it down:
- `process_image`: `geometry.make_padded_frame(source, ratio, style)` and `geometry.make_section(source, index, count, ratio, style)`.
- `preview_frames`: the same two calls.
- `name_layout`: `layout.solve(aspects, ratio, style).name`.
- `compose_preview`: `layout.solve(aspects, ratio, style)` and `compose.render(images, solved, ratio, style)`.
- `compose_images`: `compose_preview(input_paths, ratio, style)`.
- `process_folder`: `process_image(source, prefix, ratio, None, style)`.

Add one line to each docstring saying the style is a parameter rather than module state so a preview and a run cannot disagree.

- [x] **Step 4: Run the tests and verify they pass**

Run: `uv run pytest -v`

- [x] **Step 5: Run the full gate**

Run: `mise run check`

- [x] **Step 6: Commit**

```bash
git add -A
git commit -m "feat(pipeline): thread the frame style through every entry point

A parameter with a default, last in each signature, so a batch run and a
preview cannot disagree about the border and no existing call breaks."
```

---

Tasks 7, 8 and 9 touch disjoint files and depend only on Task 6. They can be worked in parallel.

### Task 7: CLI flags

**Files:**
- Modify: `src/maskingframe/cli.py`
- Test: `tests/test_cli.py` (create if absent)

**Interfaces:**
- Consumes: `pipeline.FrameStyle`, `pipeline.DEFAULT_STYLE`, `pipeline.parse_colour`.
- Produces: `cli.build_parser()` gains `--border`, `--border-colour`/`--border-color`, `--gutter`, `--gutter-colour`/`--gutter-color`, `--border-detail-frames`; and `cli._style_from_args(args) -> pipeline.FrameStyle`.

- [x] **Step 1: Write the failing tests**

```python
import argparse

import pytest

from maskingframe import cli


def test_defaults_produce_the_default_style() -> None:
    args = cli.build_parser().parse_args(["in.jpg"])
    assert cli._style_from_args(args) == cli.pipeline.DEFAULT_STYLE


def test_flags_build_a_style() -> None:
    args = cli.build_parser().parse_args(
        [
            "in.jpg",
            "--border",
            "12",
            "--border-colour",
            "#000",
            "--gutter",
            "2.5",
            "--gutter-colour",
            "c9302a",
            "--border-detail-frames",
        ]
    )
    style = cli._style_from_args(args)
    assert style.border_percent == 12.0
    assert style.border_colour == "#000000"
    assert style.gutter_percent == 2.5
    assert style.gutter_colour == "#c9302a"
    assert style.border_detail_frames is True


def test_american_spellings_are_accepted() -> None:
    args = cli.build_parser().parse_args(["in.jpg", "--border-color", "#000000"])
    assert cli._style_from_args(args).border_colour == "#000000"


@pytest.mark.parametrize("flag", ["--border", "--gutter"])
@pytest.mark.parametrize("value", ["-1", "41", "banana"])
def test_out_of_range_widths_are_rejected(flag: str, value: str) -> None:
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["in.jpg", flag, value])


def test_bad_colour_is_rejected() -> None:
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["in.jpg", "--border-colour", "chartreuse"])


def test_main_reports_a_missing_input(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["nope.jpg"]) == 1
```

- [x] **Step 2: Run the tests and verify they fail**

Run: `uv run pytest tests/test_cli.py -v`
Expected: FAIL, `AttributeError: module 'maskingframe.cli' has no attribute '_style_from_args'`.

- [x] **Step 3: Write the implementation**

Add to `src/maskingframe/cli.py`, above `build_parser`:

```python
def _percent_type(value: str) -> float:
    """Resolve a --border or --gutter argument, as a percent of the short side.

    Validated here rather than at render time so a typo fails immediately
    with argparse's own clean, non-zero-exit message.
    """
    try:
        number = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid percent '{value}': expected a number") from None
    if not 0.0 <= number <= pipeline.geometry_max_percent():
        raise argparse.ArgumentTypeError(
            f"invalid percent '{value}': must be between 0 and "
            f"{pipeline.geometry_max_percent():g}"
        )
    return number


def _colour_type(value: str) -> str:
    try:
        return pipeline.parse_colour(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from None


def _style_from_args(args: argparse.Namespace) -> pipeline.FrameStyle:
    """Assemble the frame style the run should use."""
    return pipeline.FrameStyle(
        border_percent=args.border,
        border_colour=args.border_colour,
        gutter_percent=args.gutter,
        gutter_colour=args.gutter_colour,
        border_detail_frames=args.border_detail_frames,
    )
```

Correction, before you type it: `pipeline.geometry_max_percent()` does not exist. Task 6 re-exported `pipeline.MAX_PERCENT`; use that in both places above instead.

In `build_parser`, after the `--ratio` argument:

```python
    parser.add_argument(
        "--border",
        type=_percent_type,
        default=pipeline.DEFAULT_STYLE.border_percent,
        metavar="PERCENT",
        help=(
            "border width as a percent of the frame's short side "
            f"(default: {pipeline.DEFAULT_STYLE.border_percent:g})"
        ),
    )
    parser.add_argument(
        "--border-colour",
        "--border-color",
        dest="border_colour",
        type=_colour_type,
        default=pipeline.DEFAULT_STYLE.border_colour,
        metavar="HEX",
        help=f"border colour (default: {pipeline.DEFAULT_STYLE.border_colour})",
    )
    parser.add_argument(
        "--gutter",
        type=_percent_type,
        default=pipeline.DEFAULT_STYLE.gutter_percent,
        metavar="PERCENT",
        help=(
            "composites only: gap between panels, as a percent of the "
            f"frame's short side (default: {pipeline.DEFAULT_STYLE.gutter_percent:g})"
        ),
    )
    parser.add_argument(
        "--gutter-colour",
        "--gutter-color",
        dest="gutter_colour",
        type=_colour_type,
        default=pipeline.DEFAULT_STYLE.gutter_colour,
        metavar="HEX",
        help=f"composites only: colour of the gap between panels (default: {pipeline.DEFAULT_STYLE.gutter_colour})",
    )
    parser.add_argument(
        "--border-detail-frames",
        action="store_true",
        help="draw the border around the zoomed detail frames too, not just the whole-panorama frame",
    )
```

In `main`, build the style once and pass it to both branches:

```python
    style = _style_from_args(args)
    ...
            result = pipeline.process_folder(args.input, args.output, ratio, None, style)
    ...
            written = pipeline.process_image(args.input, args.output, ratio, None, style)
```

- [x] **Step 4: Run the tests and verify they pass**

Run: `uv run pytest -v`

- [x] **Step 5: Check the help reads well**

Run: `uv run maskingframe --help`
Expected: the five new flags appear, the American aliases are listed alongside their British spellings, and the gutter flags say "composites only".

- [x] **Step 6: Run the full gate and commit**

```bash
mise run check
git add -A
git commit -m "feat(cli): expose the border and gutter settings

Validated at parse time, so a typo fails with argparse's own message
instead of at render time. American spellings are accepted as aliases so
nobody has to guess."
```

---

### Task 8: Persist the style across GUI sessions

**Files:**
- Create: `src/maskingframe/gui/settings.py`
- Modify: `src/maskingframe/gui/app.py`
- Test: `tests/test_gui_settings.py`

**Interfaces:**
- Consumes: `pipeline.FrameStyle`, `pipeline.DEFAULT_STYLE`.
- Produces:
  - `settings.ORGANISATION: str = "maskingframe"`, `settings.APPLICATION: str = "Masking Frame"`
  - `settings.configure() -> None` — sets the QSettings organisation and application names. Called once from `run()`.
  - `settings.load_style(scope: str) -> pipeline.FrameStyle`
  - `settings.save_style(scope: str, style: pipeline.FrameStyle) -> None`
  - `settings.SPLIT: str = "split"`, `settings.COMPOSE: str = "compose"`

- [x] **Step 1: Write the failing tests**

`tests/test_gui_settings.py`:

```python
import pytest

from maskingframe import pipeline

pytest.importorskip("PySide6")

from PySide6.QtCore import QSettings  # noqa: E402

from maskingframe.gui import settings  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path, monkeypatch):
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(
        QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path)
    )
    settings.configure()
    yield


def test_missing_settings_fall_back_to_the_default() -> None:
    assert settings.load_style(settings.SPLIT) == pipeline.DEFAULT_STYLE


def test_a_style_round_trips() -> None:
    style = pipeline.FrameStyle(
        border_percent=12.5,
        border_colour="#c9302a",
        gutter_percent=1.0,
        gutter_colour="#000000",
        border_detail_frames=True,
    )
    settings.save_style(settings.SPLIT, style)
    assert settings.load_style(settings.SPLIT) == style


def test_the_two_scopes_are_independent() -> None:
    settings.save_style(settings.SPLIT, pipeline.FrameStyle(border_percent=20.0))
    assert settings.load_style(settings.COMPOSE) == pipeline.DEFAULT_STYLE


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("border_percent", "not-a-number"),
        ("border_percent", "999"),
        ("border_colour", "chartreuse"),
        ("gutter_percent", "-4"),
        ("gutter_colour", ""),
    ],
)
def test_a_corrupt_value_falls_back_to_the_default(key: str, value: str) -> None:
    store = QSettings()
    store.setValue(f"{settings.SPLIT}/{key}", value)
    store.sync()
    assert settings.load_style(settings.SPLIT) == pipeline.DEFAULT_STYLE
```

- [x] **Step 2: Run the tests and verify they fail**

Run: `uv run pytest tests/test_gui_settings.py -v`
Expected: FAIL, `ImportError: cannot import name 'settings'`.

- [x] **Step 3: Write the implementation**

`src/maskingframe/gui/settings.py`:

```python
"""Remembering the user's border choices between launches.

The only module in the GUI package that touches QSettings. A stored value
is untrusted input -- the file is plain text a user can edit, and it
outlives any release -- so every field is validated on read and the whole
style falls back to the default rather than failing the launch.
"""

from PySide6.QtCore import QSettings

from maskingframe import pipeline

ORGANISATION = "maskingframe"
APPLICATION = "Masking Frame"

# A split border and a compose border are different decisions, so they are
# stored separately rather than sharing one value that surprises whichever
# tab the user touches second.
SPLIT = "split"
COMPOSE = "compose"


def configure() -> None:
    """Name the settings store. Called once, from `run()`."""
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings().setValue("schema", 1)


def load_style(scope: str) -> pipeline.FrameStyle:
    """Read a stored style, or the default if anything about it is wrong."""
    store = QSettings(ORGANISATION, APPLICATION)
    try:
        return pipeline.FrameStyle(
            border_percent=float(
                store.value(f"{scope}/border_percent", pipeline.DEFAULT_STYLE.border_percent)
            ),
            border_colour=str(
                store.value(f"{scope}/border_colour", pipeline.DEFAULT_STYLE.border_colour)
            ),
            gutter_percent=float(
                store.value(f"{scope}/gutter_percent", pipeline.DEFAULT_STYLE.gutter_percent)
            ),
            gutter_colour=str(
                store.value(f"{scope}/gutter_colour", pipeline.DEFAULT_STYLE.gutter_colour)
            ),
            border_detail_frames=str(
                store.value(f"{scope}/border_detail_frames", "false")
            ).lower()
            in ("true", "1"),
        )
    except (TypeError, ValueError):
        return pipeline.DEFAULT_STYLE


def save_style(scope: str, style: pipeline.FrameStyle) -> None:
    """Store a style for this scope."""
    store = QSettings(ORGANISATION, APPLICATION)
    store.setValue(f"{scope}/border_percent", style.border_percent)
    store.setValue(f"{scope}/border_colour", style.border_colour)
    store.setValue(f"{scope}/gutter_percent", style.gutter_percent)
    store.setValue(f"{scope}/gutter_colour", style.gutter_colour)
    store.setValue(f"{scope}/border_detail_frames", style.border_detail_frames)
    store.sync()
```

If the test fixture's `QSettings()` (no arguments) and the module's `QSettings(ORGANISATION, APPLICATION)` end up pointing at different files, make the module use a single private helper `_store() -> QSettings` returning `QSettings(ORGANISATION, APPLICATION)` and have the fixture use the same constructor. Keep one construction site.

In `src/maskingframe/gui/app.py`, inside `run()`, call `settings.configure()` immediately after the `QApplication` is created and before `MainWindow` is constructed. Also set `app.setOrganizationName(settings.ORGANISATION)` and `app.setApplicationName(settings.APPLICATION)`.

- [x] **Step 4: Run the tests and verify they pass**

Run: `uv run pytest tests/test_gui_settings.py -v`

- [x] **Step 5: Run the full gate and commit**

```bash
mise run check
git add -A
git commit -m "feat(gui): remember the border settings between launches

A stored value is untrusted input -- the file is editable and outlives a
release -- so every field is validated on read and a bad one falls back
to the default rather than failing the launch."
```

---

### Task 9: The `Swatch` and `BorderControls` widgets

**Files:**
- Modify: `src/maskingframe/gui/shell.py`, `src/maskingframe/gui/theme.py`
- Test: `tests/test_gui_shell.py`

**Interfaces:**
- Consumes: `theme`, `pipeline.FrameStyle`, `pipeline.DEFAULT_STYLE`.
- Produces:
  - `shell.Swatch(QPushButton)` — `colour: str` property, `set_colour(value: str)`, signal `colour_changed = Signal(str)`, opens `QColorDialog` when activated.
  - `shell.BorderControls(QWidget)` — constructed as `BorderControls(show_gutter: bool, show_detail_toggle: bool, parent=None)`; signal `style_changed = Signal(object)` carrying a `pipeline.FrameStyle`; methods `style() -> pipeline.FrameStyle` and `set_style(style: pipeline.FrameStyle) -> None`.

`shell.py` currently imports nothing from `pipeline` and is described as presentation-only, "nothing here knows what a panorama is". A border width and colour are presentation, so this holds — but `BorderControls` does need the `FrameStyle` type. Import it from `pipeline`, not `geometry`, keeping the dependency rule.

- [x] **Step 1: Write the failing tests**

`tests/test_gui_shell.py`:

```python
import pytest

pytest.importorskip("PySide6")

from maskingframe import pipeline  # noqa: E402
from maskingframe.gui import shell  # noqa: E402


def test_swatch_reports_its_colour(qtbot) -> None:
    swatch = shell.Swatch("#c9302a")
    qtbot.addWidget(swatch)
    assert swatch.colour == "#c9302a"


def test_swatch_emits_on_change(qtbot) -> None:
    swatch = shell.Swatch("#ffffff")
    qtbot.addWidget(swatch)
    with qtbot.waitSignal(swatch.colour_changed) as blocker:
        swatch.set_colour("#000000")
    assert blocker.args == ["#000000"]


def test_swatch_does_not_emit_when_the_colour_is_unchanged(qtbot) -> None:
    swatch = shell.Swatch("#ffffff")
    qtbot.addWidget(swatch)
    with qtbot.assertNotEmitted(swatch.colour_changed):
        swatch.set_colour("#FFFFFF")


def test_swatch_names_its_colour_for_screen_readers(qtbot) -> None:
    swatch = shell.Swatch("#c9302a")
    qtbot.addWidget(swatch)
    assert "c9302a" in swatch.accessibleName().lower()


def test_swatch_is_keyboard_reachable(qtbot) -> None:
    swatch = shell.Swatch("#ffffff")
    qtbot.addWidget(swatch)
    assert swatch.focusPolicy() != shell.Qt.FocusPolicy.NoFocus


def test_border_controls_start_at_the_default(qtbot) -> None:
    controls = shell.BorderControls(show_gutter=True, show_detail_toggle=False)
    qtbot.addWidget(controls)
    assert controls.style() == pipeline.DEFAULT_STYLE


def test_border_controls_round_trip_a_style(qtbot) -> None:
    controls = shell.BorderControls(show_gutter=True, show_detail_toggle=True)
    qtbot.addWidget(controls)
    style = pipeline.FrameStyle(
        border_percent=12.5,
        border_colour="#c9302a",
        gutter_percent=1.0,
        gutter_colour="#000000",
        border_detail_frames=True,
    )
    controls.set_style(style)
    assert controls.style() == style


def test_border_controls_emit_when_a_field_changes(qtbot) -> None:
    controls = shell.BorderControls(show_gutter=False, show_detail_toggle=False)
    qtbot.addWidget(controls)
    with qtbot.waitSignal(controls.style_changed) as blocker:
        controls.border_spin.setValue(15.0)
    assert blocker.args[0].border_percent == 15.0


def test_set_style_does_not_re_emit(qtbot) -> None:
    controls = shell.BorderControls(show_gutter=False, show_detail_toggle=False)
    qtbot.addWidget(controls)
    with qtbot.assertNotEmitted(controls.style_changed):
        controls.set_style(pipeline.FrameStyle(border_percent=20.0))


def test_gutter_controls_are_hidden_when_not_wanted(qtbot) -> None:
    controls = shell.BorderControls(show_gutter=False, show_detail_toggle=False)
    qtbot.addWidget(controls)
    assert controls.gutter_spin is None
    assert controls.gutter_swatch is None
```

- [x] **Step 2: Run the tests and verify they fail**

Run: `uv run pytest tests/test_gui_shell.py -v`
Expected: FAIL, `AttributeError: module 'maskingframe.gui.shell' has no attribute 'Swatch'`.

- [x] **Step 3: Write the implementation**

Add to `src/maskingframe/gui/theme.py`'s `stylesheet()`, near the `QLineEdit` block:

```css
QDoubleSpinBox {
    background: WELL;
    border: 1px solid EDGE;
    padding: 4px 6px;
    color: INK;
}
QDoubleSpinBox:focus { border-color: INK; }
#Swatch { border: 1px solid EDGE; min-width: 34px; min-height: 24px; }
#Swatch:focus { border: 2px solid INK; }
```

Substitute the actual constants the existing stylesheet interpolation uses — read the surrounding rules and match their style exactly. Focus is `INK`, never `CHINAGRAPH`: a field turning red when you click into it reads as invalid.

Add to `src/maskingframe/gui/shell.py`:

```python
class Swatch(QPushButton):
    """A flat block of the current colour that opens a colour picker.

    A swatch alone would carry its meaning in colour only, so the button's
    accessible name states the hex value: the control still works for
    someone who cannot distinguish the fill, and for a screen reader.
    """

    colour_changed = Signal(str)

    def __init__(self, colour: str, label: str = "Colour", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Swatch")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._label = label
        self._colour = ""
        self.set_colour(colour, notify=False)
        self.clicked.connect(self._choose)

    @property
    def colour(self) -> str:
        return self._colour

    def set_colour(self, value: str, notify: bool = True) -> None:
        normalised = pipeline.parse_colour(value)
        if normalised == self._colour:
            return
        self._colour = normalised
        self.setStyleSheet(f"#Swatch {{ background: {normalised}; }}")
        self.setAccessibleName(f"{self._label} {normalised}")
        self.setToolTip(f"{self._label}: {normalised}")
        if notify:
            self.colour_changed.emit(normalised)

    def _choose(self) -> None:
        chosen = QColorDialog.getColor(theme.rgb(self._colour), self, f"Choose {self._label}")
        if chosen.isValid():
            self.set_colour(chosen.name())


class BorderControls(QWidget):
    """The border section of a rail.

    Both tabs need it, and both must present it identically -- switching
    tabs should not re-lay-out the window. Compose additionally sets the gap
    between panels; split additionally chooses whether the detail frames
    carry the border too. Everything is emitted as one whole FrameStyle, so
    a consumer never has to reassemble the fields itself.
    """

    style_changed = Signal(object)

    def __init__(
        self,
        show_gutter: bool,
        show_detail_toggle: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._quiet = False
        self.gutter_spin: QDoubleSpinBox | None = None
        self.gutter_swatch: Swatch | None = None
        self.detail_check: QCheckBox | None = None

        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)

        column.addWidget(section("Border"))
        column.addSpacing(theme.S)
        self.border_spin, self.border_swatch, border_row = self._field(
            "Border width", pipeline.DEFAULT_STYLE.border_percent, "Border colour",
            pipeline.DEFAULT_STYLE.border_colour,
        )
        column.addWidget(border_row)
        column.addSpacing(theme.S)
        column.addWidget(
            help_label("Percent of the frame's short side, so it reads the same at every ratio.")
        )

        if show_gutter:
            column.addSpacing(theme.M)
            self.gutter_spin, self.gutter_swatch, gutter_row = self._field(
                "Gap width", pipeline.DEFAULT_STYLE.gutter_percent, "Gap colour",
                pipeline.DEFAULT_STYLE.gutter_colour,
            )
            column.addWidget(gutter_row)
            column.addSpacing(theme.S)
            column.addWidget(help_label("The gap between the panels."))

        if show_detail_toggle:
            column.addSpacing(theme.M)
            self.detail_check = QCheckBox("Border the detail frames too")
            self.detail_check.toggled.connect(self._emit)
            column.addWidget(self.detail_check)

    def _field(
        self, spin_label: str, spin_value: float, swatch_label: str, swatch_value: str
    ) -> tuple[QDoubleSpinBox, Swatch, QWidget]:
        holder = QWidget(self)
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(theme.S)

        spin = QDoubleSpinBox()
        spin.setRange(0.0, pipeline.MAX_PERCENT)
        spin.setSingleStep(0.5)
        spin.setDecimals(1)
        spin.setSuffix(" %")
        spin.setValue(spin_value)
        spin.setAccessibleName(spin_label)
        spin.valueChanged.connect(self._emit)

        swatch = Swatch(swatch_value, swatch_label)
        swatch.colour_changed.connect(self._emit)

        row.addWidget(spin, 1)
        row.addWidget(swatch)
        return spin, swatch, holder

    def style(self) -> pipeline.FrameStyle:
        return pipeline.FrameStyle(
            border_percent=self.border_spin.value(),
            border_colour=self.border_swatch.colour,
            gutter_percent=(
                self.gutter_spin.value()
                if self.gutter_spin is not None
                else pipeline.DEFAULT_STYLE.gutter_percent
            ),
            gutter_colour=(
                self.gutter_swatch.colour
                if self.gutter_swatch is not None
                else pipeline.DEFAULT_STYLE.gutter_colour
            ),
            border_detail_frames=(
                self.detail_check.isChecked() if self.detail_check is not None else False
            ),
        )

    def set_style(self, style: pipeline.FrameStyle) -> None:
        """Adopt a style without announcing it -- for restoring stored state."""
        self._quiet = True
        try:
            self.border_spin.setValue(style.border_percent)
            self.border_swatch.set_colour(style.border_colour)
            if self.gutter_spin is not None:
                self.gutter_spin.setValue(style.gutter_percent)
            if self.gutter_swatch is not None:
                self.gutter_swatch.set_colour(style.gutter_colour)
            if self.detail_check is not None:
                self.detail_check.setChecked(style.border_detail_frames)
        finally:
            self._quiet = False

    def _emit(self, *_args: object) -> None:
        if self._quiet:
            return
        self.style_changed.emit(self.style())
```

Extend `shell.py`'s imports with `Signal` from `PySide6.QtCore`, and `QCheckBox`, `QColorDialog`, `QDoubleSpinBox` from `PySide6.QtWidgets`, plus `from maskingframe import pipeline`.

Update the module docstring: it currently says "Nothing here knows what a panorama is." That is still true — add a sentence noting that `pipeline` is imported for the `FrameStyle` type and the colour parser only, never for image work.

- [x] **Step 4: Run the tests and verify they pass**

Run: `uv run pytest tests/test_gui_shell.py -v`

- [x] **Step 5: Run the full gate and commit**

```bash
mise run check
git add -A
git commit -m "feat(gui): add the border controls both rails need

One widget, emitting a whole FrameStyle, so neither tab has to reassemble
the fields. The swatch states its hex value in its accessible name, so
the control does not carry its meaning in colour alone."
```

---

Tasks 10 and 11 touch disjoint files and both depend on Tasks 6, 8 and 9. They can be worked in parallel.

### Task 10: Wire the split tab

**Files:**
- Modify: `src/maskingframe/gui/split_tab.py`
- Test: `tests/test_gui_split_tab.py` (create if absent; follow whatever the existing GUI tests do for fixtures)

**Interfaces:**
- Consumes: `shell.BorderControls`, `settings.load_style`, `settings.save_style`, `settings.SPLIT`, `pipeline.process_image`, `pipeline.process_folder`, `pipeline.preview_frames`.
- Produces: `SplitTab.border_controls: shell.BorderControls` and `SplitTab._style() -> pipeline.FrameStyle`.

- [x] **Step 1: Write the failing tests**

```python
def test_split_tab_restores_the_stored_style(qtbot, isolated_settings) -> None:
    settings.save_style(settings.SPLIT, pipeline.FrameStyle(border_percent=17.0))
    tab = split_tab.SplitTab()
    qtbot.addWidget(tab)
    assert tab._style().border_percent == 17.0


def test_split_tab_stores_a_changed_style(qtbot, isolated_settings) -> None:
    tab = split_tab.SplitTab()
    qtbot.addWidget(tab)
    tab.border_controls.border_spin.setValue(21.0)
    assert settings.load_style(settings.SPLIT).border_percent == 21.0


def test_split_tab_offers_the_detail_frame_toggle(qtbot, isolated_settings) -> None:
    tab = split_tab.SplitTab()
    qtbot.addWidget(tab)
    assert tab.border_controls.detail_check is not None
    assert tab.border_controls.gutter_spin is None
```

Put the `isolated_settings` fixture in `tests/conftest.py` (create if absent), reusing the body written for Task 8's `_isolated_settings` so both suites share one definition.

- [x] **Step 2: Run the tests and verify they fail**

Run: `uv run pytest tests/test_gui_split_tab.py -v`
Expected: FAIL, `AttributeError: 'SplitTab' object has no attribute 'border_controls'`.

- [x] **Step 3: Write the implementation**

In `split_tab.py`'s `_build`, immediately after the `count_label` block and before the `Destination` section:

```python
        rail.addSpacing(theme.L)
        self.border_controls = shell.BorderControls(show_gutter=False, show_detail_toggle=True)
        self.border_controls.set_style(settings.load_style(settings.SPLIT))
        self.border_controls.style_changed.connect(self._on_style_changed)
        rail.addWidget(self.border_controls)
```

Add the methods:

```python
    def _style(self) -> pipeline.FrameStyle:
        return self.border_controls.style()

    def _on_style_changed(self, style: pipeline.FrameStyle) -> None:
        """Persist the choice and invalidate anything on screen that predates it."""
        settings.save_style(settings.SPLIT, style)
```

Then pass `self._style()` through every pipeline call in this file, reading it on the GUI thread and closing over the value — never inside the worker, for the same reason the ratio is read up front today:

- in `_start_single`'s `cut()`: `pipeline.process_image(source, prefix, ratio, on_frame, style)` where `style` is captured before `work.submit`.
- in `_start_batch`'s `cut()`: `pipeline.process_folder(source, destination, ratio, on_progress, style)`.
- in `preview`'s `render()`: `pipeline.preview_frames(source, ratio, style)`.

Read the existing `_ratio_name()` / `ratio_name` pattern in each of those three methods and mirror it exactly: capture the style into a local before `work.submit`, then use the local inside the job.

Add `from maskingframe.gui import settings` to the imports.

- [x] **Step 4: Run the tests and verify they pass**

Run: `uv run pytest -v`

- [ ] **Step 5: Look at it** (not run: the GUI was not launched in this session)

Run: `mise run gui`
Check: the Border section sits between FORMAT and DESTINATION; tabbing reaches the spin box, the swatch and the checkbox in that order; the swatch opens a picker and the rail updates; setting the border to 25% and previewing shows a visibly thicker border.

- [x] **Step 6: Run the full gate and commit**

```bash
mise run check
git add -A
git commit -m "feat(gui): let the split tab set the border

The style is read on the GUI thread and captured before the job starts,
the same way the ratio already is -- a worker re-reading a control could
render one setting and caption it with another."
```

---

### Task 11: Wire the compose tab

**Files:**
- Modify: `src/maskingframe/gui/compose_tab.py`
- Test: `tests/test_gui_compose_tab.py` (create if absent)

**Interfaces:**
- Consumes: `shell.BorderControls`, `settings.load_style`, `settings.save_style`, `settings.COMPOSE`, `pipeline.compose_images`, `pipeline.compose_preview`, `pipeline.name_layout`.
- Produces: `ComposeTab.border_controls: shell.BorderControls` and `ComposeTab._style() -> pipeline.FrameStyle`.

- [x] **Step 1: Write the failing tests**

```python
def test_compose_tab_restores_the_stored_style(qtbot, isolated_settings) -> None:
    settings.save_style(settings.COMPOSE, pipeline.FrameStyle(gutter_percent=7.0))
    tab = compose_tab.ComposeTab()
    qtbot.addWidget(tab)
    assert tab._style().gutter_percent == 7.0


def test_compose_tab_stores_a_changed_style(qtbot, isolated_settings) -> None:
    tab = compose_tab.ComposeTab()
    qtbot.addWidget(tab)
    tab.border_controls.gutter_spin.setValue(3.0)
    assert settings.load_style(settings.COMPOSE).gutter_percent == 3.0


def test_compose_tab_offers_gutter_controls_but_no_detail_toggle(qtbot, isolated_settings) -> None:
    tab = compose_tab.ComposeTab()
    qtbot.addWidget(tab)
    assert tab.border_controls.gutter_spin is not None
    assert tab.border_controls.gutter_swatch is not None
    assert tab.border_controls.detail_check is None


def test_the_two_tabs_keep_separate_styles(qtbot, isolated_settings) -> None:
    settings.save_style(settings.SPLIT, pipeline.FrameStyle(border_percent=30.0))
    tab = compose_tab.ComposeTab()
    qtbot.addWidget(tab)
    assert tab._style().border_percent == pipeline.DEFAULT_STYLE.border_percent
```

- [x] **Step 2: Run the tests and verify they fail**

Run: `uv run pytest tests/test_gui_compose_tab.py -v`
Expected: FAIL, `AttributeError: 'ComposeTab' object has no attribute 'border_controls'`.

- [x] **Step 3: Write the implementation**

Read `compose_tab.py`'s `_build` first and find where the FORMAT section ends and DESTINATION begins — both rails carry the same sections in the same order, so the border section goes in the same relative position as Task 10 put it. Insert:

```python
        rail.addSpacing(theme.L)
        self.border_controls = shell.BorderControls(show_gutter=True, show_detail_toggle=False)
        self.border_controls.set_style(settings.load_style(settings.COMPOSE))
        self.border_controls.style_changed.connect(self._on_style_changed)
        rail.addWidget(self.border_controls)
```

Add:

```python
    def _style(self) -> pipeline.FrameStyle:
        return self.border_controls.style()

    def _on_style_changed(self, style: pipeline.FrameStyle) -> None:
        """Persist the choice and re-solve, since the gutter can change which
        arrangement wins."""
        settings.save_style(settings.COMPOSE, style)
        self._refresh_layout_name()
```

The method that refreshes the arrangement name already exists: it is `_request_layout_name()` at `compose_tab.py:449`, which calls `pipeline.name_layout` off the GUI thread behind a staleness token and hands the answer to `_apply_layout_name()` at `:480`. Call that, not a second path:

```python
    def _on_style_changed(self, style: pipeline.FrameStyle) -> None:
        """Persist the choice and re-solve: the gap can change which
        arrangement wins, so the name in the rail would otherwise be
        describing the previous solution."""
        settings.save_style(settings.COMPOSE, style)
        self._request_layout_name()
```

The `pipeline.name_layout` call inside `_request_layout_name` is at `compose_tab.py:183`; capture the style into a local there, beside the existing `ratio_name` capture, and pass it as the third argument.

Pass `self._style()` through `pipeline.compose_images`, `pipeline.compose_preview` and `pipeline.name_layout`, capturing the style into a local on the GUI thread before `work.submit` in every case, matching the existing ratio-capture pattern. The staleness token already in this file must cover the style too: if a style change and a source change race, the newer token wins, unchanged.

Add `from maskingframe.gui import settings` to the imports.

- [x] **Step 4: Run the tests and verify they pass**

Run: `uv run pytest -v`

- [ ] **Step 5: Look at it** (not run: the GUI was not launched in this session)

Run: `mise run gui`
Check: on the Compose tab the Border section carries four controls and no detail-frames checkbox, in the same position as on Split; setting the gap colour to red and previewing a diptych shows a red strip between the two panels and white around the outside; setting the gap to 0% removes the strip entirely; a large gap can change the arrangement name in the rail, and the name under the preview agrees with it.

- [x] **Step 6: Run the full gate and commit**

```bash
mise run check
git add -A
git commit -m "feat(gui): let the compose tab set the border and the gap

The gap can change which arrangement wins, so a style change re-solves
the name in the rail rather than leaving it describing the old solution."
```

---

### Task 12: Update the project documentation

**Files:**
- Modify: `CLAUDE.md`
- Modify: `README.md` if one exists

- [x] **Step 1: Rewrite the stale passages in `CLAUDE.md`**

The following statements are now wrong and must be corrected:

- The `geometry.py` bullet lists `make_padded_frame()` and `make_section()` but not `FrameStyle`, `parse_colour`, `DEFAULT_STYLE` or `MAX_PERCENT`. Add them and say the style is the border model.
- The `layout.py` bullet must mention that a solved layout now reports the rectangles between panels.
- The `pipeline.py` bullet lists the re-exports; add `FrameStyle`, `DEFAULT_STYLE`, `parse_colour` and `MAX_PERCENT`, and repeat the existing warning that they must not be "simplified" away.
- The `gui/` bullet must list `settings.py` and describe `BorderControls` and `Swatch` as part of `shell.py`.
- The whole "Padding behaviour worth knowing" section names `SIDE_PADDING (100px)`, which no longer exists. Rewrite it around `FrameStyle.border_px()`: 9% of the short side by default, the binding-axis asymmetry unchanged, and the note that a landscape frame's default border is now 51px rather than 100px.
- Add a short section describing the two colours on a composite: the gutter colour fills only the strips between panels; the outer border and the centring slack take the border colour.
- The "Behaviour changes" list should gain an entry saying the border and gutter are now settings rather than constants, and that the default landscape border changed.

- [x] **Step 2: Verify every claim in what you wrote**

For each statement you added or edited, open the file it describes and confirm it is true. Do not carry over a description from the old text without checking it.

- [x] **Step 3: Run the full gate and commit**

```bash
mise run check
git add -A
git commit -m "docs: describe the border settings

CLAUDE.md still named SIDE_PADDING and a fixed 100px border, neither of
which exists now."
```

---

## Verification

After Task 12, before declaring the work done:

- [x] `mise run check` passes.
- [x] `uv run maskingframe --help` lists all five new flags.
- [x] A CLI run with `--border 20 --border-colour '#c9302a'` produces a visibly red-bordered frame 1.
- [x] `uv run maskingframe compose --help` lists the same five flags, since both parsers are built from `_add_style_arguments()`.
- [x] A CLI compose run with `--gutter-colour '#000000'` produces a black strip between the panels. Covered by `test_compose_gutter_colour_reaches_the_written_pixels` in `tests/test_cli.py`.
- [x] `mise run gui` launches, both tabs show the Border section in the same position, settings survive a quit and relaunch, and every new control is reachable by keyboard alone. The user has since looked at it and is happy with it.
- [x] `git log --oneline` shows one commit per task, each of which builds and passes on its own.

## Known gap, and how it was closed

As written, this plan left `--gutter` and `--gutter-colour` as dead flags. The gutter only exists on a composite, and the CLI only split panoramas -- there was no `compose` subcommand, so the two flags parsed, validated and built a `FrameStyle` whose gutter fields then reached no output file. That was a hole in the plan rather than in the implementation: it asked for "full parity with the GUI" without noticing the CLI had no compose path to reach parity on.

It has since been closed by adding the subcommand rather than dropping the flags. `maskingframe compose a.jpg b.jpg -o out` writes a diptych or triptych, and both parsers take their ratio and framing flags from one `_add_style_arguments()` definition, so the two commands cannot drift apart. `main()` dispatches on the literal first word instead of an argparse subparser, which is what keeps the bare `maskingframe pano.jpg out` form untouched. The gutter flags now reach real pixels; `tests/test_cli.py` asserts that.

One flag is still inert on one command, and deliberately so: `--border-detail-frames` does nothing on `compose`, because a composite has no detail frames. Its help text says which command it applies to, in the same phrasing the gutter flags use.
