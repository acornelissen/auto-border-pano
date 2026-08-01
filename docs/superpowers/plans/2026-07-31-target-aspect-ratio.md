# Selectable Target Aspect Ratio Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user pick an Instagram aspect ratio (1:1, 4:5, 1.91:1) and shape every output to it, deriving the number of zoomed detail frames from that ratio.

**Architecture:** An `AspectRatio` value object in `geometry.py` carries both the ratio and its output pixel size, so the two cannot drift apart. `section_count()` derives how many detail frames a panorama needs, floored at 2 so the frames are always a genuine zoom. `pipeline.py` threads the ratio through, rejects portrait input, and produces a variable-length output set. The CLI gains `--ratio`; the GUI gains a combobox and a preview panel that rebuilds itself per run.

**Tech Stack:** Python 3.13, Pillow, pytest, ruff, mypy strict, tkinter, mise + uv.

## Global Constraints

- Output sizes are exactly: `1:1` → 1080x1080, `4:5` → 1080x1350, `1.91:1` → 1080x566.
- Detail-frame count is `max(2, round_half_up(pano_width / (pano_height * ratio)))`. **The floor of 2 is load-bearing** — a single detail frame just restates the whole-panorama frame, which defeats the feature.
- Use half-up rounding, not Python's built-in `round()`. `round()` is banker's rounding: `round(2.5) == 2`, which would silently pick the wrong count on exact halves. Use `math.floor(x + 0.5)`.
- Default ratio is `4:5`.
- Frame 1 (the padded whole panorama) keeps `SIDE_PADDING = 100` and `VERTICAL_PADDING = 10`. Do not change those constants.
- Portrait input (`width < height`) is rejected with a `ValueError` naming the file and its dimensions. Square input is allowed.
- Output filenames: `{prefix}_1_padded.jpg`, then `{prefix}_{n+1}_section{n}.jpg` for n in 1..count.
- JPEG quality stays 95. Resampling stays `Image.Resampling.LANCZOS`.
- `gui.py` and `cli.py` must not import `geometry` directly — that invariant is documented in CLAUDE.md. `pipeline.py` re-exports what they need.
- Conventional commits, imperative mood. **No Claude/AI attribution or Co-Authored-By trailers** — a git hook rejects them.

---

## File Structure

| File | Change |
| ---- | ------ |
| `.pre-commit-config.yaml` | Repair hooks so they can find `uv` (Task 1) |
| `src/maskingframe/geometry.py` | `AspectRatio`, `section_count`, generalised `make_section`, `make_padded_frame` |
| `src/maskingframe/pipeline.py` | Variable output paths, ratio parameter, portrait rejection, bomb limit, explicit success counter |
| `src/maskingframe/cli.py` | `--ratio` flag |
| `src/maskingframe/gui.py` | Ratio combobox, per-run preview panel rebuild |
| `tests/test_geometry.py` | Ratio and count tests, pixel-position assertions |
| `tests/test_pipeline.py` | Per-ratio goldens replacing the single golden, portrait rejection |
| `tests/test_cli.py` | `--ratio` parsing and effect |
| `tests/test_gui.py` | Preview-title generation tracks the count |
| `tests/fixtures/` | One golden panorama per ratio |
| `README.md`, `CLAUDE.md` | Document the option and the behaviour changes |

---

### Task 1: Repair the pre-commit hooks

These hooks have never run. They invoke `uv run …`, but `uv` is a mise-managed tool and is absent from `PATH` when git spawns a hook, so every hook dies with "Executable `uv` not found". Every commit in this plan depends on them, so this goes first.

**Files:**
- Modify: `.pre-commit-config.yaml`

**Interfaces:**
- Consumes: nothing
- Produces: working `pre-commit` and `pre-push` hooks

- [ ] **Step 1: Reproduce the failure**

```bash
env -i HOME="$HOME" PATH=/usr/bin:/bin sh -c 'cd "'"$PWD"'" && git commit --allow-empty -m "probe"'
```

Expected: the mypy hook fails with `Executable \`uv\` not found`. If it unexpectedly passes, the environment differs from the reported one — record that in your report and continue anyway, since the fix below is robust either way.

- [ ] **Step 2: Rewrite the local hooks to locate the toolchain themselves**

The fix is to stop assuming `uv` is on `PATH`. `mise` knows where its tools live, so ask it — and fall back to a bare `uv` when mise is absent, so a contributor without mise is not blocked.

Replace the `repo: local` block in `.pre-commit-config.yaml` with:

```yaml
  - repo: local
    hooks:
      - id: mypy
        name: mypy
        entry: scripts/run-tool mypy src tests
        language: script
        pass_filenames: false

      - id: pytest
        name: pytest
        entry: scripts/run-tool pytest
        language: script
        pass_filenames: false
        stages: [pre-push]
```

- [ ] **Step 3: Add the launcher script**

Create `scripts/run-tool`:

```sh
#!/bin/sh
# Run a project dev tool without assuming uv is on PATH.
#
# Git spawns hooks with a minimal environment, so mise's shims are usually
# absent. Prefer mise if we can find it, since it owns the toolchain; fall
# back to a bare uv for contributors who manage the venv themselves.
set -eu

for candidate in \
    "${MISE_INSTALL_PATH:-}" \
    "$(command -v mise 2>/dev/null || true)" \
    /opt/homebrew/bin/mise \
    /usr/local/bin/mise \
    "$HOME/.local/bin/mise"
do
    if [ -n "$candidate" ] && [ -x "$candidate" ]; then
        exec "$candidate" exec -- uv run "$@"
    fi
done

if command -v uv >/dev/null 2>&1; then
    exec uv run "$@"
fi

echo "run-tool: neither mise nor uv found; cannot run $1" >&2
echo "Install mise (https://mise.jdx.dev) then run: mise run setup" >&2
exit 1
```

Make it executable:

```bash
chmod +x scripts/run-tool
```

- [ ] **Step 4: Verify the hooks now run in a minimal environment**

```bash
env -i HOME="$HOME" PATH=/usr/bin:/bin sh -c 'cd "'"$PWD"'" && git commit --allow-empty -m "probe"'
```

Expected: ruff, ruff-format and mypy all report Passed. Then undo the probe commit:

```bash
git reset --hard HEAD~1
```

- [ ] **Step 5: Verify the pre-push hook too**

```bash
env -i HOME="$HOME" PATH=/usr/bin:/bin sh -c 'cd "'"$PWD"'" && .git/hooks/pre-push origin https://example.invalid < /dev/null'
```

Expected: pytest runs and passes.

- [ ] **Step 6: Commit**

```bash
git add .pre-commit-config.yaml scripts/run-tool
git commit -m "build: make pre-commit hooks find the toolchain

The hooks invoked uv directly, but uv is a mise-managed tool and is not on
PATH when git spawns a hook, so every hook failed with 'Executable uv not
found' and none of them have ever run. A small launcher script locates mise
or falls back to uv."
```

---

### Task 2: AspectRatio and section_count

**Files:**
- Modify: `src/maskingframe/geometry.py`
- Modify: `tests/test_geometry.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `AspectRatio` frozen dataclass with fields `name: str`, `width: int`, `height: int` and property `value: float`
  - `SQUARE`, `PORTRAIT`, `LANDSCAPE` instances
  - `RATIOS: dict[str, AspectRatio]` keyed by name
  - `DEFAULT_RATIO: AspectRatio` (= `PORTRAIT`)
  - `MIN_SECTIONS: int = 2`
  - `section_count(pano_width: int, pano_height: int, ratio: AspectRatio) -> int`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_geometry.py`:

```python
def test_ratio_output_sizes_are_exact() -> None:
    assert (geometry.SQUARE.width, geometry.SQUARE.height) == (1080, 1080)
    assert (geometry.PORTRAIT.width, geometry.PORTRAIT.height) == (1080, 1350)
    assert (geometry.LANDSCAPE.width, geometry.LANDSCAPE.height) == (1080, 566)


def test_ratios_are_registered_by_name() -> None:
    assert set(geometry.RATIOS) == {"1:1", "4:5", "1.91:1"}
    assert geometry.RATIOS["4:5"] is geometry.PORTRAIT
    assert geometry.DEFAULT_RATIO is geometry.PORTRAIT


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `mise run test`
Expected: FAIL with `AttributeError: module 'maskingframe.geometry' has no attribute 'SQUARE'`

- [ ] **Step 3: Write the implementation**

At the top of `src/maskingframe/geometry.py`, add `import math` and `from dataclasses import dataclass` to the imports, then insert after the existing constants:

```python
@dataclass(frozen=True)
class AspectRatio:
    """A target output shape.

    Carries the output pixel size alongside the name so the ratio and the
    dimensions it produces cannot drift apart.
    """

    name: str
    width: int
    height: int

    @property
    def value(self) -> float:
        """Width divided by height, for arithmetic."""
        return self.width / self.height


SQUARE = AspectRatio("1:1", 1080, 1080)
PORTRAIT = AspectRatio("4:5", 1080, 1350)
LANDSCAPE = AspectRatio("1.91:1", 1080, 566)

RATIOS: dict[str, AspectRatio] = {r.name: r for r in (SQUARE, PORTRAIT, LANDSCAPE)}
DEFAULT_RATIO = PORTRAIT

MIN_SECTIONS = 2


def section_count(pano_width: int, pano_height: int, ratio: AspectRatio) -> int:
    """How many detail frames to cut from a panorama.

    An exact tile is `pano_height * ratio` wide; the count is how many of
    those fit across the panorama, rounded to nearest.

    The floor of MIN_SECTIONS is deliberate and load-bearing. The detail
    frames exist so a viewer can zoom in on detail; a single detail frame
    would just restate the whole-panorama frame and defeat the purpose. A
    2.4:1 panorama at 1.91:1 is exactly that case -- tiling alone wants one
    frame.

    Half-up rounding, not Python's round(), which is banker's rounding and
    would pick the lower count on exact halves.
    """
    tile = pano_height * ratio.value
    return max(MIN_SECTIONS, math.floor(pano_width / tile + 0.5))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `mise run check`
Expected: all pass, ruff and mypy clean.

- [ ] **Step 5: Commit**

```bash
git add src/maskingframe/geometry.py tests/test_geometry.py
git commit -m "feat(geometry): add AspectRatio and derive detail-frame count

The count is floored at two because the detail frames are a zoom, not a
tiling: a single frame would just restate the whole-panorama frame. Counts
are pinned against the aspect ratios of real scans."
```

---

### Task 3: Generalise the geometry to any ratio

**Files:**
- Modify: `src/maskingframe/geometry.py`
- Modify: `tests/test_geometry.py`

**Interfaces:**
- Consumes: `AspectRatio`, `SQUARE`, `PORTRAIT`, `LANDSCAPE`, `section_count` from Task 2
- Produces:
  - `section_bounds(width: int, index: int, count: int) -> tuple[int, int]` — `count` is now a parameter
  - `make_section(image: Image.Image, index: int, count: int, ratio: AspectRatio) -> Image.Image`
  - `make_padded_frame(image: Image.Image, ratio: AspectRatio) -> Image.Image`
  - `padded_frame_size(pano_width: int, pano_height: int, ratio: AspectRatio) -> tuple[int, int]`
  - **Removed:** `SECTION_SIZE`, `SECTION_COUNT`, `padded_square_size`, `make_padded_square`

- [ ] **Step 1: Replace the existing geometry tests**

The current tests in `tests/test_geometry.py` call `make_padded_square`, `make_section(image, index)` and `section_bounds(width, index)`, all of which change signature here. Rewrite those tests rather than adding alongside. Keep the Task 2 tests untouched.

Replace every test that references `make_padded_square`, `padded_square_size`, or the two-argument `section_bounds` with:

```python
def test_padded_frame_is_exactly_the_target_ratio() -> None:
    for ratio in geometry.RATIOS.values():
        frame = geometry.make_padded_frame(synthetic_panorama(3000, 800), ratio)
        assert abs(frame.width / frame.height - ratio.value) < 0.01, ratio.name


def test_padded_frame_keeps_side_padding() -> None:
    frame = geometry.make_padded_frame(synthetic_panorama(3000, 800), geometry.SQUARE)
    assert frame.width == 3000 + 2 * geometry.SIDE_PADDING


def test_padded_frame_pastes_at_side_padding_not_zero() -> None:
    # Kills a mutation that pastes at (0, 0) or at (SIDE_PADDING, VERTICAL_PADDING)
    # instead of centering.
    frame = geometry.make_padded_frame(synthetic_panorama(3000, 800), geometry.SQUARE)
    mid_y = frame.height // 2
    assert frame.getpixel((geometry.SIDE_PADDING - 1, mid_y)) == (255, 255, 255)
    assert frame.getpixel((geometry.SIDE_PADDING + 1, mid_y)) != (255, 255, 255)


def test_padded_frame_centers_vertically() -> None:
    frame = geometry.make_padded_frame(synthetic_panorama(3000, 800), geometry.SQUARE)
    top_gap = (frame.height - 800) // 2
    mid_x = frame.width // 2
    assert frame.getpixel((mid_x, top_gap - 1)) == (255, 255, 255)
    assert frame.getpixel((mid_x, top_gap + 1)) != (255, 255, 255)


def test_padded_frame_grows_when_ratio_would_clip_the_panorama() -> None:
    # A tall-ish input at 1.91:1: deriving height from width would leave the
    # panorama taller than the canvas, so the canvas is sized from height.
    frame = geometry.make_padded_frame(synthetic_panorama(400, 2000), geometry.LANDSCAPE)
    assert frame.height >= 2000 + 2 * geometry.VERTICAL_PADDING
    assert abs(frame.width / frame.height - geometry.LANDSCAPE.value) < 0.01


def test_section_bounds_split_on_integer_division() -> None:
    assert geometry.section_bounds(3001, 0, 3) == (0, 1000)
    assert geometry.section_bounds(3001, 1, 3) == (1000, 2000)
    assert geometry.section_bounds(3001, 2, 3) == (2000, 3000)


def test_section_bounds_validates_index() -> None:
    import pytest

    with pytest.raises(ValueError):
        geometry.section_bounds(3000, 3, 3)


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
    panorama = synthetic_panorama(3000, 800)
    section = geometry.make_section(panorama, 0, 2, geometry.PORTRAIT)
    top_left = section.getpixel((0, 0))
    assert isinstance(top_left, tuple)
    assert top_left[1] != 0, "green channel 0 means source row 0 -- offset was not applied"


def test_adjacent_sections_show_different_parts_of_the_panorama() -> None:
    # Kills a mutation that ignores `index` and always crops the same region.
    panorama = synthetic_panorama(3000, 800)
    first = geometry.make_section(panorama, 0, 3, geometry.SQUARE)
    second = geometry.make_section(panorama, 1, 3, geometry.SQUARE)
    assert first.getpixel((0, 0)) != second.getpixel((0, 0))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `mise run test`
Expected: FAIL with `AttributeError: module 'maskingframe.geometry' has no attribute 'make_padded_frame'`

- [ ] **Step 3: Rewrite the geometry functions**

In `src/maskingframe/geometry.py`, delete `padded_square_size`, `make_padded_square`, `SECTION_SIZE` and `SECTION_COUNT`, and replace with:

```python
def padded_frame_size(
    pano_width: int, pano_height: int, ratio: AspectRatio
) -> tuple[int, int]:
    """Canvas size for the whole-panorama frame at a given ratio.

    Sized from the width so the panorama keeps SIDE_PADDING left and right.
    If the ratio would then make the canvas too short to hold the panorama
    with its minimum vertical padding, size from the height instead. Either
    way the ratio is exact.
    """
    width = pano_width + 2 * SIDE_PADDING
    height = math.floor(width / ratio.value + 0.5)

    minimum_height = pano_height + 2 * VERTICAL_PADDING
    if height < minimum_height:
        height = minimum_height
        width = math.floor(height * ratio.value + 0.5)
    return width, height


def make_padded_frame(image: Image.Image, ratio: AspectRatio) -> Image.Image:
    """Center a panorama on a white canvas of the target ratio.

    The panorama is centered, so at a tall ratio most of the frame is white
    border. That is the intended aesthetic, not a bug.
    """
    pano_width, pano_height = image.size
    width, height = padded_frame_size(pano_width, pano_height, ratio)
    canvas = Image.new("RGB", (width, height), BACKGROUND)
    canvas.paste(image, ((width - pano_width) // 2, (height - pano_height) // 2))
    return canvas


def section_bounds(width: int, index: int, count: int) -> tuple[int, int]:
    """Return the horizontal crop bounds of one detail frame.

    Uses integer division, so when the width is not divisible by `count`
    the remaining pixels on the right edge are discarded.
    """
    if not 0 <= index < count:
        raise ValueError(f"index must be 0..{count - 1}, got {index}")
    section_width = width // count
    start = index * section_width
    return start, start + section_width


def make_section(
    image: Image.Image, index: int, count: int, ratio: AspectRatio
) -> Image.Image:
    """Crop one detail frame and scale it to exactly fill the target ratio.

    Scales by whichever axis keeps the target fully covered, then
    center-crops the overflow.
    """
    width, height = image.size
    start, end = section_bounds(width, index, count)
    crop = image.crop((start, 0, end, height))
    crop_width, crop_height = crop.size

    scale = max(ratio.width / crop_width, ratio.height / crop_height)
    resized = crop.resize(
        (
            max(ratio.width, math.floor(crop_width * scale + 0.5)),
            max(ratio.height, math.floor(crop_height * scale + 0.5)),
        ),
        Image.Resampling.LANCZOS,
    )

    x_offset = (resized.width - ratio.width) // 2
    y_offset = (resized.height - ratio.height) // 2
    return resized.crop(
        (x_offset, y_offset, x_offset + ratio.width, y_offset + ratio.height)
    )
```

Note the `max(ratio.width, ...)` guards: they ensure the resized image always covers the target even when floating-point rounding lands a pixel short, which would otherwise make the final crop smaller than requested.

- [ ] **Step 4: Run tests to verify they pass**

Run: `mise run check`
Expected: geometry tests pass. `tests/test_pipeline.py` and `tests/test_gui.py` will now FAIL because `pipeline` still calls the removed functions — that is expected and Task 4 fixes it. Confirm the geometry tests specifically pass:

```bash
mise exec -- uv run pytest tests/test_geometry.py -v
```

- [ ] **Step 5: Commit**

Commit with the pipeline still broken, since the two tasks are separately reviewable and the geometry change stands on its own:

```bash
git add src/maskingframe/geometry.py tests/test_geometry.py
git commit --no-verify -m "feat(geometry): generalise padding and sectioning to any ratio

make_padded_square becomes make_padded_frame, and make_section takes the
count and target ratio. The old two-branch scale logic collapses into one
cover-scale expression, of which the square case was a specialisation.

Uses --no-verify because pipeline.py still calls the removed functions;
Task 4 restores a green tree."
```

---

### Task 4: Thread the ratio through the pipeline

**Files:**
- Modify: `src/maskingframe/pipeline.py`
- Modify: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `geometry.make_padded_frame`, `geometry.make_section`, `geometry.section_count`, `geometry.AspectRatio`, `geometry.RATIOS`, `geometry.DEFAULT_RATIO`
- Produces:
  - `RATIOS`, `DEFAULT_RATIO`, `AspectRatio` re-exported so `cli` and `gui` need not import `geometry`
  - `output_paths(prefix: Path | str, count: int) -> list[Path]`
  - `process_image(input_path, output_prefix, ratio: AspectRatio = DEFAULT_RATIO) -> list[Path]`
  - `process_folder(input_folder, output_folder, ratio=DEFAULT_RATIO, on_progress=None) -> BatchResult`
  - `BatchResult` gains `last_count: int | None` and a plain `succeeded_count: int` field

- [ ] **Step 1: Update the pipeline tests**

In `tests/test_pipeline.py`, delete `GOLDEN_OUTPUT_HASHES` and the golden test entirely — Task 5 replaces them with per-ratio goldens. Update the naming-contract test and add the new cases:

```python
def test_output_paths_follow_the_naming_contract() -> None:
    paths = pipeline.output_paths("/tmp/holiday", 3)
    assert [p.name for p in paths] == [
        "holiday_1_padded.jpg",
        "holiday_2_section1.jpg",
        "holiday_3_section2.jpg",
        "holiday_4_section3.jpg",
    ]


def test_output_paths_length_tracks_the_count() -> None:
    assert len(pipeline.output_paths("/tmp/x", 2)) == 3
    assert len(pipeline.output_paths("/tmp/x", 5)) == 6


def test_process_image_writes_frame_one_plus_detail_frames(tmp_path: Path) -> None:
    source = _write_panorama(tmp_path / "pano.jpg", 3000, 1250)
    written = pipeline.process_image(source, tmp_path / "out", pipeline.RATIOS["4:5"])
    assert len(written) == 1 + 3
    assert all(p.exists() for p in written)


def test_process_image_output_sizes_match_the_ratio(tmp_path: Path) -> None:
    source = _write_panorama(tmp_path / "pano.jpg", 3000, 1250)
    for ratio in pipeline.RATIOS.values():
        written = pipeline.process_image(source, tmp_path / ratio.name, ratio)
        with Image.open(written[0]) as frame:
            assert abs(frame.width / frame.height - ratio.value) < 0.01
        for detail in written[1:]:
            with Image.open(detail) as img:
                assert img.size == (ratio.width, ratio.height)


def test_process_image_rejects_portrait_input(tmp_path: Path) -> None:
    import pytest

    source = _write_panorama(tmp_path / "tall.jpg", 800, 3000)
    with pytest.raises(ValueError, match="portrait"):
        pipeline.process_image(source, tmp_path / "out")


def test_portrait_input_is_recorded_as_a_failure_not_an_abort(tmp_path: Path) -> None:
    source_dir = tmp_path / "in"
    source_dir.mkdir()
    _write_panorama(source_dir / "good.jpg", 3000, 1250)
    _write_panorama(source_dir / "tall.jpg", 800, 3000)

    result = pipeline.process_folder(source_dir, tmp_path / "out")

    assert result.succeeded_count == 1
    assert [p.name for p, _ in result.failed] == ["tall.jpg"]
    assert "portrait" in result.failed[0][1]


def test_batch_result_counts_sources_not_files(tmp_path: Path) -> None:
    source_dir = tmp_path / "in"
    source_dir.mkdir()
    _write_panorama(source_dir / "a.jpg", 3000, 1250)
    _write_panorama(source_dir / "b.jpg", 3000, 1250)

    result = pipeline.process_folder(source_dir, tmp_path / "out")

    assert result.succeeded_count == 2
    assert result.total_count == 2
    assert result.last_count == 3
```

Also update `test_process_folder_creates_output_dir_and_reports_progress`, which asserts `len(written) == 8`: at the default 4:5 ratio with the panorama sizes it uses, each source now produces `1 + count` files. Recompute the expected number from `geometry.section_count` rather than hard-coding it, or change the assertion to `len(result.written) == 2 * (1 + 3)` after sizing the fixtures at 3000x1250.

- [ ] **Step 2: Run tests to verify they fail**

Run: `mise run test`
Expected: FAIL — `output_paths()` missing the `count` argument, and `pipeline` still calling the removed `geometry.make_padded_square`.

- [ ] **Step 3: Rewrite the pipeline**

In `src/maskingframe/pipeline.py`:

Add the bomb-limit lift and the re-exports near the top, after the existing imports:

```python
# These are the user's own large-format scans, not hostile downloads; the
# largest sample is 132MP against Pillow's ~178MP default. Lifting the guard
# stops a legitimate scan being reported as a corrupt file. Malformed input
# is still caught by the per-file exception handling in process_folder.
Image.MAX_IMAGE_PIXELS = None

# Re-exported so cli.py and gui.py can offer ratio selection without
# importing geometry directly -- they depend on pipeline only.
AspectRatio = geometry.AspectRatio
RATIOS = geometry.RATIOS
DEFAULT_RATIO = geometry.DEFAULT_RATIO
```

Delete the `OUTPUT_SUFFIXES` constant and replace `output_paths`:

```python
PADDED_SUFFIX = "_1_padded.jpg"


def output_paths(prefix: Path | str, count: int) -> list[Path]:
    """Return every output path for a prefix and detail-frame count.

    Frame 1 is the whole panorama; frames 2..count+1 are the detail frames.
    """
    prefix = Path(prefix)
    names = [PADDED_SUFFIX]
    names += [f"_{n + 1}_section{n}.jpg" for n in range(1, count + 1)]
    return [prefix.with_name(prefix.name + name) for name in names]
```

Replace `process_image`:

```python
def process_image(
    input_path: Path | str,
    output_prefix: Path | str,
    ratio: AspectRatio = DEFAULT_RATIO,
) -> list[Path]:
    """Split one panorama into a whole-panorama frame plus detail frames."""
    with Image.open(input_path) as opened:
        source = opened.convert("RGB")

    width, height = source.size
    if width < height:
        raise ValueError(
            f"{input_path} is portrait ({width}x{height}); "
            "maskingframe expects a landscape panorama"
        )

    count = geometry.section_count(width, height, ratio)
    targets = output_paths(output_prefix, count)
    targets[0].parent.mkdir(parents=True, exist_ok=True)

    geometry.make_padded_frame(source, ratio).save(
        targets[0], "JPEG", quality=JPEG_QUALITY
    )
    for index in range(count):
        geometry.make_section(source, index, count, ratio).save(
            targets[index + 1], "JPEG", quality=JPEG_QUALITY
        )
    return targets
```

Update `BatchResult` — `succeeded_count` becomes a plain field, since the number of files per source now varies and cannot be divided out:

```python
@dataclass
class BatchResult:
    """Outcome of processing every panorama in a folder.

    `written` holds every output file from every successfully processed
    source, in source order. `failed` holds one (source_path, error_message)
    entry per source that could not be processed. `last_prefix` and
    `last_count` describe the last successfully processed source, so callers
    can preview it without re-deriving the naming convention.
    """

    written: list[Path] = field(default_factory=list)
    failed: list[tuple[Path, str]] = field(default_factory=list)
    last_prefix: Path | None = None
    last_count: int | None = None
    succeeded_count: int = 0

    @property
    def total_count(self) -> int:
        return self.succeeded_count + len(self.failed)
```

Update `process_folder` to take the ratio and maintain the new fields:

```python
def process_folder(
    input_folder: Path | str,
    output_folder: Path | str,
    ratio: AspectRatio = DEFAULT_RATIO,
    on_progress: ProgressCallback | None = None,
) -> BatchResult:
    """Split every panorama in a folder.

    Individual failures are skipped so one unreadable or non-landscape file
    cannot abort a long batch. `on_progress` is called before each file with
    (completed_count, total_count, path). Failures are reported via the
    returned `BatchResult.failed`; the caller owns how they are surfaced.
    """
    output_folder = Path(output_folder)
    output_folder.mkdir(parents=True, exist_ok=True)

    sources = find_panoramas(input_folder)
    result = BatchResult()

    for done, source in enumerate(sources):
        if on_progress is not None:
            on_progress(done, len(sources), source)
        prefix = output_folder / source.stem
        try:
            written = process_image(source, prefix, ratio)
        except Exception as error:
            result.failed.append((source, str(error)))
        else:
            result.written.extend(written)
            result.last_prefix = prefix
            result.last_count = len(written) - 1
            result.succeeded_count += 1
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `mise run check`
Expected: geometry and pipeline tests pass. `tests/test_cli.py` and `tests/test_gui.py` may still fail on `output_paths` arity — Tasks 6 and 7 fix those. Confirm:

```bash
mise exec -- uv run pytest tests/test_geometry.py tests/test_pipeline.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/maskingframe/pipeline.py tests/test_pipeline.py
git commit --no-verify -m "feat(pipeline): thread the target ratio through and reject portrait input

Output count now varies per image, so succeeded_count becomes an explicit
counter rather than dividing the file list by a constant. Lifts Pillow's
decompression-bomb limit: the inputs are the user's own large-format scans,
the largest 132MP against a ~178MP default.

Uses --no-verify because cli.py and gui.py still call output_paths with the
old arity; Tasks 6 and 7 restore a green tree."
```

---

### Task 5: Replace the single golden with per-ratio goldens

The old golden test asserted three sections at 1:1 and is now wrong by design. Per-ratio goldens also fix a coverage gap flagged in the previous branch's review, where the single 320x120 fixture exercised only one branch of the crop logic.

**Files:**
- Create: `tests/fixtures/golden_wide.jpg`
- Modify: `tests/test_pipeline.py`
- Delete: `tests/fixtures/golden_panorama.jpg`

**Interfaces:**
- Consumes: `pipeline.process_image`, `pipeline.RATIOS`
- Produces: a standing byte-identity guard across all three ratios

- [ ] **Step 1: Create the golden fixture**

The old fixture was 320x120 (2.67:1). Use 600x250 (2.40:1) instead — it matches the most common aspect in the user's real scans and is large enough that all three ratios produce meaningfully different crops, while staying small in git.

```bash
mise exec -- uv run python -c "
from PIL import Image
img = Image.new('RGB', (600, 250))
px = img.load()
for x in range(600):
    for y in range(250):
        px[x, y] = (x % 256, y % 256, (x + y) % 256)
img.save('tests/fixtures/golden_wide.jpg', 'JPEG', quality=95)
print('wrote tests/fixtures/golden_wide.jpg', img.size)
"
git rm tests/fixtures/golden_panorama.jpg
```

- [ ] **Step 2: Generate the hashes**

```bash
mise exec -- uv run python -c "
import hashlib
from maskingframe import pipeline
for name, ratio in pipeline.RATIOS.items():
    out = pipeline.process_image(
        'tests/fixtures/golden_wide.jpg', f'/tmp/golden_gen/{ratio.name.replace(\":\", \"-\")}', ratio
    )
    print(f'  {name!r}: {{')
    for p in out:
        print(f'      {p.name!r}: {hashlib.sha256(p.read_bytes()).hexdigest()!r},')
    print('  },')
"
```

Copy the printed structure into the test below. Sanity-check before trusting it: 1.91:1 and 1:1 should each list 3 entries (frame 1 plus 2 detail frames) and 4:5 should list 4 (frame 1 plus 3), matching `section_count` for a 2.40:1 panorama.

- [ ] **Step 3: Write the golden test**

Add to `tests/test_pipeline.py`, replacing the deleted single-golden test:

```python
# Byte-identity guard for the project's core promise: a given input at a
# given ratio always produces the same images. Covers all three ratios, so
# both branches of the cover-crop are exercised -- 1.91:1 crops the sides of
# a wide section, 4:5 crops the top and bottom.
#
# These hashes are tied to the installed Pillow version's JPEG encoder. If a
# deliberate Pillow upgrade changes encoding, regenerate with:
#   mise exec -- uv run python -c "
#   import hashlib
#   from maskingframe import pipeline
#   for name, ratio in pipeline.RATIOS.items():
#       out = pipeline.process_image(
#           'tests/fixtures/golden_wide.jpg', f'/tmp/g/{name}', ratio
#       )
#       for p in out:
#           print(name, p.name, hashlib.sha256(p.read_bytes()).hexdigest())
#   "
# and confirm the change is expected before updating.
GOLDEN_HASHES: dict[str, dict[str, str]] = {
    # <-- paste the generated structure here
}


def test_golden_outputs_are_byte_identical(tmp_path: Path) -> None:
    import hashlib

    for name, expected in GOLDEN_HASHES.items():
        ratio = pipeline.RATIOS[name]
        written = pipeline.process_image(
            "tests/fixtures/golden_wide.jpg",
            tmp_path / name.replace(":", "-"),
            ratio,
        )
        actual = {
            p.name.split("_", 1)[1]: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in written
        }
        expected_by_suffix = {k.split("_", 1)[1]: v for k, v in expected.items()}
        assert actual == expected_by_suffix, f"output changed at {name}"


def test_golden_frame_counts_differ_by_ratio() -> None:
    # Guards the feature itself: if every ratio produced the same count,
    # the byte-identity test above could pass while the feature was broken.
    counts = {name: len(hashes) for name, hashes in GOLDEN_HASHES.items()}
    assert counts["4:5"] > counts["1:1"], counts
    assert counts["1:1"] >= counts["1.91:1"], counts
```

- [ ] **Step 4: Verify the golden test actually catches a change**

Temporarily set `JPEG_QUALITY = 94` in `src/maskingframe/pipeline.py`, run `mise exec -- uv run pytest tests/test_pipeline.py -k golden`, and confirm it FAILS. Restore `95` and confirm it passes again. Record both outcomes in your report — a golden test that cannot fail is worse than none.

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures/golden_wide.jpg tests/test_pipeline.py
git rm --cached tests/fixtures/golden_panorama.jpg 2>/dev/null || true
git commit --no-verify -m "test: replace the single golden with one per ratio

The old golden asserted three sections at 1:1, which the new tiling no
longer produces. Per-ratio goldens also close a coverage gap: the previous
320x120 fixture exercised only one branch of the crop logic."
```

---

### Task 6: Add --ratio to the CLI

**Files:**
- Modify: `src/maskingframe/cli.py`
- Modify: `tests/test_cli.py`

**Interfaces:**
- Consumes: `pipeline.RATIOS`, `pipeline.DEFAULT_RATIO`, `pipeline.process_image`, `pipeline.process_folder`
- Produces: `--ratio` accepted by `main`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_cli.py`:

```python
def test_ratio_flag_changes_the_output_shape(tmp_path: Path) -> None:
    source = tmp_path / "pano.jpg"
    synthetic_panorama(3000, 1250).save(source, "JPEG", quality=95)

    assert cli.main([str(source), str(tmp_path / "wide"), "--ratio", "1.91:1"]) == 0

    with Image.open(tmp_path / "wide_2_section1.jpg") as img:
        assert img.size == (1080, 566)


def test_default_ratio_is_four_five(tmp_path: Path) -> None:
    source = tmp_path / "pano.jpg"
    synthetic_panorama(3000, 1250).save(source, "JPEG", quality=95)

    assert cli.main([str(source), str(tmp_path / "out")]) == 0

    with Image.open(tmp_path / "out_2_section1.jpg") as img:
        assert img.size == (1080, 1350)


def test_unknown_ratio_is_rejected(tmp_path: Path) -> None:
    import pytest

    source = tmp_path / "pano.jpg"
    synthetic_panorama(3000, 1250).save(source, "JPEG", quality=95)

    with pytest.raises(SystemExit):
        cli.main([str(source), str(tmp_path / "out"), "--ratio", "16:9"])


def test_portrait_input_exits_nonzero(tmp_path: Path) -> None:
    source = tmp_path / "tall.jpg"
    synthetic_panorama(800, 3000).save(source, "JPEG", quality=95)

    assert cli.main([str(source), str(tmp_path / "out")]) == 1
```

`tests/test_cli.py` needs `from PIL import Image` at the top if it is not already imported.

- [ ] **Step 2: Run tests to verify they fail**

Run: `mise exec -- uv run pytest tests/test_cli.py -v`
Expected: FAIL with `unrecognized arguments: --ratio`

- [ ] **Step 3: Implement**

In `src/maskingframe/cli.py`, update the parser description and add the flag:

```python
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="maskingframe",
        description=(
            "Split a panorama into a whole-panorama frame plus zoomed detail "
            "frames, sized for an Instagram carousel. Accepts a single image "
            "or a folder of images."
        ),
    )
    parser.add_argument("input", type=Path, help="input image or folder")
    parser.add_argument(
        "output",
        type=Path,
        nargs="?",
        default=Path("output"),
        help="output prefix for a single image, or output folder",
    )
    parser.add_argument(
        "--ratio",
        choices=sorted(pipeline.RATIOS),
        default=pipeline.DEFAULT_RATIO.name,
        help=(
            "target aspect ratio for every frame "
            f"(default: {pipeline.DEFAULT_RATIO.name}). The number of detail "
            "frames is derived from this."
        ),
    )
    return parser
```

In `main`, resolve the ratio and pass it through:

```python
def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    ratio = pipeline.RATIOS[args.ratio]

    if not args.input.exists():
        print(f"Error: '{args.input}' not found", file=sys.stderr)
        return 1

    try:
        if args.input.is_dir():
            if not pipeline.find_panoramas(args.input):
                print(f"No JPG files found in '{args.input}'")
                return 0
            result = pipeline.process_folder(args.input, args.output, ratio)
            print(
                f"Wrote {result.succeeded_count} of {result.total_count} "
                f"images to {args.output} at {ratio.name}"
            )
            for source, message in result.failed:
                print(f"Error processing {source}: {message}", file=sys.stderr)
            if result.failed:
                return 1
        else:
            written = pipeline.process_image(args.input, args.output, ratio)
            print(f"Wrote {len(written) - 1} detail frames at {ratio.name}")
            for path in written:
                print(f"  {path}")
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `mise run check`
Expected: geometry, pipeline and cli tests pass. `tests/test_gui.py` may still fail — Task 7 fixes it.

- [ ] **Step 5: Commit**

```bash
git add src/maskingframe/cli.py tests/test_cli.py
git commit --no-verify -m "feat(cli): add --ratio for the target aspect ratio

Defaults to 4:5, Instagram's largest feed footprint, which also tiles a
typical 2.4:1 panorama into three detail frames with almost no cropping."
```

---

### Task 7: Add the ratio selector and a per-run preview panel to the GUI

The preview panel currently builds exactly four fixed labels at construction time. The frame count now varies between runs, so it must be rebuilt per run. This is the part most likely to look wrong in manual testing.

**Files:**
- Modify: `src/maskingframe/gui.py`
- Modify: `tests/test_gui.py`

**Interfaces:**
- Consumes: `pipeline.RATIOS`, `pipeline.DEFAULT_RATIO`, `pipeline.output_paths`, `pipeline.process_image`, `pipeline.process_folder`, `pipeline.BatchResult` (with `last_count`)
- Produces: `preview_titles(count: int) -> list[str]` module-level helper

- [ ] **Step 1: Write the failing tests**

Replace the fixed-length preview assertion in `tests/test_gui.py` with:

```python
def test_preview_titles_track_the_frame_count() -> None:
    from maskingframe import gui

    assert gui.preview_titles(2) == ["Whole", "Detail 1", "Detail 2"]
    assert gui.preview_titles(4) == [
        "Whole",
        "Detail 1",
        "Detail 2",
        "Detail 3",
        "Detail 4",
    ]


def test_preview_titles_match_output_paths_length() -> None:
    from maskingframe import gui, pipeline

    for count in (2, 3, 4, 5):
        assert len(gui.preview_titles(count)) == len(
            pipeline.output_paths("/tmp/x", count)
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `mise exec -- uv run pytest tests/test_gui.py -v`
Expected: FAIL with `AttributeError: module 'maskingframe.gui' has no attribute 'preview_titles'`

- [ ] **Step 3: Implement**

In `src/maskingframe/gui.py`, replace the `PREVIEW_TITLES` constant with:

```python
PREVIEW_MAX_PX = 150


def preview_titles(count: int) -> list[str]:
    """Labels for the preview panes: the whole panorama plus each detail frame."""
    return ["Whole"] + [f"Detail {n}" for n in range(1, count + 1)]
```

In `__init__`, add the ratio variable alongside the others:

```python
        self.ratio = tk.StringVar(value=pipeline.DEFAULT_RATIO.name)
```

and initialise the preview bookkeeping:

```python
        self.preview_labels: list[ttk.Label] = []
```

In `_build_ui`, add the combobox. Put it on its own row between the mode label and the Process button, and shift the Process button, progress frame and preview frame down one row each (Process button to row 4, progress frame to row 5, preview frame to row 6, and update `main.rowconfigure(5, weight=1)` to `main.rowconfigure(6, weight=1)`):

```python
        ratio_row = ttk.Frame(main)
        ratio_row.grid(row=3, column=0, columnspan=4, sticky=tk.W, pady=5)
        ttk.Label(ratio_row, text="Aspect ratio:").pack(side="left")
        ttk.Combobox(
            ratio_row,
            textvariable=self.ratio,
            values=sorted(pipeline.RATIOS),
            state="readonly",
            width=10,
        ).pack(side="left", padx=8)
        ttk.Label(
            ratio_row,
            text="detail frames are derived from this",
            foreground="grey40",
        ).pack(side="left")
```

Keep a reference to the preview frame so it can be rebuilt, replacing the fixed label-building loop:

```python
        self.preview_frame = ttk.LabelFrame(main, text="Preview (Last Processed)", padding="10")
        self.preview_frame.grid(
            row=6, column=0, columnspan=4, sticky=(tk.W, tk.E, tk.N, tk.S), pady=10
        )
        self.preview_frame.rowconfigure(0, weight=1)
```

Add the rebuild method:

```python
    def _rebuild_preview_panes(self, count: int) -> None:
        """Recreate the preview cells for a run's frame count.

        The count varies with the aspect ratio, so the panes cannot be built
        once at construction time. Runs on the main thread only.
        """
        for child in self.preview_frame.winfo_children():
            child.destroy()
        self.preview_labels = []

        titles = preview_titles(count)
        for column, title in enumerate(titles):
            self.preview_frame.columnconfigure(column, weight=1)
            cell = ttk.Frame(self.preview_frame)
            cell.grid(row=0, column=column, padx=5, pady=5, sticky=(tk.N, tk.S, tk.E, tk.W))
            ttk.Label(cell, text=title, font=("Arial", 10, "bold")).pack()
            label = ttk.Label(cell, text="No preview", relief="sunken", anchor="center")
            label.pack(expand=True, fill="both")
            self.preview_labels.append(label)

        # Drop stale column weights from a previous, longer run.
        for column in range(len(titles), len(titles) + 6):
            self.preview_frame.columnconfigure(column, weight=0)
```

Update `update_preview` to take the count and rebuild first:

```python
    def update_preview(self, output_prefix: str, count: int) -> None:
        self._rebuild_preview_panes(count)
        images: list[ImageTk.PhotoImage] = []
        for label, path in zip(
            self.preview_labels, pipeline.output_paths(output_prefix, count), strict=True
        ):
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
        self._preview_images = images
```

Note the widened `except Exception` there: it is the last instance of the narrow-catch pattern flagged in the previous review, and it sits before the button is re-enabled, so a surprise exception would leave the GUI wedged.

Update `_finish` and `_finish_batch` to carry the count:

```python
    def _finish(
        self, message: str, prefix: str | None, count: int | None, error: str | None
    ) -> None:
        """Runs on the main thread. All widget mutation happens here."""
        self.progress.set(100)
        self.status.set(message)
        if prefix is not None and count is not None:
            self.update_preview(prefix, count)
        self.process_btn.config(state="normal")
        if error is not None:
            messagebox.showerror("Error", error)
        else:
            messagebox.showinfo("Success", message)
```

and in `_finish_batch` replace the preview call:

```python
        if result.last_prefix is not None and result.last_count is not None:
            self.update_preview(str(result.last_prefix), result.last_count)
```

Update the workers to accept and forward the ratio, and to pass the count back:

```python
    def _run_single(self, source: str, prefix: str, ratio_name: str) -> None:
        try:
            written = pipeline.process_image(source, prefix, pipeline.RATIOS[ratio_name])
        except Exception as error:
            self.root.after(0, self._finish, "Failed", None, None, str(error))
            return
        self.root.after(0, self._finish, "Complete", prefix, len(written) - 1, None)

    def _run_batch(self, source: str, destination: str, ratio_name: str) -> None:
        def report(done: int, total: int, path: Path) -> None:
            self.root.after(0, self._set_progress, done, total, path.name)

        try:
            result = pipeline.process_folder(
                source, destination, pipeline.RATIOS[ratio_name], on_progress=report
            )
        except Exception as error:
            self.root.after(0, self._finish, "Failed", None, None, str(error))
            return
        self.root.after(0, self._finish_batch, result)
```

Finally, read the ratio on the main thread in `process_images` and pass it as a plain string, preserving the invariant that no worker thread touches a tk object:

```python
        target = self._run_batch if self.is_folder_mode.get() else self._run_single
        threading.Thread(
            target=target, args=(source, destination, self.ratio.get()), daemon=True
        ).start()
```

- [ ] **Step 4: Run tests and type checks**

Run: `mise run check`
Expected: everything passes. The tree should be fully green again for the first time since Task 3.

- [ ] **Step 5: Verify the widget tree builds and the panel rebuilds**

```bash
mise exec -- uv run python -c "
import tkinter
from maskingframe.gui import PanoramaSplitterGUI
root = tkinter.Tk(); root.withdraw()
app = PanoramaSplitterGUI(root)
app._rebuild_preview_panes(2)
assert len(app.preview_labels) == 3, len(app.preview_labels)
app._rebuild_preview_panes(4)
assert len(app.preview_labels) == 5, len(app.preview_labels)
app._rebuild_preview_panes(2)
assert len(app.preview_labels) == 3, 'stale panes left behind after shrinking'
print('preview panel rebuilds cleanly in both directions')
root.destroy()
"
```

Expected: the success message. The shrink case is the one that matters — it catches panes left behind from a longer previous run.

- [ ] **Step 6: Programmatic end-to-end drive**

Build the GUI with a withdrawn root, point it at `tests/fixtures/golden_wide.jpg`, set the ratio to `4:5`, call `process_images()`, run `root.mainloop()` with a `root.after` timer that quits once the worker has finished, then assert four output files exist and `len(app._preview_images) == 4`. Repeat with `1.91:1` and assert three. Paste the output in your report.

- [ ] **Step 7: Commit**

```bash
git add src/maskingframe/gui.py tests/test_gui.py
git commit -m "feat(gui): add a ratio selector and rebuild previews per run

The preview panel held exactly four fixed labels; the frame count now
varies with the ratio, so the panes are rebuilt each run. The ratio is read
on the main thread and passed to the worker as a plain string, keeping the
invariant that no worker thread touches a tk object."
```

---

### Task 8: Documentation and a real-panorama sweep

**Files:**
- Modify: `README.md`, `CLAUDE.md`

**Interfaces:**
- Consumes: everything above
- Produces: accurate docs and evidence the feature works on real input

- [ ] **Step 1: Sweep the user's real panoramas**

`samples/` holds 18 of the user's own scans (gitignored). Run all three ratios over them and check the counts against what the spec predicts:

```bash
for r in "1:1" "4:5" "1.91:1"; do
  echo "=== $r ==="
  mise exec -- uv run maskingframe samples "/tmp/sweep/${r//:/-}" --ratio "$r"
done
```

Expected: 16 succeed and 2 fail. The two failures must be `DSCF6771.jpg` and `DSCF6774.jpg`, both reported as portrait, and the batch must not abort. Confirm the per-file frame counts match the spec's table: typical 2.2-2.5:1 scans give 2 / 2 / 3 detail frames at 1.91:1 / 1:1 / 4:5, and the two 3.0:1 scans give 2 / 3 / 4.

Record the actual counts in your report. If any file's count disagrees with the table, STOP and report it rather than adjusting the table to match.

- [ ] **Step 2: Spot-check the output visually**

```bash
mise exec -- uv run python -c "
from PIL import Image
from pathlib import Path
for p in sorted(Path('/tmp/sweep/4-5').glob('horizons3-hp5-4*.jpg')):
    with Image.open(p) as im:
        print(f'{p.name:<40} {im.size[0]}x{im.size[1]}  ratio {im.size[0]/im.size[1]:.3f}')
"
```

Expected: the padded frame is 0.800 and each detail frame is exactly 1080x1350.

- [ ] **Step 3: Update README.md**

Add a section documenting the ratio option, and correct anything the change invalidates:

```markdown
## Aspect ratio

Instagram supports three feed shapes, and every image in a carousel must
share one. Pick the target with `--ratio`:

| Ratio | Output size | Use |
| ----- | ----------- | --- |
| `4:5` | 1080x1350 | Default. Largest feed footprint. |
| `1:1` | 1080x1080 | Classic square. |
| `1.91:1` | 1080x566 | Landscape. |

The first frame is the whole panorama on a white canvas. The frames after it
are a zoom, so viewers can see detail that is illegible in the first — and
how many there are is derived from the ratio and the panorama's shape, never
fewer than two.

A typical 2.4:1 panorama gives 3 detail frames at 4:5, 2 at 1:1, and 2 at
1.91:1. A 3:1 panorama gives 4, 3 and 2.

```bash
mise run split -- panorama.jpg my_prefix --ratio 4:5
mise run split -- ./panoramas ./output --ratio 1.91:1
```

Portrait images are rejected — this tool expects landscape panoramas. In a
batch the rejected file is reported and the rest continue.
```

Also update the Output Details section: the first output is now `_1_padded.jpg`, not `_1_padded_square.jpg`, and it is only square when you ask for `1:1`. Remove any claim of a fixed three sections or a fixed 1080x1080 output.

- [ ] **Step 4: Update CLAUDE.md**

Update these sections to match the code:

- Commands: show `--ratio` on the `split` examples.
- Architecture: `geometry.py` now owns `AspectRatio`, `section_count`, `make_padded_frame` and a `make_section` that takes a count and a ratio. `pipeline.py` re-exports `AspectRatio`, `RATIOS` and `DEFAULT_RATIO` specifically so `cli.py` and `gui.py` need not import `geometry`, preserving the stated dependency direction — say so explicitly, or a future reader will "tidy" it away.
- The padding section: `make_padded_frame` centers the panorama on a canvas of the target ratio. At 4:5 most of the frame is white border; that is the intended aesthetic.
- Behaviour changes: add that the detail-frame count is derived and floored at 2; that portrait input is rejected; that `Image.MAX_IMAGE_PIXELS` is lifted in `pipeline.py` and why; and that the padded output was renamed.
- Note that `gui.py` rebuilds its preview panes per run because the count varies.

- [ ] **Step 5: Full verification from a clean state**

```bash
rm -rf .venv
mise run setup
mise run check
```

Expected: dependencies reinstall, pre-commit hooks install, ruff and mypy clean, all tests pass.

- [ ] **Step 6: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs: document the aspect-ratio option and derived frame count

Records that the frames after the first are a zoom rather than a tiling,
which is why the count is floored at two, and that portrait input is
rejected."
```

---

## Self-Review

**Spec coverage:**

| Spec requirement | Task |
| ---------------- | ---- |
| `AspectRatio` with exact output sizes | 2 |
| Ratio registry and 4:5 default | 2 |
| `section_count` with floor of 2 | 2 |
| Half-up rounding | 2 |
| `section_bounds` takes a count | 3 |
| `make_section` covers then center-crops | 3 |
| `make_padded_frame` with ratio and growth rule | 3 |
| Variable `output_paths`, renamed padded output | 4 |
| `process_image` takes a ratio | 4 |
| Portrait rejection, batch continues | 4 |
| `MAX_IMAGE_PIXELS` lifted | 4 |
| `succeeded_count` as explicit counter | 4 |
| Per-ratio goldens replacing the single golden | 5 |
| `--ratio` flag, default 4:5, unknown rejected | 6 |
| GUI combobox | 7 |
| GUI preview panel rebuilt per run | 7 |
| `cli`/`gui` do not import `geometry` | 4 (re-exports), 6, 7 |
| Pre-commit hook repair | 1 |
| Real-panorama sweep | 8 |
| README and CLAUDE.md updated | 8 |

**Placeholder scan:** one intentional placeholder remains — the
`GOLDEN_HASHES` structure in Task 5 Step 3 is filled from the generator
command in Step 2, because the hashes depend on the installed Pillow build
and cannot be known when writing the plan. Every other step carries real
content.

**Type consistency:** `AspectRatio`, `section_count`, `section_bounds`,
`make_section`, `make_padded_frame`, `padded_frame_size`, `output_paths`,
`process_image`, `process_folder`, `BatchResult.last_count`,
`BatchResult.succeeded_count` and `preview_titles` are spelled identically
everywhere they appear. `make_section` takes `(image, index, count, ratio)`
in that order in both its definition and all three call sites (pipeline,
tests, and the geometry tests).

**Note on the broken window between Tasks 3 and 7.** Tasks 3 through 6 commit
with `--no-verify` because the tree does not fully typecheck until Task 7
lands. This is deliberate: splitting the geometry, pipeline, CLI and GUI
changes into separately reviewable commits is worth more than a green tree at
every intermediate commit, and the plan states which task restores it. Each
of those tasks still verifies its own module's tests before committing.
