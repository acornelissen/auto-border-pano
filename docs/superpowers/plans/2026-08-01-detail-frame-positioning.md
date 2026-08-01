# Detail Frame Positioning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user place each detail frame along a panorama by hand in the GUI, with every frame becoming a full-height crop at exactly the output aspect ratio.

**Architecture:** A detail frame stops being "slice `i` of `count`" and becomes a single number — its left edge as a fraction of the panorama's width — with its width derived from `pano_height * ratio`. `geometry` gains the pure arithmetic for that (derivation, clamping, ordering, defaults, add/remove); `pipeline` threads an optional positions tuple through the two functions that cut frames; the GUI gains a ribbon widget above the contact strip plus horizontal dragging inside a strip frame, both writing to one tuple owned by the Split tab.

**Tech Stack:** Python 3.13, Pillow, PySide6 (Qt), pytest + pytest-qt, mypy --strict, ruff, mise + uv.

## Global Constraints

- Dependency direction is one-way and must not be broken: `geometry` and `layout` are leaves; `compose` uses both; `pipeline` uses all three; `cli` and `gui/` use **only** `pipeline`. A GUI module must never `import geometry`.
- `gui/strip.py`, `gui/ribbon.py` and `gui/theme.py` are presentation only. They take plain data (floats, ints, strings, PIL images) and must never learn what a `FrameStyle` or an `AspectRatio` is.
- `style` stays the **last** parameter of every `pipeline` entry point that takes one, and every new parameter has a default so no existing positional call breaks.
- Round half-up with `math.floor(v + 0.5)`. Never Python's `round()` — it is banker's rounding.
- Concurrency rule: a job returns plain data and the callback runs on the GUI thread via `work.submit`. Never touch a widget inside a job. Background answers carry a monotonic staleness token, and whatever the job was computed *for* travels back with its result.
- No rounded corners, no drop shadows, no animation. `theme.CHINAGRAPH` is for marking up only — numbering, selection, primary action, errors. Chrome stays greyscale.
- Verification command for every task: `mise run check` (runs `lint`, `fmtcheck`, `typecheck`, `test`). It must pass before a commit.
- Commit messages are conventional commits in imperative mood, plain English. No Claude attribution trailers — the pre-commit hook rejects them.
- Run single tests with `mise exec -- uv run pytest <path> -v`.

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `src/maskingframe/geometry.py` | Pure transforms; now also the position model | Modify |
| `src/maskingframe/pipeline.py` | The only filesystem module; threads positions through | Modify |
| `src/maskingframe/gui/ribbon.py` | The panorama overview with draggable windows | Create |
| `src/maskingframe/gui/strip.py` | Contact strip; gains in-frame horizontal drag | Modify |
| `src/maskingframe/gui/split_tab.py` | Owns the positions tuple, wires both views | Modify |
| `tests/test_geometry.py` | Position arithmetic | Modify |
| `tests/test_pipeline.py` | Positions honoured on disk; golden hashes | Modify |
| `tests/test_preview_frames.py` | Positions honoured in memory | Modify |
| `tests/test_ribbon.py` | The ribbon widget | Create |
| `tests/test_strip.py` | In-frame drag | Modify |
| `tests/test_split_tab.py` | Wiring, folder mode | Modify |
| `CLAUDE.md` | Architecture notes and behaviour-changes list | Modify |

**Task order:** 1 → 2 → 3 → 4 → then 5 and 6 in parallel → 7 → 8.

---

### Task 1: The position model in `geometry`

Pure arithmetic only. Nothing existing changes yet, so the suite stays green throughout.

**Files:**
- Modify: `src/maskingframe/geometry.py`
- Test: `tests/test_geometry.py`

**Interfaces:**
- Consumes: `AspectRatio` (has `.width`, `.height`, `.value`), `MIN_SECTIONS = 2`, `section_count(pano_width, pano_height, ratio) -> int` — all already in `geometry.py`.
- Produces:
  - `frame_width(pano_height: int, ratio: AspectRatio) -> int`
  - `position_travel(pano_width: int, pano_height: int, ratio: AspectRatio) -> float`
  - `clamp_position(position: float, pano_width: int, pano_height: int, ratio: AspectRatio) -> float`
  - `normalise_positions(positions: Sequence[float], pano_width: int, pano_height: int, ratio: AspectRatio) -> tuple[float, ...]`
  - `default_positions(pano_width: int, pano_height: int, ratio: AspectRatio, count: int | None = None) -> tuple[float, ...]`

- [x] **Step 1: Write the failing tests**

Add to the end of `tests/test_geometry.py`:

```python
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
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `mise exec -- uv run pytest tests/test_geometry.py -k "frame_width or travel or clamp or normalise or default_positions" -v`
Expected: FAIL with `AttributeError: module 'maskingframe.geometry' has no attribute 'frame_width'`.

- [x] **Step 3: Implement**

Add `from collections.abc import Sequence` to the imports at the top of `geometry.py`, then add this block immediately after `section_count()`:

```python
def frame_width(pano_height: int, ratio: AspectRatio) -> int:
    """How wide one detail frame's crop is, in source pixels.

    A detail frame is a full-height crop at exactly the output aspect
    ratio, so nothing vertical is ever thrown away. The width deliberately
    does not depend on how many frames there are: once the frames are
    placed by hand, adding a sixth must not re-cut the first five.
    """
    return max(1, math.floor(pano_height * ratio.value + 0.5))


def position_travel(pano_width: int, pano_height: int, ratio: AspectRatio) -> float:
    """How far a frame's left edge may move, as a fraction of the width.

    Zero when the source is narrower than a single frame -- a 1.5:1 image
    at 1.91:1 -- in which case every frame is the whole width and there is
    nothing to choose. Degenerate, but it must not raise.
    """
    return max(0.0, 1.0 - frame_width(pano_height, ratio) / pano_width)


def clamp_position(
    position: float, pano_width: int, pano_height: int, ratio: AspectRatio
) -> float:
    """Hold one position inside the travel, so no frame hangs off an edge."""
    return min(max(position, 0.0), position_travel(pano_width, pano_height, ratio))


def normalise_positions(
    positions: Sequence[float], pano_width: int, pano_height: int, ratio: AspectRatio
) -> tuple[float, ...]:
    """Clamp every position and hold the tuple ascending.

    Ascending, not sorted: a frame dragged past its neighbour stops at the
    neighbour rather than swapping with it. Sorting would renumber the
    carousel under the user's hand. Overlap is allowed -- two tight crops
    on one subject is a legitimate choice -- so this is a running maximum,
    not a minimum separation.
    """
    running = 0.0
    result: list[float] = []
    for position in positions:
        running = max(running, clamp_position(position, pano_width, pano_height, ratio))
        result.append(running)
    return tuple(result)


def default_positions(
    pano_width: int,
    pano_height: int,
    ratio: AspectRatio,
    count: int | None = None,
) -> tuple[float, ...]:
    """Evenly spaced frames: the first flush left, the last flush right.

    The count defaults to `section_count`, which is still the right first
    guess -- how many exact tiles fit across the panorama -- but it is only
    an opening position now, not a constraint.
    """
    if count is None:
        count = section_count(pano_width, pano_height, ratio)
    count = max(1, count)
    travel = position_travel(pano_width, pano_height, ratio)
    if count == 1:
        return (0.0,)
    return tuple(index * travel / (count - 1) for index in range(count))
```

- [x] **Step 4: Run the tests to verify they pass**

Run: `mise exec -- uv run pytest tests/test_geometry.py -v`
Expected: PASS, all of them.

- [x] **Step 5: Run the full gate**

Run: `mise run check`
Expected: PASS.

- [x] **Step 6: Commit**

```bash
git add src/maskingframe/geometry.py tests/test_geometry.py
git commit -m "feat(geometry): describe a detail frame by its position"
```

---

### Task 2: Cut frames from a position

This is the behaviour change. `section_bounds` and `make_section` stop taking an index and a count, `pipeline` computes default positions instead, and the golden hashes are regenerated.

**Files:**
- Modify: `src/maskingframe/geometry.py:194-260` (`section_bounds`, `make_section`)
- Modify: `src/maskingframe/pipeline.py:103-168` (`process_image`), `src/maskingframe/pipeline.py:245-292` (`preview_frames`)
- Test: `tests/test_geometry.py`, `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `frame_width`, `position_travel`, `clamp_position`, `default_positions` from Task 1.
- Produces:
  - `geometry.section_bounds(pano_width: int, pano_height: int, position: float, ratio: AspectRatio) -> tuple[int, int]`
  - `geometry.make_section(image: Image.Image, position: float, ratio: AspectRatio, style: FrameStyle = DEFAULT_STYLE) -> Image.Image`

- [x] **Step 1: Write the failing tests**

Replace any existing `section_bounds` / `make_section` tests in `tests/test_geometry.py` that pass an index and a count (search for `section_bounds(` and `make_section(`) with these:

```python
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
```

If `tests/test_geometry.py` does not already import the helper, add `from tests import conftest` to its imports (the suite has `tests/__init__.py`, so this works).

Add to `tests/test_pipeline.py`:

```python
def test_process_image_honours_explicit_positions(tmp_path: Path) -> None:
    source = tmp_path / "pano.jpg"
    conftest.synthetic_panorama(2000, 1000).save(source, "JPEG", quality=95)

    left = pipeline.process_image(source, tmp_path / "left", positions=(0.0, 0.0))
    spread = pipeline.process_image(source, tmp_path / "spread", positions=(0.0, 0.6))

    # Both runs asked for two detail frames, so both wrote three files.
    assert len(left) == 3 and len(spread) == 3
    # Same position, same picture; different position, different picture.
    assert left[1].read_bytes() == left[2].read_bytes()
    assert spread[1].read_bytes() != spread[2].read_bytes()


def test_process_image_without_positions_uses_the_even_default(tmp_path: Path) -> None:
    source = tmp_path / "pano.jpg"
    conftest.synthetic_panorama(2000, 1000).save(source, "JPEG", quality=95)

    implicit = pipeline.process_image(source, tmp_path / "implicit")
    explicit = pipeline.process_image(
        source,
        tmp_path / "explicit",
        positions=geometry_default_positions(2000, 1000),
    )
    assert [p.read_bytes() for p in implicit] == [p.read_bytes() for p in explicit]
```

`pipeline` re-exports what the GUI needs, but a test may import `geometry` directly. Add this helper just above that second test:

```python
def geometry_default_positions(width: int, height: int) -> tuple[float, ...]:
    from maskingframe import geometry

    return geometry.default_positions(width, height, pipeline.DEFAULT_RATIO)
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `mise exec -- uv run pytest tests/test_geometry.py tests/test_pipeline.py -v`
Expected: FAIL — `section_bounds()` takes different arguments, and `process_image()` got an unexpected keyword argument `positions`.

- [x] **Step 3: Rewrite `section_bounds` and `make_section`**

In `geometry.py`, replace the whole of `section_bounds` with:

```python
def section_bounds(
    pano_width: int, pano_height: int, position: float, ratio: AspectRatio
) -> tuple[int, int]:
    """The horizontal crop bounds of the detail frame at `position`.

    Full height and exactly the output aspect, so the cover-scale in
    `make_section` discards nothing vertically. `position` is the left edge
    as a fraction of the width; it is clamped, so a caller cannot ask for a
    crop that runs off an edge.
    """
    width = min(frame_width(pano_height, ratio), pano_width)
    clamped = clamp_position(position, pano_width, pano_height, ratio)
    start = math.floor(clamped * pano_width + 0.5)
    start = min(start, pano_width - width)
    return start, start + width
```

Then in `make_section`, change the signature and the two lines that use it:

```python
def make_section(
    image: Image.Image,
    position: float,
    ratio: AspectRatio,
    style: FrameStyle = DEFAULT_STYLE,
) -> Image.Image:
```

and replace

```python
    width, height = image.size
    start, end = section_bounds(width, index, count)
```

with

```python
    width, height = image.size
    start, end = section_bounds(width, height, position, ratio)
```

Leave the rest of `make_section` — the cover-scale, the centre crop and the border branch — exactly as it is. Update its docstring's first paragraph to:

```python
    """Crop one detail frame at `position` and scale it to fill the ratio.

    The crop is already the output aspect, so the cover-scale is close to a
    straight resize and the centre crop takes at most a rounding pixel.
```

- [x] **Step 4: Thread positions through `pipeline`**

In `process_image`, add the parameter and use it. The signature becomes:

```python
def process_image(
    input_path: Path | str,
    output_prefix: Path | str,
    ratio: AspectRatio = DEFAULT_RATIO,
    on_frame: FrameCallback | None = None,
    positions: Sequence[float] | None = None,
    style: FrameStyle = DEFAULT_STYLE,
) -> list[Path]:
```

Add to its docstring, after the `style` paragraph:

```text
    `positions` places each detail frame along the panorama: one left edge
    per frame, as a fraction of the width, ascending. Omitted, the frames
    are spread evenly, which is what the CLI and every batch run do -- a
    position is chosen by looking at one photograph.
```

Replace

```python
    count = geometry.section_count(width, height, ratio)
    targets = output_paths(output_prefix, count)
```

with

```python
    places = (
        geometry.default_positions(width, height, ratio)
        if positions is None
        else geometry.normalise_positions(positions, width, height, ratio)
    )
    count = len(places)
    targets = output_paths(output_prefix, count)
```

and replace the section loop

```python
    for index in range(count):
        geometry.make_section(source, index, count, ratio, style).save(
            targets[index + 1], "JPEG", quality=JPEG_QUALITY
        )
        _report_frame(on_frame, index + 1, total, targets[index + 1])
```

with

```python
    for index, place in enumerate(places):
        geometry.make_section(source, place, ratio, style).save(
            targets[index + 1], "JPEG", quality=JPEG_QUALITY
        )
        _report_frame(on_frame, index + 1, total, targets[index + 1])
```

In `preview_frames`, add `positions` **after** `cached` — `style` is already the third parameter there and moving it would break positional callers:

```python
def preview_frames(
    input_path: Path | str,
    ratio: AspectRatio = DEFAULT_RATIO,
    style: FrameStyle = DEFAULT_STYLE,
    cached: bool = False,
    positions: Sequence[float] | None = None,
) -> list[Image.Image]:
```

and replace

```python
    count = geometry.section_count(width, height, ratio)
    frames = [geometry.make_padded_frame(source, ratio, style)]
    frames += [geometry.make_section(source, index, count, ratio, style) for index in range(count)]
    return frames
```

with

```python
    places = (
        geometry.default_positions(width, height, ratio)
        if positions is None
        else geometry.normalise_positions(positions, width, height, ratio)
    )
    frames = [geometry.make_padded_frame(source, ratio, style)]
    frames += [geometry.make_section(source, place, ratio, style) for place in places]
    return frames
```

`Sequence` is already imported in `pipeline.py` (`from collections.abc import Sequence`); confirm with `grep -n "collections.abc" src/maskingframe/pipeline.py` and add it if not.

- [x] **Step 5: Regenerate the golden hashes**

The detail frames change on purpose, so the byte-identity guard has to be re-baselined. First record the old values:

```bash
git show HEAD:tests/test_pipeline.py | sed -n '/^GOLDEN_HASHES/,/^}/p' > /tmp/old-golden.txt
```

Then generate the new ones with the command already documented above `GOLDEN_HASHES` in `tests/test_pipeline.py`:

```bash
mkdir -p /tmp/g && mise exec -- uv run python -c "
import hashlib
from maskingframe import pipeline
for name, ratio in pipeline.RATIOS.items():
    out = pipeline.process_image('tests/fixtures/golden_wide.jpg', f'/tmp/g/{name}', ratio)
    for p in out:
        print(name, p.name, hashlib.sha256(p.read_bytes()).hexdigest())
"
```

Paste the new digests into `GOLDEN_HASHES`, keeping the existing dict shape. Note that the *number* of frames per ratio does not change — `section_count` is untouched — so only the digests move, and the `_1_padded.jpg` digests should be **unchanged**, because `make_padded_frame` was not touched. If a padded digest moves, stop: something else broke.

Add a sentence to the comment block above `GOLDEN_HASHES`:

```python
# Re-baselined on 2026-08-01: a detail frame is now a full-height crop at
# exactly the output aspect (`pano_height * ratio`) rather than a
# `width // count` tile, so the section digests moved. The padded-frame
# digests did not, and must not.
```

- [x] **Step 6: Run the tests to verify they pass**

Run: `mise run check`
Expected: PASS. If `tests/test_preview_frames.py` or `tests/test_cli.py` fail on a changed frame count, they are asserting the old tiling — read the failure and update the expectation to the new full-height crop, do not weaken the assertion.

- [x] **Step 7: Record the behaviour change in CLAUDE.md**

In the "Behaviour changes from the pre-refactor scripts" list in `CLAUDE.md`, add:

```markdown
- A detail frame is no longer a `pano_width // count` tile. It is a full-height crop exactly `pano_height * ratio` wide, placed by a position — its left edge as a fraction of the panorama's width. The tiles no longer meet edge to edge, which they never needed to: the detail frames are a zoom, not a tiling. The gain is that nothing vertical is discarded. Before, a 2.4:1 panorama at `1.91:1` got two 1.2:1 tiles that `make_section` scaled to cover and then centre-cropped the top and bottom away from. The golden hashes were re-baselined on 2026-08-01; the padded frame is unaffected.
```

Also update the `geometry.py` bullet in the Architecture section: replace "`make_section()` (takes an index, a count, a ratio, and a style)" with "`make_section()` (takes a position, a ratio, and a style)", and add after `section_count()`: "`frame_width()`, `position_travel()`, `clamp_position()`, `normalise_positions()` and `default_positions()` — the position model".

- [x] **Step 8: Run the full gate and commit**

```bash
mise run check
git add src/maskingframe/geometry.py src/maskingframe/pipeline.py tests/ CLAUDE.md
git commit -m "feat: cut detail frames from a position at full source height"
```

---

### Task 3: Adding and removing a frame

Pure arithmetic, so it is worth its own gate before any widget depends on it.

**Files:**
- Modify: `src/maskingframe/geometry.py`
- Test: `tests/test_geometry.py`

**Interfaces:**
- Consumes: `frame_width`, `position_travel`, `clamp_position`, `normalise_positions`, `MIN_SECTIONS` from Task 1 and the existing module.
- Produces:
  - `geometry.insert_position(positions: Sequence[float], pano_width: int, pano_height: int, ratio: AspectRatio) -> tuple[float, ...]`
  - `geometry.drop_position(positions: Sequence[float]) -> tuple[float, ...]`

- [x] **Step 1: Write the failing tests**

Add to `tests/test_geometry.py`:

```python
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
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `mise exec -- uv run pytest tests/test_geometry.py -k "insert or drop" -v`
Expected: FAIL with `AttributeError: module 'maskingframe.geometry' has no attribute 'insert_position'`.

- [x] **Step 3: Implement**

Add after `default_positions` in `geometry.py`:

```python
def insert_position(
    positions: Sequence[float], pano_width: int, pano_height: int, ratio: AspectRatio
) -> tuple[float, ...]:
    """Add one frame where the panorama is least covered.

    A new frame should land on something nobody is looking at yet, so the
    widest stretch no frame covers wins and the frame is centred in it.
    When the frames already cover everything -- which they do as soon as
    they are close together -- there is no such stretch, so it falls back
    to halving the widest gap between two adjacent left edges.
    """
    width = frame_width(pano_height, ratio) / pano_width
    places = sorted(positions)
    if not places:
        return (0.0,)

    # Merge the covered intervals, then look at what is left over.
    merged: list[list[float]] = []
    for start in places:
        end = start + width
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])

    holes: list[tuple[float, float]] = []
    edge = 0.0
    for start, end in merged:
        if start > edge:
            holes.append((edge, start))
        edge = max(edge, end)
    if edge < 1.0:
        holes.append((edge, 1.0))

    if holes:
        start, end = max(holes, key=lambda hole: hole[1] - hole[0])
        chosen = (start + end) / 2 - width / 2
    else:
        gaps = list(zip(places, places[1:], strict=False))
        if gaps:
            start, end = max(gaps, key=lambda gap: gap[1] - gap[0])
            chosen = (start + end) / 2
        else:
            chosen = places[0]

    chosen = clamp_position(chosen, pano_width, pano_height, ratio)
    return normalise_positions(sorted([*places, chosen]), pano_width, pano_height, ratio)


def drop_position(positions: Sequence[float]) -> tuple[float, ...]:
    """Remove the last frame. Never goes below two.

    Two is the floor for the same reason `section_count` floors there: a
    single detail frame would just restate the whole-panorama frame.
    """
    if len(positions) <= MIN_SECTIONS:
        raise ValueError(f"a panorama keeps at least two detail frames, got {len(positions)}")
    return tuple(positions[:-1])
```

- [x] **Step 4: Run the tests to verify they pass**

Run: `mise exec -- uv run pytest tests/test_geometry.py -v`
Expected: PASS.

- [x] **Step 5: Run the full gate and commit**

```bash
mise run check
git add src/maskingframe/geometry.py tests/test_geometry.py
git commit -m "feat(geometry): add and remove a detail frame"
```

---

### Task 4: The GUI's way in through `pipeline`

The GUI may not import `geometry`, so everything it needs about positions has to arrive through `pipeline`.

**Files:**
- Modify: `src/maskingframe/pipeline.py` (the re-export block near the top, `SourceFacts`, `inspect_source`)
- Test: `tests/test_inspect.py`

**Interfaces:**
- Consumes: `geometry.default_positions`, `geometry.normalise_positions`, `geometry.insert_position`, `geometry.drop_position`, `geometry.frame_width`, `geometry.position_travel` from Tasks 1 and 3.
- Produces, all importable as `pipeline.<name>`:
  - `default_positions`, `normalise_positions`, `insert_position`, `drop_position`, `frame_width`, `position_travel` (re-exports)
  - `SourceFacts.positions: tuple[float, ...]` and `SourceFacts.window_fraction: float`
  - `ribbon_thumbnail(path: Path | str, max_width: int = 1200) -> Image.Image`

- [x] **Step 1: Write the failing tests**

Add to `tests/test_inspect.py`:

```python
def test_facts_carry_the_default_positions(tmp_path: Path) -> None:
    source = tmp_path / "pano.jpg"
    conftest.synthetic_panorama(2000, 1000).save(source, "JPEG", quality=95)

    facts = pipeline.inspect_source(source, pipeline.RATIOS["4:5"])

    # frame_count counts the padded frame too, so there is one fewer position.
    assert len(facts.positions) == facts.frame_count - 1
    assert facts.positions[0] == 0.0
    assert facts.window_fraction == pytest.approx(0.4)


def test_facts_positions_follow_the_ratio(tmp_path: Path) -> None:
    source = tmp_path / "pano.jpg"
    conftest.synthetic_panorama(2000, 1000).save(source, "JPEG", quality=95)

    portrait = pipeline.inspect_source(source, pipeline.RATIOS["4:5"])
    landscape = pipeline.inspect_source(source, pipeline.RATIOS["1.91:1"])

    assert portrait.window_fraction < landscape.window_fraction


def test_the_gui_can_reach_the_position_model_without_importing_geometry() -> None:
    # gui/ may import only pipeline, so these have to be re-exported.
    for name in (
        "default_positions",
        "normalise_positions",
        "insert_position",
        "drop_position",
        "frame_width",
        "position_travel",
    ):
        assert callable(getattr(pipeline, name)), name


def test_ribbon_thumbnail_is_bounded_and_keeps_its_shape(tmp_path: Path) -> None:
    source = tmp_path / "pano.jpg"
    conftest.synthetic_panorama(4000, 800).save(source, "JPEG", quality=95)

    thumb = pipeline.ribbon_thumbnail(source, max_width=1200)

    assert thumb.width <= 1200
    assert thumb.width / thumb.height == pytest.approx(5.0, rel=0.01)
```

Make sure `tests/test_inspect.py` imports what it needs: `pytest`, `from pathlib import Path`, `from maskingframe import pipeline`, and `from tests import conftest`.

- [x] **Step 2: Run the tests to verify they fail**

Run: `mise exec -- uv run pytest tests/test_inspect.py -v`
Expected: FAIL — `SourceFacts` has no attribute `positions`, and `pipeline` has no attribute `ribbon_thumbnail`.

- [x] **Step 3: Implement**

Find the existing re-export block in `pipeline.py` (the one bringing `AspectRatio`, `RATIOS`, `DEFAULT_RATIO`, `FrameStyle`, `DEFAULT_STYLE`, `parse_colour`, `MAX_PERCENT` across from `geometry`) and extend it with the six position functions, keeping whatever style it already uses. If it is a `from maskingframe.geometry import (...)` list, add the names to that list; if it is a series of assignments, add matching assignments. Extend the comment that guards it so the reason survives:

```python
# Re-exported so `cli.py` and `gui/` can offer ratio, border and position
# controls without importing `geometry` directly -- that is what preserves
# the one-way dependency direction. Do not "simplify" these away.
```

Add the two fields to `SourceFacts`, with defaults so no existing constructor breaks:

```python
    positions: tuple[float, ...] = ()
    """Where the detail frames land by default: one left edge per frame, as
    a fraction of the panorama's width. The interface opens on these and
    the user moves them from there."""

    window_fraction: float = 0.0
    """How much of the panorama's width one detail frame covers. The ribbon
    needs it to draw a window, and it is derived from the ratio and the
    source's height, so it belongs with the rest of the header read."""
```

In `inspect_source`, build them from the size already read:

```python
    return SourceFacts(
        width=width,
        height=height,
        native_ratio=f"{width / height:.2f}:1",
        frame_count=geometry.section_count(width, height, ratio) + 1,
        positions=geometry.default_positions(width, height, ratio),
        window_fraction=min(1.0, geometry.frame_width(height, ratio) / width),
    )
```

Add `ribbon_thumbnail` next to `cached_preview_source`:

```python
def ribbon_thumbnail(input_path: Path | str, max_width: int = 1200) -> Image.Image:
    """A small copy of the whole panorama, for the ribbon to draw.

    Bounded by width rather than by pixels because the ribbon is one long
    strip: a 13:1 panorama at 1200px wide is under 100px tall and costs
    almost nothing. Uses `draft` so libjpeg decodes straight to a reduced
    scale rather than decoding in full and throwing the pixels away.

    Separate from `cached_preview_source`, which holds a much larger copy
    for cutting detail frames from. This one is only ever looked at.
    """
    path = Path(input_path)
    with Image.open(path) as opened:
        width, height = opened.size
        if width > max_width:
            scale = max_width / width
            opened.draft("RGB", (max_width, max(1, math.floor(height * scale + 0.5))))
        image = opened.convert("RGB")
    if image.width > max_width:
        scale = max_width / image.width
        image = image.resize(
            (max_width, max(1, math.floor(image.height * scale + 0.5))),
            Image.Resampling.LANCZOS,
        )
    return image
```

If `pipeline.py` does not already `import math`, add it.

- [x] **Step 4: Run the tests to verify they pass**

Run: `mise exec -- uv run pytest tests/test_inspect.py -v`
Expected: PASS.

- [x] **Step 5: Run the full gate and commit**

```bash
mise run check
git add src/maskingframe/pipeline.py tests/test_inspect.py
git commit -m "feat(pipeline): report where the detail frames land"
```

---

### Task 5: The ribbon widget

Presentation only. It knows a picture, a window width and a list of positions, and nothing else. Do this in parallel with Task 6.

**Files:**
- Create: `src/maskingframe/gui/ribbon.py`
- Create: `tests/test_ribbon.py`

**Interfaces:**
- Consumes: `maskingframe.gui.theme` (`TABLE`, `PANEL`, `EDGE`, `INK`, `INK_DIM`, `CHINAGRAPH`, `S`, `M`, `stencil_font`), `maskingframe.gui.strip.pil_to_pixmap`.
- Produces:
  - `ribbon.RIBBON_HEIGHT: int`
  - `class FrameRibbon(QWidget)` with:
    - `positions_changed = Signal(tuple)` — during a drag, every move
    - `positions_settled = Signal(tuple)` — once, on release
    - `set_source(image: Image.Image | None) -> None`
    - `set_plan(positions: Sequence[float], window_fraction: float) -> None` (silent; emits nothing)
    - `positions() -> tuple[float, ...]`
    - `window_rects() -> list[QRect]`
    - `picture_rect() -> QRect`

- [x] **Step 1: Write the failing tests**

Create `tests/test_ribbon.py`:

```python
"""Tests for the ribbon: the whole panorama with a window per detail frame.

Offscreen, like every other widget test here -- `conftest` sets
QT_QPA_PLATFORM before Qt is imported.
"""

from collections.abc import Sequence

import pytest
from PySide6.QtCore import QPoint, Qt
from pytestqt.qtbot import QtBot

from maskingframe.gui.ribbon import RIBBON_HEIGHT, FrameRibbon
from tests import conftest


def build(qtbot: QtBot, positions: Sequence[float] = (0.0, 0.6)) -> FrameRibbon:
    ribbon = FrameRibbon()
    qtbot.addWidget(ribbon)
    ribbon.resize(600, RIBBON_HEIGHT)
    ribbon.set_source(conftest.synthetic_panorama(1000, 400))
    ribbon.set_plan(positions, 0.4)
    return ribbon


def test_the_picture_is_letterboxed_not_cropped(qtbot: QtBot) -> None:
    ribbon = build(qtbot)
    rect = ribbon.picture_rect()
    # A 2.5:1 picture in a 600-wide, fixed-height ribbon fits on width and
    # leaves space above and below rather than losing the top and bottom.
    assert rect.width() / rect.height() == pytest.approx(2.5, rel=0.02)
    assert rect.width() <= 600
    assert rect.height() <= RIBBON_HEIGHT


def test_one_window_per_position(qtbot: QtBot) -> None:
    ribbon = build(qtbot, (0.0, 0.3, 0.6))
    assert len(ribbon.window_rects()) == 3


def test_a_window_sits_where_its_position_says(qtbot: QtBot) -> None:
    ribbon = build(qtbot, (0.0, 0.6))
    picture = ribbon.picture_rect()
    first, second = ribbon.window_rects()
    assert first.left() == picture.left()
    assert second.left() == pytest.approx(picture.left() + 0.6 * picture.width(), abs=2)
    assert first.width() == pytest.approx(0.4 * picture.width(), abs=2)


def test_set_plan_is_silent(qtbot: QtBot) -> None:
    ribbon = build(qtbot)
    with qtbot.assertNotEmitted(ribbon.positions_changed):
        ribbon.set_plan((0.1, 0.5), 0.4)


def test_dragging_a_window_moves_only_that_frame(qtbot: QtBot) -> None:
    ribbon = build(qtbot, (0.0, 0.6))
    picture = ribbon.picture_rect()
    start = QPoint(picture.left() + 5, picture.center().y())

    qtbot.mousePress(ribbon, Qt.MouseButton.LeftButton, pos=start)
    qtbot.mouseMove(ribbon, QPoint(start.x() + int(0.2 * picture.width()), start.y()))

    moved = ribbon.positions()
    assert moved[0] == pytest.approx(0.2, abs=0.02)
    assert moved[1] == pytest.approx(0.6)


def test_a_drag_emits_while_moving_and_once_on_release(qtbot: QtBot) -> None:
    ribbon = build(qtbot, (0.0, 0.6))
    picture = ribbon.picture_rect()
    start = QPoint(picture.left() + 5, picture.center().y())

    with qtbot.waitSignal(ribbon.positions_changed, timeout=1000):
        qtbot.mousePress(ribbon, Qt.MouseButton.LeftButton, pos=start)
        qtbot.mouseMove(ribbon, QPoint(start.x() + 40, start.y()))

    with qtbot.waitSignal(ribbon.positions_settled, timeout=1000):
        qtbot.mouseRelease(
            ribbon, Qt.MouseButton.LeftButton, pos=QPoint(start.x() + 40, start.y())
        )


def test_a_frame_cannot_be_dragged_past_its_neighbour(qtbot: QtBot) -> None:
    ribbon = build(qtbot, (0.0, 0.3))
    picture = ribbon.picture_rect()
    start = QPoint(picture.left() + 5, picture.center().y())

    qtbot.mousePress(ribbon, Qt.MouseButton.LeftButton, pos=start)
    qtbot.mouseMove(ribbon, QPoint(picture.right() - 5, start.y()))

    moved = ribbon.positions()
    assert moved[0] == pytest.approx(0.3, abs=0.02)
    assert moved[1] == pytest.approx(0.3)


def test_a_frame_cannot_be_dragged_off_the_left_edge(qtbot: QtBot) -> None:
    ribbon = build(qtbot, (0.2, 0.6))
    picture = ribbon.picture_rect()
    start = QPoint(picture.left() + int(0.2 * picture.width()) + 5, picture.center().y())

    qtbot.mousePress(ribbon, Qt.MouseButton.LeftButton, pos=start)
    qtbot.mouseMove(ribbon, QPoint(picture.left() - 200, start.y()))

    assert ribbon.positions()[0] == 0.0


def test_with_no_source_it_draws_nothing_and_does_not_crash(qtbot: QtBot) -> None:
    ribbon = FrameRibbon()
    qtbot.addWidget(ribbon)
    ribbon.resize(600, RIBBON_HEIGHT)
    ribbon.set_source(None)
    ribbon.set_plan((0.0, 0.5), 0.4)
    ribbon.repaint()
    assert ribbon.window_rects() == []
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `mise exec -- uv run pytest tests/test_ribbon.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'maskingframe.gui.ribbon'`.

- [x] **Step 3: Implement the widget**

Create `src/maskingframe/gui/ribbon.py`:

```python
"""The ribbon: the whole panorama once, with a window per detail frame.

The contact strip shows what each frame *is*; the ribbon shows where each
one *came from*, which is the thing you cannot see by looking at the frames
alone -- how close two crops are, and what the panorama has left over.

Fixed height with the picture fitted inside it, never cropped. A height
that followed the picture would be 275px for a 2.3:1 panorama and a 49px
sliver for a 13:1 one, and the whole tab would jump every time a different
file was loaded.

Presentation only, like `strip.py`. It knows a picture, how wide one window
is as a fraction of the panorama, and where the windows are. It has never
heard of a FrameStyle, an AspectRatio or a file.
"""

from collections.abc import Sequence

from PIL import Image
from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPaintEvent, QPixmap
from PySide6.QtWidgets import QSizePolicy, QWidget

from maskingframe.gui import theme
from maskingframe.gui.strip import pil_to_pixmap

RIBBON_HEIGHT = 96
"""Tall enough to judge a crop by, short enough to leave the strip the room."""

DIM = QColor(theme.INK)
"""The wash over everything no frame covers. Alpha is set where it is used."""

DIM_ALPHA = 110

HANDLE = 2
"""The window's edge. A hairline, like every other edge in this interface."""


class FrameRibbon(QWidget):
    """The panorama with a draggable window per detail frame."""

    positions_changed = Signal(tuple)
    """Every movement of a drag. Cheap work only -- this drives the overlay,
    not a re-render."""

    positions_settled = Signal(tuple)
    """Once, when the hand stops. This is what a re-render hangs off, and it
    is the same split `PercentSlider` makes for the border controls."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pixmap: QPixmap | None = None
        self._aspect = 1.0
        self._positions: tuple[float, ...] = ()
        self._window = 0.0
        self._dragging: int | None = None
        self._grab_offset = 0.0
        self._font: QFont = theme.stencil_font(10, tracking=1.4)
        self.setFixedHeight(RIBBON_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    # --- what it is showing -------------------------------------------------

    def set_source(self, image: Image.Image | None) -> None:
        """The panorama to draw, or nothing."""
        if image is None:
            self._pixmap = None
            self._aspect = 1.0
        else:
            self._pixmap = pil_to_pixmap(image)
            self._aspect = image.width / max(1, image.height)
        self.update()

    def set_plan(self, positions: Sequence[float], window_fraction: float) -> None:
        """Where the frames are and how wide one is. Emits nothing.

        Silent on purpose: a tab that saves on `positions_changed` would
        otherwise write back what it has just read.
        """
        self._positions = tuple(positions)
        self._window = max(0.0, min(1.0, window_fraction))
        self.update()

    def positions(self) -> tuple[float, ...]:
        return self._positions

    # --- geometry, exposed so it can be checked without sampling pixels -----

    def picture_rect(self) -> QRect:
        """Where the panorama lands, fitted inside the ribbon."""
        if self._pixmap is None:
            return QRect()
        available_width = max(1, self.width() - 2 * theme.S)
        available_height = max(1, self.height() - 2 * theme.S)
        width = available_width
        height = max(1, round(width / self._aspect))
        if height > available_height:
            height = available_height
            width = max(1, round(height * self._aspect))
        left = theme.S + (available_width - width) // 2
        top = theme.S + (available_height - height) // 2
        return QRect(left, top, width, height)

    def window_rects(self) -> list[QRect]:
        """One rectangle per frame, in widget pixels."""
        picture = self.picture_rect()
        if picture.isNull() or not self._positions:
            return []
        span = picture.width()
        width = max(1, round(self._window * span))
        return [
            QRect(picture.left() + round(position * span), picture.top(), width, picture.height())
            for position in self._positions
        ]

    # --- dragging -----------------------------------------------------------

    def _window_at(self, point: QPoint) -> int | None:
        """Which window the cursor is in, latest first.

        Latest first so that when two frames overlap the one drawn on top is
        the one you grab -- anything else would feel like the interface
        picking a different frame from the one under the cursor.
        """
        for index in reversed(range(len(self.window_rects()))):
            if self.window_rects()[index].contains(point):
                return index
        return None

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        point = event.position().toPoint()
        index = self._window_at(point)
        if index is None:
            return
        picture = self.picture_rect()
        grabbed = (point.x() - picture.left()) / max(1, picture.width())
        self._dragging = index
        self._grab_offset = grabbed - self._positions[index]

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._dragging is None:
            return
        picture = self.picture_rect()
        point = event.position().toPoint()
        wanted = (point.x() - picture.left()) / max(1, picture.width()) - self._grab_offset
        self._positions = self._moved(self._dragging, wanted)
        self.update()
        self.positions_changed.emit(self._positions)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._dragging is None:
            return
        self._dragging = None
        self.positions_settled.emit(self._positions)

    def _moved(self, index: int, wanted: float) -> tuple[float, ...]:
        """One frame moved to `wanted`, clamped by the edges and its neighbours.

        Neighbours clamp rather than swap: the frames are numbered, and a
        carousel that runs backwards along the picture is confusing. Overlap
        is fine, so the bound is the neighbour's position itself, not a
        minimum separation.
        """
        lower = self._positions[index - 1] if index > 0 else 0.0
        upper = (
            self._positions[index + 1]
            if index + 1 < len(self._positions)
            else max(0.0, 1.0 - self._window)
        )
        upper = min(upper, max(0.0, 1.0 - self._window))
        placed = min(max(wanted, lower), max(lower, upper))
        return tuple(
            placed if position_index == index else position
            for position_index, position in enumerate(self._positions)
        )

    # --- drawing ------------------------------------------------------------

    def sizeHint(self) -> QSize:
        return QSize(480, RIBBON_HEIGHT)

    def paintEvent(self, _event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(theme.TABLE))
        if self._pixmap is None:
            return
        picture = self.picture_rect()
        painter.drawPixmap(picture, self._pixmap)

        # Everything no frame covers goes under a wash, so the windows read
        # as the part of the picture that will actually be printed.
        wash = QColor(DIM)
        wash.setAlpha(DIM_ALPHA)
        windows = self.window_rects()
        for band in _uncovered(picture, windows):
            painter.fillRect(band, wash)

        painter.setFont(self._font)
        for index, window in enumerate(windows):
            painter.setPen(QColor(theme.INK))
            for offset in range(HANDLE):
                painter.drawRect(window.adjusted(offset, offset, -offset - 1, -offset - 1))
            painter.setPen(QColor(theme.CHINAGRAPH))
            painter.drawText(
                window.adjusted(theme.S // 2, 1, 0, 0),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                str(index + 2),
            )
        painter.end()


def _uncovered(picture: QRect, windows: Sequence[QRect]) -> list[QRect]:
    """The parts of the picture no window covers.

    Merged first, because windows may overlap and washing an overlap twice
    would make it darker than the rest of the dimmed area.
    """
    if not windows:
        return [picture] if not picture.isNull() else []
    merged: list[list[int]] = []
    for window in sorted(windows, key=lambda w: w.left()):
        if merged and window.left() <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], window.right())
        else:
            merged.append([window.left(), window.right()])

    bands: list[QRect] = []
    edge = picture.left()
    for start, end in merged:
        if start > edge:
            bands.append(QRect(edge, picture.top(), start - edge, picture.height()))
        edge = max(edge, end + 1)
    if edge < picture.right():
        bands.append(QRect(edge, picture.top(), picture.right() - edge, picture.height()))
    return bands
```

The frame numbering starts at 2 because frame 1 is the whole-panorama frame, exactly as `split_tab.preview_titles` numbers them.

- [x] **Step 4: Run the tests to verify they pass**

Run: `mise exec -- uv run pytest tests/test_ribbon.py -v`
Expected: PASS. If `mouseMove` does not reach `mouseMoveEvent`, add `self.setMouseTracking(False)` — Qt delivers move events to a widget during a press without tracking, so no change should be needed; check the press actually landed inside `picture_rect()` first.

- [x] **Step 5: Run the full gate and commit**

```bash
mise run check
git add src/maskingframe/gui/ribbon.py tests/test_ribbon.py
git commit -m "feat(gui): add the frame ribbon"
```

---

### Task 6: Dragging inside a strip frame

Do this in parallel with Task 5. It touches only `strip.py`, which Task 5 does not modify.

**Files:**
- Modify: `src/maskingframe/gui/strip.py` (`ContactStrip`)
- Test: `tests/test_strip.py`

**Interfaces:**
- Consumes: `ContactStrip._frame_rect(index)` and `frame_rect_at(index)`, both already present.
- Produces, on `ContactStrip`:
  - `frame_dragged = Signal(int, float)` — (frame index, delta in *frame widths*, positive meaning the crop moves right)
  - `frame_drag_settled = Signal(int)` — (frame index), once on release
  - `set_draggable(draggable: bool) -> None`

- [x] **Step 1: Write the failing tests**

Add to `tests/test_strip.py`:

```python
def test_the_strip_is_not_draggable_until_it_is_told_to_be(qtbot: QtBot) -> None:
    strip = ContactStrip(frames=3)
    qtbot.addWidget(strip)
    strip.resize(600, 300)

    with qtbot.assertNotEmitted(strip.frame_dragged):
        centre = strip.frame_rect_at(1).center()
        qtbot.mousePress(strip, Qt.MouseButton.LeftButton, pos=centre)
        qtbot.mouseMove(strip, QPoint(centre.x() + 30, centre.y()))
        qtbot.mouseRelease(strip, Qt.MouseButton.LeftButton, pos=centre)


def test_dragging_a_frame_reports_a_delta_in_frame_widths(qtbot: QtBot) -> None:
    strip = ContactStrip(frames=3)
    qtbot.addWidget(strip)
    strip.resize(600, 300)
    strip.set_draggable(True)

    rect = strip.frame_rect_at(1)
    centre = rect.center()
    seen: list[tuple[int, float]] = []
    strip.frame_dragged.connect(lambda index, delta: seen.append((index, delta)))

    qtbot.mousePress(strip, Qt.MouseButton.LeftButton, pos=centre)
    qtbot.mouseMove(strip, QPoint(centre.x() - rect.width() // 2, centre.y()))

    assert seen, "a drag inside a frame should report a delta"
    index, delta = seen[-1]
    assert index == 1
    # The picture was pushed left by half a frame, so the crop moves right.
    assert delta == pytest.approx(0.5, abs=0.05)


def test_dragging_frame_one_reports_nothing(qtbot: QtBot) -> None:
    # Frame 1 is the whole panorama. There is nothing to position.
    strip = ContactStrip(frames=3)
    qtbot.addWidget(strip)
    strip.resize(600, 300)
    strip.set_draggable(True)

    with qtbot.assertNotEmitted(strip.frame_dragged):
        centre = strip.frame_rect_at(0).center()
        qtbot.mousePress(strip, Qt.MouseButton.LeftButton, pos=centre)
        qtbot.mouseMove(strip, QPoint(centre.x() + 40, centre.y()))


def test_releasing_a_drag_settles_once(qtbot: QtBot) -> None:
    strip = ContactStrip(frames=3)
    qtbot.addWidget(strip)
    strip.resize(600, 300)
    strip.set_draggable(True)

    centre = strip.frame_rect_at(2).center()
    qtbot.mousePress(strip, Qt.MouseButton.LeftButton, pos=centre)
    qtbot.mouseMove(strip, QPoint(centre.x() + 20, centre.y()))

    with qtbot.waitSignal(strip.frame_drag_settled, timeout=1000) as blocker:
        qtbot.mouseRelease(
            strip, Qt.MouseButton.LeftButton, pos=QPoint(centre.x() + 20, centre.y())
        )
    assert blocker.args == [2]
```

Ensure `tests/test_strip.py` imports `QPoint` and `Qt` from `PySide6.QtCore` and `pytest`.

- [x] **Step 2: Run the tests to verify they fail**

Run: `mise exec -- uv run pytest tests/test_strip.py -k drag -v`
Expected: FAIL with `AttributeError: 'ContactStrip' object has no attribute 'frame_dragged'`.

- [x] **Step 3: Implement**

Add `Signal` to the `PySide6.QtCore` import in `strip.py` and `QMouseEvent` to the `PySide6.QtGui` import. Then, inside `ContactStrip`, add the signals immediately under the class docstring:

```python
    frame_dragged = Signal(int, float)
    """(frame index, delta in frame widths). Positive means the crop moves
    right along the panorama -- the user pushed the picture left, the way a
    photograph moves under a hand.

    A delta rather than a position, because the strip has no idea how wide
    the panorama is. The tab converts it, since the tab is the only thing
    that knows both."""

    frame_drag_settled = Signal(int)
    """The hand has stopped on this frame. What a re-render hangs off."""
```

In `__init__`, after `self._border`:

```python
        self._draggable = False
        self._drag_index: int | None = None
        self._drag_origin = 0
```

Add the public switch next to `set_border_preview`:

```python
    def set_draggable(self, draggable: bool) -> None:
        """Whether a frame's picture can be pushed left and right.

        Off by default and off in folder mode: a position is chosen by
        looking at one photograph, so there is nothing to drag when the run
        is a whole folder.
        """
        self._draggable = draggable
        self._drag_index = None
        self.setCursor(
            Qt.CursorShape.SizeHorCursor if draggable else Qt.CursorShape.ArrowCursor
        )
```

And the handlers, after `paintEvent`:

```python
    def _frame_at(self, point: QPoint) -> int | None:
        for index in range(len(self._frames)):
            if self._frame_rect(index).contains(point):
                return index
        return None

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if not self._draggable or event.button() != Qt.MouseButton.LeftButton:
            return
        point = event.position().toPoint()
        index = self._frame_at(point)
        # Frame 0 is the whole panorama: it shows everything, so there is no
        # position in it to choose.
        if index is None or index == 0:
            return
        self._drag_index = index
        self._drag_origin = point.x()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_index is None:
            return
        rect = self._frame_rect(self._drag_index)
        moved = event.position().toPoint().x() - self._drag_origin
        # Pushing the picture left moves the crop right, so the sign flips.
        self.frame_dragged.emit(self._drag_index, -moved / max(1, rect.width()))

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._drag_index is None:
            return
        index = self._drag_index
        self._drag_index = None
        self.frame_drag_settled.emit(index)
```

Add `QPoint` to the `PySide6.QtCore` import as well.

Note the delta is measured from the press point, not from the previous move, so successive move events report an absolute displacement rather than accumulating rounding. The tab must therefore treat it as "position at press plus delta", which Task 7 does.

- [x] **Step 4: Run the tests to verify they pass**

Run: `mise exec -- uv run pytest tests/test_strip.py -v`
Expected: PASS, including the existing tests.

- [x] **Step 5: Run the full gate and commit**

```bash
mise run check
git add src/maskingframe/gui/strip.py tests/test_strip.py
git commit -m "feat(gui): let a strip frame be dragged along the panorama"
```

---

### Task 7: Wire the Split tab

**Files:**
- Modify: `src/maskingframe/gui/split_tab.py`
- Test: `tests/test_split_tab.py`

**Interfaces:**
- Consumes: `pipeline.default_positions`, `pipeline.normalise_positions`, `pipeline.ribbon_thumbnail`, `SourceFacts.positions`, `SourceFacts.window_fraction` (Task 4); `FrameRibbon`, `RIBBON_HEIGHT` (Task 5); `ContactStrip.frame_dragged`, `ContactStrip.frame_drag_settled`, `ContactStrip.set_draggable` (Task 6).
- Produces: `SplitTab.ribbon`, `SplitTab.ribbon_note`, `SplitTab.positions() -> tuple[float, ...]`.

- [x] **Step 1: Write the failing tests**

Add to `tests/test_split_tab.py`:

```python
NO_POSITIONS = "Frames are spread evenly. Load one panorama to place them by hand."


def test_the_ribbon_is_hidden_until_a_panorama_is_loaded(qtbot: QtBot) -> None:
    tab = SplitTab()
    qtbot.addWidget(tab)
    assert not tab.ribbon.isVisibleTo(tab)


def test_loading_a_panorama_shows_the_ribbon(qtbot: QtBot, tmp_path: Path) -> None:
    source = tmp_path / "pano.jpg"
    conftest.synthetic_panorama(2000, 1000).save(source, "JPEG", quality=95)

    tab = SplitTab()
    qtbot.addWidget(tab)
    tab.show()
    tab.source_row.setText(str(source))
    qtbot.waitUntil(lambda: tab.positions() != (), timeout=3000)

    assert tab.ribbon.isVisibleTo(tab)
    assert len(tab.positions()) == 2 or len(tab.positions()) >= 2


def test_folder_mode_hides_the_ribbon_and_says_why(qtbot: QtBot, tmp_path: Path) -> None:
    tab = SplitTab()
    qtbot.addWidget(tab)
    tab.show()
    tab.folder_radio.setChecked(True)
    tab.source_row.setText(str(tmp_path))

    assert not tab.ribbon.isVisibleTo(tab)
    assert tab.ribbon_note.isVisibleTo(tab)
    assert tab.ribbon_note.text() == NO_POSITIONS


def test_dragging_in_the_strip_moves_the_matching_position(
    qtbot: QtBot, tmp_path: Path
) -> None:
    source = tmp_path / "pano.jpg"
    conftest.synthetic_panorama(2000, 1000).save(source, "JPEG", quality=95)

    tab = SplitTab()
    qtbot.addWidget(tab)
    tab.show()
    tab.source_row.setText(str(source))
    qtbot.waitUntil(lambda: tab.positions() != (), timeout=3000)

    before = tab.positions()
    # Strip frame 1 is detail frame 0. A quarter of a frame width to the right.
    tab.strip.frame_dragged.emit(1, 0.25)

    after = tab.positions()
    assert after[0] > before[0]
    assert after[1:] == before[1:]
    # And the ribbon was told, so the two views cannot disagree.
    assert tab.ribbon.positions() == after


def test_the_ribbon_and_the_tab_agree_after_a_ribbon_drag(
    qtbot: QtBot, tmp_path: Path
) -> None:
    source = tmp_path / "pano.jpg"
    conftest.synthetic_panorama(2000, 1000).save(source, "JPEG", quality=95)

    tab = SplitTab()
    qtbot.addWidget(tab)
    tab.show()
    tab.source_row.setText(str(source))
    qtbot.waitUntil(lambda: tab.positions() != (), timeout=3000)

    moved = (0.1, *tab.positions()[1:])
    tab.ribbon.positions_changed.emit(moved)

    assert tab.positions()[0] == pytest.approx(0.1)


def test_a_run_cuts_at_the_chosen_positions(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "pano.jpg"
    conftest.synthetic_panorama(2000, 1000).save(source, "JPEG", quality=95)

    seen: dict[str, object] = {}
    real = pipeline.process_image

    def spy(*args: object, **kwargs: object) -> object:
        seen.update(kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr(pipeline, "process_image", spy)

    tab = SplitTab()
    qtbot.addWidget(tab)
    tab.show()
    tab.source_row.setText(str(source))
    qtbot.waitUntil(lambda: tab.positions() != (), timeout=3000)
    tab.ribbon.positions_changed.emit((0.1, *tab.positions()[1:]))
    tab.dest_row.setText(str(tmp_path / "out"))
    tab.process_images()
    qtbot.waitUntil(lambda: "positions" in seen, timeout=5000)

    assert seen["positions"] == tab.positions()
```

Ensure the module imports `pytest`, `Path`, `pipeline`, `conftest` and `SplitTab` — most are already there; add what is missing.

- [x] **Step 2: Run the tests to verify they fail**

Run: `mise exec -- uv run pytest tests/test_split_tab.py -k "ribbon or position" -v`
Expected: FAIL with `AttributeError: 'SplitTab' object has no attribute 'ribbon'`.

- [x] **Step 3: Build the ribbon into the tab**

In `split_tab.py`, add to the imports:

```python
from maskingframe.gui.ribbon import FrameRibbon
```

Add the constant next to `NO_COUNT`:

```python
NO_POSITIONS = "Frames are spread evenly. Load one panorama to place them by hand."
"""What stands where the ribbon would be when there is nothing to place --
folder mode, or no source. Silence would read as a missing feature rather
than a decision."""
```

In `__init__`, before `self._build()`:

```python
        self._positions: tuple[float, ...] = ()
        self._source_size: tuple[int, int] | None = None
        self._window_fraction = 0.0
        # The positions as they were when a strip drag began. A strip drag
        # reports displacement from the press point, so the tab adds it to
        # where the frame started rather than to wherever it has got to --
        # otherwise every move event would compound the last one.
        self._drag_anchor: tuple[float, ...] = ()
```

At the end of `_build`, replace the two lines that add the strip with:

```python
        # Source above, results below: the ribbon says where the frames come
        # from, the strip says what they are.
        self.ribbon = FrameRibbon(self.columns.table)
        self.ribbon.positions_changed.connect(self._on_positions_changed)
        self.ribbon.positions_settled.connect(self._on_positions_settled)
        self.ribbon.setVisible(False)
        self.columns.table_layout.addWidget(self.ribbon)

        self.ribbon_note = shell.help_label(NO_POSITIONS)
        self.columns.table_layout.addWidget(self.ribbon_note)

        self.columns.table_layout.addSpacing(theme.M)

        # An object lying on the light table, not a panel filling it.
        self.strip = ContactStrip(self.columns.table)
        self.strip.frame_dragged.connect(self._on_frame_dragged)
        self.strip.frame_drag_settled.connect(self._on_frame_drag_settled)
        # No top alignment and no stretch under it: the strip fills the
        # table, so the frames are as large as the window allows.
        self.columns.table_layout.addWidget(self.strip, 1)
```

Add the position handling, after `_refresh_border_preview`:

```python
    def positions(self) -> tuple[float, ...]:
        """Where the detail frames land. The one copy; both views read it."""
        return self._positions

    def _set_positions(self, positions: Sequence[float]) -> None:
        """Adopt a new plan and tell both views about it. GUI thread only.

        Normalised through `pipeline` rather than trusted: a drag is clamped
        by the widget that produced it, but the tab is the only thing that
        knows the source's real size, so the last word on what is inside the
        picture belongs here.
        """
        if self._source_size is None:
            self._positions = tuple(positions)
        else:
            width, height = self._source_size
            self._positions = pipeline.normalise_positions(
                positions, width, height, pipeline.RATIOS[self._ratio_name()]
            )
        self.ribbon.set_plan(self._positions, self._window_fraction)

    def _show_ribbon(self, visible: bool) -> None:
        """The ribbon and the sentence explaining its absence are exclusive."""
        self.ribbon.setVisible(visible)
        self.ribbon_note.setVisible(not visible)
        self.strip.set_draggable(visible)

    def _on_positions_changed(self, positions: tuple[float, ...]) -> None:
        """Every movement of a ribbon drag. Cheap work only."""
        self._set_positions(positions)

    def _on_positions_settled(self, positions: tuple[float, ...]) -> None:
        """The hand has stopped. Now the frames themselves can be redone."""
        self._set_positions(positions)
        self._rerender()

    def _on_frame_dragged(self, index: int, delta: float) -> None:
        """A drag inside strip frame `index`. Frame 0 is the whole panorama.

        The strip reports its delta in frame widths because it has no idea
        how wide the panorama is; here it becomes a fraction of the width.
        """
        detail = index - 1
        if not 0 <= detail < len(self._positions):
            return
        if not self._drag_anchor:
            self._drag_anchor = self._positions
        anchored = list(self._drag_anchor)
        anchored[detail] += delta * self._window_fraction
        self._set_positions(anchored)

    def _on_frame_drag_settled(self, _index: int) -> None:
        self._drag_anchor = ()
        self._rerender()
```

Add `from collections.abc import Sequence` to the imports.

- [x] **Step 4: Fill the ribbon when a source is chosen**

In `_apply_facts`, after the existing readout lines, adopt the plan and load the picture:

```python
        self._source_size = (facts.width, facts.height)
        self._window_fraction = facts.window_fraction
        self._set_positions(facts.positions)
        self._show_ribbon(True)
        self._load_ribbon_picture(token)
```

In `_clear_facts`, put it all back:

```python
        self._positions = ()
        self._source_size = None
        self._window_fraction = 0.0
        self._drag_anchor = ()
        self.ribbon.set_source(None)
        self.ribbon.set_plan((), 0.0)
        self._show_ribbon(False)
```

Add the loader next to the other workers:

```python
    def _load_ribbon_picture(self, token: int) -> None:
        """Decode a small copy of the panorama for the ribbon to draw.

        Off the GUI thread like every other decode here, and behind the same
        inspection token: a user can pick a second file before the first
        picture arrives, and the older one must not land on the newer plan.
        """
        source = self.source_row.text()

        def read() -> Image.Image | None:
            # Worker thread. Returns plain data; touches no widget.
            try:
                return pipeline.ribbon_thumbnail(source)
            except Exception:
                return None

        def done(image: Image.Image | None) -> None:
            if token != self._inspect_token:
                return
            self.ribbon.set_source(image)

        submit(read, done, lambda _error: None)
```

- [x] **Step 5: Pass the positions into the run and the preview**

In `_start_single`, read the plan on the GUI thread beside the style and pass it in:

```python
        style = self._style()
        positions = self._positions or None

        def cut() -> list[Path]:
            # Worker thread. `frame_written.emit` is the only crossing, and
            # Qt queues it to the GUI thread by itself.
            return pipeline.process_image(
                source,
                prefix,
                pipeline.RATIOS[ratio_name],
                on_frame=lambda done, total, path: self.frame_written.emit(done, total, path),
                positions=positions,
                style=style,
            )
```

In `_render`, the same:

```python
        style = self._style()
        positions = self._positions or None
```

and

```python
        def render() -> list[Image.Image]:
            return pipeline.preview_frames(
                source,
                pipeline.RATIOS[ratio_name],
                style,
                cached=True,
                positions=positions,
            )
```

`_start_batch` is left alone: folder mode uses the even default, which is what `positions=None` gives.

- [x] **Step 6: Add the frame-count control**

Task 3's add and remove rules need a way in, or the count stays a derived
default the user cannot override — which the spec says it must be.

Add these tests to `tests/test_split_tab.py`:

```python
def test_adding_a_frame_lands_it_between_the_others(qtbot: QtBot, tmp_path: Path) -> None:
    source = tmp_path / "pano.jpg"
    conftest.synthetic_panorama(2000, 1000).save(source, "JPEG", quality=95)

    tab = SplitTab()
    qtbot.addWidget(tab)
    tab.show()
    tab.source_row.setText(str(source))
    qtbot.waitUntil(lambda: tab.positions() != (), timeout=3000)

    before = tab.positions()
    tab.add_frame()

    after = tab.positions()
    assert len(after) == len(before) + 1
    assert list(after) == sorted(after)


def test_removing_a_frame_takes_the_last_one(qtbot: QtBot, tmp_path: Path) -> None:
    source = tmp_path / "pano.jpg"
    conftest.synthetic_panorama(2000, 1000).save(source, "JPEG", quality=95)

    tab = SplitTab()
    qtbot.addWidget(tab)
    tab.show()
    tab.source_row.setText(str(source))
    qtbot.waitUntil(lambda: tab.positions() != (), timeout=3000)

    tab.add_frame()
    before = tab.positions()
    tab.remove_frame()

    assert tab.positions() == before[:-1]


def test_the_remove_button_is_dead_at_two_frames(qtbot: QtBot, tmp_path: Path) -> None:
    # Two is the floor: one detail frame would just restate frame 1.
    source = tmp_path / "pano.jpg"
    conftest.synthetic_panorama(2000, 1000).save(source, "JPEG", quality=95)

    tab = SplitTab()
    qtbot.addWidget(tab)
    tab.show()
    tab.source_row.setText(str(source))
    qtbot.waitUntil(lambda: tab.positions() != (), timeout=3000)

    while len(tab.positions()) > 2:
        tab.remove_frame()

    assert not tab.remove_btn.isEnabled()
    tab.remove_frame()
    assert len(tab.positions()) == 2
```

Run them first and watch them fail with `AttributeError: 'SplitTab' object has
no attribute 'add_frame'`.

Then, in `_build`, immediately after the `count_label` line, add the pair:

```python
        rail.addSpacing(theme.S)
        counter = QWidget()
        counter_row = QHBoxLayout(counter)
        counter_row.setContentsMargins(0, 0, 0, 0)
        counter_row.setSpacing(theme.S)
        # Secondary, not primary: chinagraph is for marking up, and two more
        # filled blocks of it beside the action would cost that action its
        # primacy. These are chrome.
        self.remove_btn = QPushButton("−")
        self.remove_btn.setObjectName("Secondary")
        self.remove_btn.clicked.connect(self.remove_frame)
        self.add_btn = QPushButton("+")
        self.add_btn.setObjectName("Secondary")
        self.add_btn.clicked.connect(self.add_frame)
        counter_row.addWidget(self.remove_btn)
        counter_row.addWidget(self.add_btn)
        counter_row.addStretch(1)
        rail.addWidget(counter)
```

The minus is U+2212, not a hyphen: beside a `+` at the same size a hyphen sits
too high and reads as a dash rather than an operator.

Add the two methods next to the other position handling:

```python
    def add_frame(self) -> None:
        """One more detail frame, in the widest stretch nothing covers.

        A new frame should land on something nobody is looking at yet, which
        is a judgement `pipeline` already makes; this only supplies the size
        of the source it needs to make it.
        """
        if self._source_size is None or not self._positions:
            return
        width, height = self._source_size
        self._set_positions(
            pipeline.insert_position(
                self._positions, width, height, pipeline.RATIOS[self._ratio_name()]
            )
        )
        self._apply_count_states()
        self._rerender()

    def remove_frame(self) -> None:
        """One fewer, taken from the end. Never below two."""
        if len(self._positions) <= 2:
            return
        self._set_positions(pipeline.drop_position(self._positions))
        self._apply_count_states()
        self._rerender()

    def _apply_count_states(self) -> None:
        """The one place that decides whether the pair is pressable.

        Derived from the plan itself, so it cannot go out of date, and it
        also updates the readouts the count feeds -- the label and the
        button's number both count what a run will actually write.
        """
        placed = len(self._positions)
        self.add_btn.setEnabled(placed > 0)
        self.remove_btn.setEnabled(placed > 2)
        if placed:
            self.count_label.setText(f"{placed + 1} frames")
            self.action_btn.setText(f"Cut {placed + 1} frames")
```

Call `self._apply_count_states()` at the end of `_apply_facts` and at the end
of `_clear_facts`, so the pair is right from the first header read onwards.

The buttons live in the rail's FORMAT section, beside the frame count they
change, rather than on the ribbon: the ribbon is the picture, and hanging
controls on it would put chrome over the photograph.

- [x] **Step 7: Run the tab's tests, then the full gate, then commit**

Run: `mise exec -- uv run pytest tests/test_split_tab.py -v`
Expected: PASS, including every test that was already in the file.

```bash
mise run check
git add src/maskingframe/gui/split_tab.py tests/test_split_tab.py
git commit -m "feat(gui): place the detail frames from the Split tab"
```

---

### Task 8: Documentation

**Files:**
- Modify: `CLAUDE.md`

- [x] **Step 1: Update the architecture notes**

In the `pipeline.py` bullet, after the sentence about re-exports, add:

> It also re-exports the position model (`default_positions`, `normalise_positions`, `insert_position`, `drop_position`, `frame_width`, `position_travel`) for the same reason, and `ribbon_thumbnail()` decodes the small copy of the panorama the ribbon draws — separate from `cached_preview_source()`, which holds a much larger copy for cutting frames from.

In the `gui/` bullet, add `ribbon.py` to the list of modules: "`ribbon.py` (`FrameRibbon`, the whole panorama with a draggable window per detail frame)".

- [x] **Step 2: Add a section on the position model**

Add this after the "Border behaviour worth knowing" section:

```markdown
### Where the detail frames land

A detail frame is one number: its left edge as a fraction of the panorama's
width. The width is derived, not stored — `pano_height * ratio` — so every
detail frame is a full-height crop at exactly the output aspect and moving one
frame never resizes another.

Positions are held ascending, and a frame dragged past its neighbour stops at
it rather than swapping with it: the frames are numbered, and a carousel
running backwards along the picture is confusing. Overlap is allowed, because
two tight crops on one subject is a legitimate choice.

`section_count()` is unchanged and still gives the opening count. It is a first
guess now, not a constraint.

The ribbon (`gui/ribbon.py`) sits above the contact strip and shows where the
frames come from; the strip shows what they are. Both write to one tuple owned
by `SplitTab`, so they cannot disagree. Folder mode hides the ribbon and cuts
with the even default — a position is chosen by looking at one photograph — and
says so where the ribbon would be, because silence would read as a missing
feature. The CLI has no position flags for the same reason.

A source narrower than one output tile (a 1.5:1 image at `1.91:1`) has no
travel at all: every position clamps to zero and the crop is the whole width.
Degenerate, but it must not raise.
```

- [x] **Step 2b: Check the behaviour-changes entry landed**

Task 2 added the detail-frame entry to "Behaviour changes from the pre-refactor scripts". Confirm it is there with `grep -n "full-height crop" CLAUDE.md`; if it is missing, add it now using the wording from Task 2, Step 7.

- [x] **Step 3: Run the full gate and commit**

```bash
mise run check
git add CLAUDE.md
git commit -m "docs: record the detail frame position model"
```

---

## Verification

Every box above is ticked, and:

- [x] `mise run check` passes on a clean tree.
- [x] `mise exec -- uv run maskingframe tests/fixtures/golden_wide.jpg /tmp/verify --ratio 1.91:1` writes a padded frame plus detail frames, and each detail frame is 1080x566.
- [x] Opening `mise run gui`, loading a panorama in the Split tab, dragging a ribbon window and pressing Preview shows the frames from the chosen positions.
- [x] Switching to "Whole folder" hides the ribbon and shows the sentence in its place.
- [x] `grep -rn "import geometry\|from maskingframe import geometry" src/maskingframe/gui/` returns nothing.
