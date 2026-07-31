# Tooling and Harness Modernisation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hand-rolled venv bootstrap scripts with mise + uv, restructure the two flat modules into a tested `src`-layout package, and add ruff, mypy, pytest and pre-commit — without changing a single output pixel.

**Architecture:** Pure geometry functions (PIL Image in, PIL Image out) are extracted into `geometry.py` and covered by fast in-memory tests. A thin `pipeline.py` owns all file I/O, the output-filename contract, and the batch loop with an optional progress callback. `cli.py` and `gui.py` are both consumers of `pipeline.py`. Behaviour is preserved exactly, including the padding quirk, and verified by byte-comparing outputs against references captured before the refactor.

**Tech Stack:** Python 3.13.13 (mise-managed), uv, Pillow, pytest, ruff, mypy, pre-commit, tkinter.

## Global Constraints

- Python pinned to **3.13.13** via mise. Do not use a system or Homebrew Python.
- Pillow floor is **>=10.0.0** (current resolved version 12.3.0).
- **No output image may change.** Task 1 captures byte references; Task 7 verifies against them.
- Padding behaviour is **preserved, not fixed**: canvas is `max(width + 200, height + 20)` and the panorama is centered. Tests lock this in as characterisation.
- Section splitting uses **integer division** `width // 3` and discards the remainder pixels at the right edge. Preserve exactly.
- JPEG quality is **95** for every output.
- Output filenames are a contract: `{prefix}_1_padded_square.jpg`, `{prefix}_2_section1.jpg`, `{prefix}_3_section2.jpg`, `{prefix}_4_section3.jpg`.
- Resampling is **`Image.Resampling.LANCZOS`** everywhere.
- Commit after every task. Conventional commits, imperative mood. No Claude attribution in commit messages.

---

## File Structure

| File | Responsibility |
| ---- | -------------- |
| `mise.toml` | Python + uv pins, task surface |
| `pyproject.toml` | Package metadata, entry points, ruff/mypy/pytest config |
| `src/auto_border_pano/__init__.py` | Package marker, version |
| `src/auto_border_pano/geometry.py` | Pure image transforms. No paths, no disk |
| `src/auto_border_pano/pipeline.py` | File I/O, output naming, batch loop |
| `src/auto_border_pano/cli.py` | argparse entry points, tkinter import guard |
| `src/auto_border_pano/gui.py` | tkinter front end |
| `tests/conftest.py` | Shared synthetic-panorama fixtures |
| `tests/test_geometry.py` | Geometry unit tests |
| `tests/test_pipeline.py` | I/O and batch tests against `tmp_path` |
| `.pre-commit-config.yaml` | ruff + mypy on commit, pytest on push |
| `install.bat`, `run_gui.bat` | Thin uv wrappers (Windows) |

Deleted at Task 7: `install.sh`, `run_gui.sh`, `requirements.txt`, `panorama_splitter.py`, `panorama_splitter_gui.py`.

---

### Task 1: Capture behaviour references and bootstrap the toolchain

Nothing else can proceed safely until we can prove the refactor changed no pixels. This task creates the safety net first, then stands up mise, uv, and the empty harness.

**Files:**
- Create: `mise.toml`, `pyproject.toml`, `src/auto_border_pano/__init__.py`, `tests/conftest.py`, `tests/test_harness.py`
- Create (untracked): `reference/` holding pre-refactor outputs

**Interfaces:**
- Consumes: nothing
- Produces: `synthetic_panorama(width, height)` fixture helper in `tests/conftest.py`; `reference/` directory of golden outputs used only by Task 7

- [ ] **Step 1: Generate reference outputs from the current, unmodified code**

The panorama is a deterministic gradient so it can be regenerated identically at any time. Run with the current repo state, before any file is touched:

```bash
mkdir -p reference
python3 - <<'PY'
from PIL import Image
import sys
sys.path.insert(0, '.')
from panorama_splitter import process_panoramic_image

# Deterministic gradient panorama, 3000x800
img = Image.new('RGB', (3000, 800))
px = img.load()
for x in range(3000):
    for y in range(800):
        px[x, y] = (x % 256, y % 256, (x + y) % 256)
img.save('reference/input.jpg', 'JPEG', quality=95)

process_panoramic_image('reference/input.jpg', 'reference/ref')
PY
ls -1 reference/
```

Expected: `input.jpg`, `ref_1_padded_square.jpg`, `ref_2_section1.jpg`, `ref_3_section2.jpg`, `ref_4_section3.jpg`.

- [ ] **Step 2: Record the reference checksums**

```bash
cd reference && shasum -a 256 ref_*.jpg | tee checksums.txt && cd ..
```

Keep this output. Task 7 compares against it.

- [ ] **Step 3: Add `reference/` to .gitignore**

Append to `.gitignore`:

```gitignore
# Pre-refactor output references (regenerable, see plan Task 1)
reference/
```

- [ ] **Step 4: Write `mise.toml`**

```toml
[tools]
python = "3.13.13"
uv = "latest"

[env]
_.python.venv = { path = ".venv", create = true }

[tasks.setup]
description = "Install dependencies"
run = "uv sync"

[tasks.gui]
description = "Launch the GUI"
run = "uv run pano-split-gui"

[tasks.split]
description = "Run the CLI"
run = "uv run pano-split"

[tasks.test]
description = "Run tests"
run = "uv run pytest"

[tasks.lint]
description = "Lint"
run = "uv run ruff check ."

[tasks.fmt]
description = "Format"
run = "uv run ruff format ."

[tasks.typecheck]
description = "Type check"
run = "uv run mypy src tests"

[tasks.check]
description = "Lint, type check and test"
depends = ["lint", "typecheck", "test"]
```

- [ ] **Step 5: Write `pyproject.toml`**

```toml
[project]
name = "auto-border-pano"
version = "0.2.0"
description = "Split panoramic images into social-media-ready square formats"
requires-python = ">=3.13"
dependencies = ["Pillow>=10.0.0"]

[project.scripts]
pano-split = "auto_border_pano.cli:main"
pano-split-gui = "auto_border_pano.cli:gui_main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/auto_border_pano"]

[dependency-groups]
dev = ["pytest>=8.0", "ruff>=0.6", "mypy>=1.11", "pre-commit>=3.8"]

[tool.ruff]
line-length = 100
src = ["src", "tests"]

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM", "RUF"]

[tool.mypy]
python_version = "3.13"
strict = true
files = ["src", "tests"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra"
```

- [ ] **Step 6: Create the package marker**

`src/auto_border_pano/__init__.py`:

```python
"""Split panoramic images into social-media-ready square formats."""

__version__ = "0.2.0"
```

- [ ] **Step 7: Write the shared test fixture**

`tests/conftest.py`:

```python
"""Shared fixtures for the auto_border_pano test suite."""

from PIL import Image


def synthetic_panorama(width: int = 3000, height: int = 800) -> Image.Image:
    """Build a deterministic gradient panorama for tests.

    Deterministic so that failures are reproducible and so that reference
    outputs can be regenerated byte-for-byte.
    """
    img = Image.new("RGB", (width, height))
    pixels = img.load()
    assert pixels is not None
    for x in range(width):
        for y in range(height):
            pixels[x, y] = (x % 256, y % 256, (x + y) % 256)
    return img
```

- [ ] **Step 8: Write a harness smoke test**

`tests/test_harness.py`:

```python
"""Proves the toolchain itself works before real tests are written."""

from auto_border_pano import __version__
from tests.conftest import synthetic_panorama


def test_package_imports() -> None:
    assert __version__ == "0.2.0"


def test_synthetic_panorama_has_requested_size() -> None:
    img = synthetic_panorama(120, 40)
    assert img.size == (120, 40)
```

- [ ] **Step 9: Install and verify the whole harness runs**

```bash
mise install
mise run setup
mise run check
```

Expected: ruff passes, mypy reports no issues, pytest collects and passes 2 tests.

If mypy complains about `tests.conftest` import resolution, add `mypy_path = "."` under `[tool.mypy]`.

- [ ] **Step 10: Commit**

```bash
git add mise.toml pyproject.toml uv.lock .gitignore src tests
git commit -m "build: adopt mise, uv, ruff, mypy and pytest

Stands up the toolchain and an empty src-layout package ahead of
extracting the geometry code. Pins Python to 3.13.13 and replaces
ad-hoc pip usage with a committed uv lockfile."
```

---

### Task 2: Extract padded-square geometry

**Files:**
- Create: `src/auto_border_pano/geometry.py`
- Create: `tests/test_geometry.py`

**Interfaces:**
- Consumes: `synthetic_panorama` from `tests/conftest.py`
- Produces:
  - `SIDE_PADDING: int = 100`
  - `VERTICAL_PADDING: int = 10`
  - `padded_square_size(width: int, height: int) -> int`
  - `make_padded_square(image: Image.Image) -> Image.Image`

- [ ] **Step 1: Write the failing tests**

`tests/test_geometry.py`:

```python
"""Characterisation tests for the pure geometry transforms.

These lock in current behaviour exactly, including the padding quirk where
the vertical padding constant only influences canvas size and the panorama
ends up vertically centered.
"""

from auto_border_pano import geometry
from tests.conftest import synthetic_panorama


def test_canvas_is_width_plus_two_side_paddings_for_wide_panorama() -> None:
    assert geometry.padded_square_size(3000, 800) == 3200


def test_canvas_uses_height_term_when_image_is_tall() -> None:
    # height + 20 exceeds width + 200 only when the image is nearly square
    # or taller than it is wide.
    assert geometry.padded_square_size(100, 800) == 820


def test_padded_square_is_square_and_correctly_sized() -> None:
    result = geometry.make_padded_square(synthetic_panorama(3000, 800))
    assert result.size == (3200, 3200)


def test_padded_square_centers_the_panorama() -> None:
    # The panorama is centered, so the top gap is (3200 - 800) // 2 = 1200,
    # NOT the 10px VERTICAL_PADDING. This is the documented quirk.
    result = geometry.make_padded_square(synthetic_panorama(3000, 800))
    assert result.getpixel((1600, 1199)) == (255, 255, 255)
    assert result.getpixel((1600, 1201)) != (255, 255, 255)


def test_padded_square_background_is_white() -> None:
    result = geometry.make_padded_square(synthetic_panorama(3000, 800))
    assert result.getpixel((0, 0)) == (255, 255, 255)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `mise run test`
Expected: FAIL, `ModuleNotFoundError: No module named 'auto_border_pano.geometry'`

- [ ] **Step 3: Write the minimal implementation**

`src/auto_border_pano/geometry.py`:

```python
"""Pure image transforms.

Every function here takes and returns PIL Images. Nothing in this module
opens or writes a file, which is what makes it fast to test.
"""

from PIL import Image

SIDE_PADDING = 100
VERTICAL_PADDING = 10
BACKGROUND = "white"


def padded_square_size(width: int, height: int) -> int:
    """Return the edge length of the square canvas for a panorama.

    Note that for any normal wide panorama the width term wins, so the
    vertical padding never actually applies -- see make_padded_square.
    """
    return max(width + 2 * SIDE_PADDING, height + 2 * VERTICAL_PADDING)


def make_padded_square(image: Image.Image) -> Image.Image:
    """Center a panorama on a white square canvas.

    The panorama is centered rather than offset by VERTICAL_PADDING, so a
    wide panorama gets exactly SIDE_PADDING left and right and a much
    larger leftover gap top and bottom. Preserved deliberately.
    """
    width, height = image.size
    size = padded_square_size(width, height)
    canvas = Image.new("RGB", (size, size), BACKGROUND)
    canvas.paste(image, ((size - width) // 2, (size - height) // 2))
    return canvas
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `mise run check`
Expected: 7 tests pass, ruff and mypy clean.

- [ ] **Step 5: Commit**

```bash
git add src/auto_border_pano/geometry.py tests/test_geometry.py
git commit -m "refactor: extract padded-square geometry as a pure function

Characterisation tests lock in the existing centering behaviour, including
the quirk that the vertical padding constant only affects canvas size."
```

---

### Task 3: Extract section-cropping geometry

**Files:**
- Modify: `src/auto_border_pano/geometry.py`
- Modify: `tests/test_geometry.py`

**Interfaces:**
- Consumes: `geometry.SIDE_PADDING` and friends from Task 2
- Produces:
  - `SECTION_SIZE: int = 1080`
  - `SECTION_COUNT: int = 3`
  - `section_bounds(width: int, index: int) -> tuple[int, int]`
  - `make_section(image: Image.Image, index: int, size: int = SECTION_SIZE) -> Image.Image`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_geometry.py`:

```python
def test_section_bounds_split_on_integer_division() -> None:
    # 3001 // 3 == 1000, so the final pixel is discarded. Preserved.
    assert geometry.section_bounds(3001, 0) == (0, 1000)
    assert geometry.section_bounds(3001, 1) == (1000, 2000)
    assert geometry.section_bounds(3001, 2) == (2000, 3000)


def test_every_section_is_square_and_1080() -> None:
    panorama = synthetic_panorama(3000, 800)
    for index in range(geometry.SECTION_COUNT):
        assert geometry.make_section(panorama, index).size == (1080, 1080)


def test_section_honours_explicit_size() -> None:
    result = geometry.make_section(synthetic_panorama(3000, 800), 0, size=256)
    assert result.size == (256, 256)


def test_tall_section_scales_on_width() -> None:
    # A section narrower than it is tall takes the else branch: scale to
    # width, then crop vertically. 300 wide / 3 = 100 per section.
    result = geometry.make_section(synthetic_panorama(300, 900), 0)
    assert result.size == (1080, 1080)


def test_section_index_is_validated() -> None:
    import pytest

    with pytest.raises(ValueError):
        geometry.make_section(synthetic_panorama(300, 100), 3)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `mise run test`
Expected: FAIL with `AttributeError: module 'auto_border_pano.geometry' has no attribute 'section_bounds'`

- [ ] **Step 3: Write the minimal implementation**

Append to `src/auto_border_pano/geometry.py`:

```python
SECTION_SIZE = 1080
SECTION_COUNT = 3


def section_bounds(width: int, index: int) -> tuple[int, int]:
    """Return the horizontal crop bounds of one section.

    Uses integer division, so when the width is not divisible by
    SECTION_COUNT the remaining pixels on the right edge are discarded.
    """
    if not 0 <= index < SECTION_COUNT:
        raise ValueError(f"index must be 0..{SECTION_COUNT - 1}, got {index}")
    section_width = width // SECTION_COUNT
    start = index * section_width
    return start, start + section_width


def make_section(
    image: Image.Image, index: int, size: int = SECTION_SIZE
) -> Image.Image:
    """Crop one section of the panorama and fill a square of `size`.

    Scales on whichever axis keeps the square fully covered, then
    center-crops the overflow.
    """
    width, height = image.size
    start, end = section_bounds(width, index)
    crop = image.crop((start, 0, end, height))
    crop_width, crop_height = crop.size

    if crop_width > crop_height:
        scale = size / crop_height
        resized = crop.resize(
            (int(crop_width * scale), size), Image.Resampling.LANCZOS
        )
        offset = (resized.width - size) // 2
        return resized.crop((offset, 0, offset + size, size))

    scale = size / crop_width
    resized = crop.resize(
        (size, int(crop_height * scale)), Image.Resampling.LANCZOS
    )
    offset = (resized.height - size) // 2
    return resized.crop((0, offset, size, offset + size))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `mise run check`
Expected: 12 tests pass, ruff and mypy clean.

Move the `import pytest` from inside the test body to the top of the file if ruff's PLC0415 or your own taste objects; the plan puts it inline only to keep the diff readable.

- [ ] **Step 5: Commit**

```bash
git add src/auto_border_pano/geometry.py tests/test_geometry.py
git commit -m "refactor: extract section cropping as a pure function

Locks in integer-division splitting, which discards remainder pixels on
the right edge, and the scale-then-center-crop behaviour."
```

---

### Task 4: Build the I/O pipeline

**Files:**
- Create: `src/auto_border_pano/pipeline.py`
- Create: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `geometry.make_padded_square`, `geometry.make_section`, `geometry.SECTION_COUNT`
- Produces:
  - `JPEG_QUALITY: int = 95`
  - `OUTPUT_SUFFIXES: tuple[str, ...]`
  - `output_paths(prefix: Path | str) -> list[Path]`
  - `process_image(input_path: Path | str, output_prefix: Path | str) -> list[Path]`
  - `find_panoramas(folder: Path | str) -> list[Path]`
  - `ProgressCallback` type alias
  - `process_folder(input_folder, output_folder, on_progress=None) -> list[Path]`

- [ ] **Step 1: Write the failing tests**

`tests/test_pipeline.py`:

```python
"""Tests for the file-I/O layer."""

from pathlib import Path

from PIL import Image

from auto_border_pano import pipeline
from tests.conftest import synthetic_panorama


def _write_panorama(path: Path, width: int = 3000, height: int = 800) -> Path:
    synthetic_panorama(width, height).save(path, "JPEG", quality=95)
    return path


def test_output_paths_follow_the_naming_contract() -> None:
    paths = pipeline.output_paths("/tmp/holiday")
    assert [p.name for p in paths] == [
        "holiday_1_padded_square.jpg",
        "holiday_2_section1.jpg",
        "holiday_3_section2.jpg",
        "holiday_4_section3.jpg",
    ]


def test_process_image_writes_four_files(tmp_path: Path) -> None:
    source = _write_panorama(tmp_path / "pano.jpg")
    written = pipeline.process_image(source, tmp_path / "out")
    assert len(written) == 4
    assert all(p.exists() for p in written)


def test_process_image_output_dimensions(tmp_path: Path) -> None:
    source = _write_panorama(tmp_path / "pano.jpg")
    written = pipeline.process_image(source, tmp_path / "out")
    with Image.open(written[0]) as square:
        assert square.size == (3200, 3200)
    for section in written[1:]:
        with Image.open(section) as img:
            assert img.size == (1080, 1080)


def test_find_panoramas_matches_all_jpeg_spellings(tmp_path: Path) -> None:
    for name in ("a.jpg", "b.JPG", "c.jpeg", "d.JPEG", "ignore.png"):
        (tmp_path / name).touch()
    found = {p.name for p in pipeline.find_panoramas(tmp_path)}
    assert found == {"a.jpg", "b.JPG", "c.jpeg", "d.JPEG"}


def test_find_panoramas_does_not_return_duplicates(tmp_path: Path) -> None:
    # On a case-insensitive filesystem (macOS default) naive globbing of
    # both *.jpg and *.JPG returns the same file twice.
    (tmp_path / "only.jpg").touch()
    assert len(pipeline.find_panoramas(tmp_path)) == 1


def test_process_folder_creates_output_dir_and_reports_progress(
    tmp_path: Path,
) -> None:
    source_dir = tmp_path / "in"
    source_dir.mkdir()
    _write_panorama(source_dir / "one.jpg", 600, 200)
    _write_panorama(source_dir / "two.jpg", 600, 200)
    out_dir = tmp_path / "out"

    seen: list[tuple[int, int, str]] = []
    written = pipeline.process_folder(
        source_dir,
        out_dir,
        on_progress=lambda done, total, path: seen.append(
            (done, total, path.name)
        ),
    )

    assert out_dir.is_dir()
    assert len(written) == 8
    assert [s[:2] for s in seen] == [(0, 2), (1, 2)]


def test_process_folder_continues_after_a_bad_file(tmp_path: Path) -> None:
    source_dir = tmp_path / "in"
    source_dir.mkdir()
    _write_panorama(source_dir / "good.jpg", 600, 200)
    (source_dir / "broken.jpg").write_text("not an image")

    written = pipeline.process_folder(source_dir, tmp_path / "out")
    assert len(written) == 4
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `mise run test`
Expected: FAIL, `ModuleNotFoundError: No module named 'auto_border_pano.pipeline'`

- [ ] **Step 3: Write the minimal implementation**

`src/auto_border_pano/pipeline.py`:

```python
"""File I/O for panorama splitting.

This is the only module that touches the filesystem. It also owns the
output-filename contract, which the GUI depends on for previews.
"""

from collections.abc import Callable
from pathlib import Path

from PIL import Image

from auto_border_pano import geometry

JPEG_QUALITY = 95
JPEG_EXTENSIONS = (".jpg", ".jpeg")

OUTPUT_SUFFIXES = (
    "_1_padded_square.jpg",
    "_2_section1.jpg",
    "_3_section2.jpg",
    "_4_section3.jpg",
)

ProgressCallback = Callable[[int, int, Path], None]


def output_paths(prefix: Path | str) -> list[Path]:
    """Return the four output paths produced for a given prefix."""
    prefix = Path(prefix)
    return [prefix.with_name(prefix.name + suffix) for suffix in OUTPUT_SUFFIXES]


def process_image(
    input_path: Path | str, output_prefix: Path | str
) -> list[Path]:
    """Split one panorama into its four outputs and return their paths."""
    targets = output_paths(output_prefix)
    targets[0].parent.mkdir(parents=True, exist_ok=True)

    with Image.open(input_path) as source:
        source = source.convert("RGB")
        geometry.make_padded_square(source).save(
            targets[0], "JPEG", quality=JPEG_QUALITY
        )
        for index in range(geometry.SECTION_COUNT):
            geometry.make_section(source, index).save(
                targets[index + 1], "JPEG", quality=JPEG_QUALITY
            )
    return targets


def find_panoramas(folder: Path | str) -> list[Path]:
    """Return every JPEG in a folder, case-insensitively, without duplicates."""
    return sorted(
        path
        for path in Path(folder).iterdir()
        if path.is_file() and path.suffix.lower() in JPEG_EXTENSIONS
    )


def process_folder(
    input_folder: Path | str,
    output_folder: Path | str,
    on_progress: ProgressCallback | None = None,
) -> list[Path]:
    """Split every panorama in a folder.

    Individual failures are skipped so one unreadable file cannot abort a
    long batch. `on_progress` is called before each file with
    (completed_count, total_count, path).
    """
    output_folder = Path(output_folder)
    output_folder.mkdir(parents=True, exist_ok=True)

    sources = find_panoramas(input_folder)
    written: list[Path] = []

    for done, source in enumerate(sources):
        if on_progress is not None:
            on_progress(done, len(sources), source)
        try:
            written.extend(process_image(source, output_folder / source.stem))
        except (OSError, ValueError) as error:
            print(f"Error processing {source}: {error}")
    return written
```

Note on `find_panoramas`: the original globbed `*.jpg` and `*.JPG` separately, which double-counts every file on macOS's case-insensitive filesystem. Suffix matching fixes that; the test above pins it.

- [ ] **Step 4: Run tests to verify they pass**

Run: `mise run check`
Expected: 19 tests pass, ruff and mypy clean.

- [ ] **Step 5: Commit**

```bash
git add src/auto_border_pano/pipeline.py tests/test_pipeline.py
git commit -m "refactor: centralise file I/O and the output-naming contract

The four output filenames were previously built in two places, so renaming
one silently broke GUI previews. The batch loop now takes an optional
progress callback, which removes the GUI's duplicate implementation.

Also fixes double-counting of files on case-insensitive filesystems, where
globbing *.jpg and *.JPG separately returned each file twice."
```

---

### Task 5: Build the CLI

**Files:**
- Create: `src/auto_border_pano/cli.py`
- Create: `tests/test_cli.py`

**Interfaces:**
- Consumes: `pipeline.process_image`, `pipeline.process_folder`
- Produces: `main(argv: list[str] | None = None) -> int`, `gui_main() -> int`

- [ ] **Step 1: Write the failing tests**

`tests/test_cli.py`:

```python
"""Tests for the argparse entry point."""

from pathlib import Path

from auto_border_pano import cli
from tests.conftest import synthetic_panorama


def test_single_file_mode_writes_outputs(tmp_path: Path) -> None:
    source = tmp_path / "pano.jpg"
    synthetic_panorama(600, 200).save(source, "JPEG", quality=95)

    exit_code = cli.main([str(source), str(tmp_path / "out")])

    assert exit_code == 0
    assert (tmp_path / "out_1_padded_square.jpg").exists()


def test_folder_mode_writes_outputs(tmp_path: Path) -> None:
    source_dir = tmp_path / "in"
    source_dir.mkdir()
    synthetic_panorama(600, 200).save(source_dir / "a.jpg", "JPEG", quality=95)

    exit_code = cli.main([str(source_dir), str(tmp_path / "out")])

    assert exit_code == 0
    assert (tmp_path / "out" / "a_1_padded_square.jpg").exists()


def test_missing_input_is_an_error(tmp_path: Path) -> None:
    assert cli.main([str(tmp_path / "nope.jpg")]) == 1


def test_default_prefix_is_output(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "pano.jpg"
    synthetic_panorama(600, 200).save(source, "JPEG", quality=95)

    assert cli.main([str(source)]) == 0
    assert (tmp_path / "output_1_padded_square.jpg").exists()
```

If mypy objects to the untyped `monkeypatch` parameter, type it as
`pytest.MonkeyPatch` and drop the ignore comment.

- [ ] **Step 2: Run tests to verify they fail**

Run: `mise run test`
Expected: FAIL, `ModuleNotFoundError: No module named 'auto_border_pano.cli'`

- [ ] **Step 3: Write the minimal implementation**

`src/auto_border_pano/cli.py`:

```python
"""Command-line entry points."""

import argparse
import sys
from pathlib import Path

from auto_border_pano import pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pano-split",
        description=(
            "Split a panorama into a padded square plus three 1080x1080 "
            "sections. Accepts a single image or a folder of images."
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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if not args.input.exists():
        print(f"Error: '{args.input}' not found", file=sys.stderr)
        return 1

    try:
        if args.input.is_dir():
            written = pipeline.process_folder(args.input, args.output)
            print(f"Wrote {len(written)} files to {args.output}")
        else:
            for path in pipeline.process_image(args.input, args.output):
                print(f"Wrote {path}")
    except (OSError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


def gui_main() -> int:
    """Launch the GUI, explaining clearly if tkinter is unavailable.

    The guard lives here rather than at module scope in gui.py so that
    importing the package can never terminate the host process.
    """
    try:
        from auto_border_pano.gui import run
    except ImportError:
        print(
            "Error: tkinter is not available.\n\n"
            "tkinter is required for the GUI.\n"
            "  macOS (Homebrew):  brew install python-tk\n"
            "  Ubuntu/Debian:     sudo apt-get install python3-tk\n"
            "  Fedora:            sudo dnf install python3-tkinter\n"
            "  Arch:              sudo pacman -S tk\n"
            "  SUSE:              sudo zypper install python3-tk\n\n"
            "Alternatively use the command-line version: pano-split --help",
            file=sys.stderr,
        )
        return 1
    run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `mise run check`
Expected: 23 tests pass, ruff and mypy clean.

- [ ] **Step 5: Commit**

```bash
git add src/auto_border_pano/cli.py tests/test_cli.py
git commit -m "feat: replace hand-rolled argv parsing with argparse

Adds a real --help, and moves the tkinter availability guard onto the GUI
entry point so that importing the package can no longer exit the process."
```

---

### Task 6: Port the GUI

**Files:**
- Create: `src/auto_border_pano/gui.py`
- Reference: `panorama_splitter_gui.py` (source of the widget layout; deleted in Task 7)

**Interfaces:**
- Consumes: `pipeline.process_image`, `pipeline.process_folder`, `pipeline.output_paths`
- Produces: `run() -> None`, `PanoramaSplitterGUI`

- [ ] **Step 1: Write `src/auto_border_pano/gui.py`**

Port the existing widget tree verbatim, with four changes: previews come from `pipeline.output_paths`, the batch loop calls `pipeline.process_folder` with a progress callback rather than reimplementing the glob, all widget mutation from the worker thread is marshalled through `root.after`, and the thread is a daemon so a closed window does not hang the process.

```python
"""tkinter front end.

Importing this module raises ImportError when tkinter is missing; the
friendly message lives in cli.gui_main.
"""

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from auto_border_pano import pipeline

PREVIEW_TITLES = ("Padded Square", "Left Section", "Middle Section", "Right Section")
PREVIEW_MAX_PX = 150


class PanoramaSplitterGUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Panorama Splitter")
        self.root.geometry("800x600")

        self.input_path = tk.StringVar()
        self.output_path = tk.StringVar()
        self.is_folder_mode = tk.BooleanVar(value=False)
        self.progress = tk.DoubleVar()
        self.status = tk.StringVar(value="Ready")
        self._preview_images: list[ImageTk.PhotoImage] = []

        self._build_ui()

    def _build_ui(self) -> None:
        main = ttk.Frame(self.root, padding="10")
        main.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main.columnconfigure(1, weight=1)

        ttk.Label(main, text="Input:").grid(row=0, column=0, sticky=tk.W, pady=5)
        ttk.Entry(main, textvariable=self.input_path, width=50).grid(
            row=0, column=1, sticky=(tk.W, tk.E), padx=5
        )
        ttk.Button(main, text="Browse File", command=self.browse_file).grid(
            row=0, column=2, padx=5
        )
        ttk.Button(main, text="Browse Folder", command=self.browse_folder).grid(
            row=0, column=3, padx=5
        )

        ttk.Label(main, text="Output:").grid(row=1, column=0, sticky=tk.W, pady=5)
        ttk.Entry(main, textvariable=self.output_path, width=50).grid(
            row=1, column=1, sticky=(tk.W, tk.E), padx=5
        )
        ttk.Button(main, text="Browse", command=self.browse_output).grid(
            row=1, column=2, padx=5
        )

        self.mode_label = ttk.Label(main, text="Mode: Single File")
        self.mode_label.grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=10)

        self.process_btn = ttk.Button(
            main, text="Process Images", command=self.process_images
        )
        self.process_btn.grid(row=3, column=0, columnspan=4, pady=20)

        progress_frame = ttk.LabelFrame(main, text="Progress", padding="10")
        progress_frame.grid(row=4, column=0, columnspan=4, sticky=(tk.W, tk.E), pady=10)
        progress_frame.columnconfigure(0, weight=1)
        ttk.Progressbar(progress_frame, variable=self.progress, maximum=100).grid(
            row=0, column=0, sticky=(tk.W, tk.E), pady=5
        )
        ttk.Label(progress_frame, textvariable=self.status).grid(
            row=1, column=0, sticky=tk.W
        )

        preview_frame = ttk.LabelFrame(main, text="Preview (Last Processed)", padding="10")
        preview_frame.grid(
            row=5, column=0, columnspan=4, sticky=(tk.W, tk.E, tk.N, tk.S), pady=10
        )
        preview_frame.rowconfigure(0, weight=1)

        self.preview_labels: list[ttk.Label] = []
        for column, title in enumerate(PREVIEW_TITLES):
            preview_frame.columnconfigure(column, weight=1)
            cell = ttk.Frame(preview_frame)
            cell.grid(row=0, column=column, padx=5, pady=5, sticky=(tk.N, tk.S, tk.E, tk.W))
            ttk.Label(cell, text=title, font=("Arial", 10, "bold")).pack()
            label = ttk.Label(cell, text="No preview", relief="sunken", anchor="center")
            label.pack(expand=True, fill="both")
            self.preview_labels.append(label)

        main.rowconfigure(5, weight=1)

    def browse_file(self) -> None:
        filename = filedialog.askopenfilename(
            title="Select Panorama Image",
            filetypes=[("Image files", "*.jpg *.jpeg *.JPG *.JPEG"), ("All files", "*.*")],
        )
        if not filename:
            return
        self.input_path.set(filename)
        self.is_folder_mode.set(False)
        self.mode_label.config(text="Mode: Single File")
        self.output_path.set(str(Path(filename).with_suffix("")) + "_output")

    def browse_folder(self) -> None:
        folder = filedialog.askdirectory(title="Select Input Folder")
        if not folder:
            return
        chosen = Path(folder)
        self.input_path.set(folder)
        self.is_folder_mode.set(True)
        self.mode_label.config(text="Mode: Folder Processing")
        self.output_path.set(str(chosen.parent / f"{chosen.name}_output"))

    def browse_output(self) -> None:
        folder = filedialog.askdirectory(title="Select Output Folder")
        if not folder:
            return
        if self.is_folder_mode.get():
            self.output_path.set(folder)
            return
        source = self.input_path.get()
        self.output_path.set(str(Path(folder) / Path(source).stem) if source else folder)

    def update_preview(self, output_prefix: str) -> None:
        self._preview_images.clear()
        for label, path in zip(
            self.preview_labels, pipeline.output_paths(output_prefix), strict=True
        ):
            if not path.exists():
                label.config(image="", text="No preview")
                continue
            try:
                with Image.open(path) as img:
                    img.thumbnail((PREVIEW_MAX_PX, PREVIEW_MAX_PX), Image.Resampling.LANCZOS)
                    photo = ImageTk.PhotoImage(img)
            except OSError as error:
                label.config(image="", text=f"Error: {error}")
                continue
            self._preview_images.append(photo)
            label.config(image=photo, text="")

    def _finish(self, message: str, prefix: str | None, error: str | None) -> None:
        """Runs on the main thread. All widget mutation happens here."""
        self.progress.set(100)
        self.status.set(message)
        if prefix is not None:
            self.update_preview(prefix)
        self.process_btn.config(state="normal")
        if error is not None:
            messagebox.showerror("Error", error)
        else:
            messagebox.showinfo("Success", message)

    def _run_single(self) -> None:
        source = self.input_path.get()
        prefix = self.output_path.get()
        try:
            pipeline.process_image(source, prefix)
        except (OSError, ValueError) as error:
            self.root.after(0, self._finish, "Failed", None, str(error))
            return
        self.root.after(0, self._finish, "Complete", prefix, None)

    def _run_batch(self) -> None:
        source = self.input_path.get()
        destination = self.output_path.get()
        last: list[str] = []

        def report(done: int, total: int, path: Path) -> None:
            last.append(str(Path(destination) / path.stem))
            self.root.after(0, self._set_progress, done, total, path.name)

        try:
            pipeline.process_folder(source, destination, on_progress=report)
        except (OSError, ValueError) as error:
            self.root.after(0, self._finish, "Failed", None, str(error))
            return
        self.root.after(
            0, self._finish, f"Complete, processed {len(last)} files",
            last[-1] if last else None, None,
        )

    def _set_progress(self, done: int, total: int, name: str) -> None:
        self.progress.set(done / total * 100 if total else 0)
        self.status.set(f"Processing {done + 1}/{total}: {name}")

    def process_images(self) -> None:
        source = self.input_path.get()
        if not source or not Path(source).exists():
            messagebox.showerror("Error", "Please select a valid input")
            return
        self.process_btn.config(state="disabled")
        self.progress.set(0)
        self.status.set("Working...")
        target = self._run_batch if self.is_folder_mode.get() else self._run_single
        threading.Thread(target=target, daemon=True).start()


def run() -> None:
    root = tk.Tk()
    PanoramaSplitterGUI(root)
    root.mainloop()
```

- [ ] **Step 2: Verify it type-checks and lints**

Run: `mise run lint && mise run typecheck`
Expected: clean.

If mypy flags `label.config(image=photo)`, note that keeping the
`PhotoImage` alive in `self._preview_images` is what prevents the garbage
collection bug the original avoided with `label.image = photo`; do not
remove that list.

- [ ] **Step 3: Verify the widget tree builds headlessly**

```bash
uv run python -c "
import tkinter
from auto_border_pano.gui import PanoramaSplitterGUI
root = tkinter.Tk(); root.withdraw()
app = PanoramaSplitterGUI(root)
assert len(app.preview_labels) == 4
print('GUI builds OK')
root.destroy()
"
```

Expected: `GUI builds OK`

- [ ] **Step 4: Launch it for real and process one image**

```bash
mise run gui
```

Pick a panorama, process it, confirm four previews appear. This is a manual gate; do not skip it.

- [ ] **Step 5: Commit**

```bash
git add src/auto_border_pano/gui.py
git commit -m "refactor: port the GUI onto the shared pipeline

Previews now derive their paths from pipeline.output_paths instead of
rebuilding the filename convention, and batch mode calls the shared
process_folder with a progress callback rather than duplicating the glob.

All widget mutation from the worker thread now goes through root.after;
previously messagebox and widget config were called directly off-thread."
```

---

### Task 7: Verify no pixels changed, then remove the old world

**Files:**
- Delete: `panorama_splitter.py`, `panorama_splitter_gui.py`, `install.sh`, `run_gui.sh`, `requirements.txt`
- Modify: `install.bat`, `run_gui.bat`, `README.md`, `CLAUDE.md`
- Create: `.pre-commit-config.yaml`

**Interfaces:**
- Consumes: everything from Tasks 1-6
- Produces: the finished repository

- [ ] **Step 1: Prove the refactor changed no pixels**

```bash
uv run python -c "
from auto_border_pano import pipeline
pipeline.process_image('reference/input.jpg', 'reference/new')
"
cd reference && shasum -a 256 new_*.jpg && cat checksums.txt && cd ..
```

Compare the two lists pairwise: `new_1_padded_square.jpg` must match
`ref_1_padded_square.jpg`, and so on for all four.

**If any checksum differs, stop.** Do not proceed to deletion. Diff the
two images to find where the geometry drifted:

```bash
uv run python -c "
from PIL import Image, ImageChops
a = Image.open('reference/ref_1_padded_square.jpg')
b = Image.open('reference/new_1_padded_square.jpg')
print('sizes', a.size, b.size)
print('bbox of difference:', ImageChops.difference(a, b).getbbox())
"
```

- [ ] **Step 2: Delete the superseded files**

```bash
git rm panorama_splitter.py panorama_splitter_gui.py install.sh run_gui.sh requirements.txt
```

- [ ] **Step 3: Rewrite the Windows wrappers**

`install.bat`:

```bat
@echo off
REM Requires uv: https://docs.astral.sh/uv/getting-started/installation/
uv sync
echo.
echo Installation complete. Run the GUI with run_gui.bat
```

`run_gui.bat`:

```bat
@echo off
uv run pano-split-gui
if errorlevel 1 pause
```

- [ ] **Step 4: Add pre-commit hooks**

`.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.6.9
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: local
    hooks:
      - id: mypy
        name: mypy
        entry: uv run mypy src tests
        language: system
        pass_filenames: false

      - id: pytest
        name: pytest
        entry: uv run pytest
        language: system
        pass_filenames: false
        stages: [pre-push]
```

Install them:

```bash
uv run pre-commit install
uv run pre-commit install --hook-type pre-push
uv run pre-commit run --all-files
```

- [ ] **Step 5: Update README.md**

Replace the Requirements, Quick Installation and Usage sections. The new
install story is mise on macOS and Linux, uv on Windows:

```markdown
## Requirements

- [mise](https://mise.jdx.dev) on macOS and Linux, or
  [uv](https://docs.astral.sh/uv/) on Windows

Everything else, including Python itself, is installed for you.

## Installation

**macOS / Linux**

```bash
mise install
mise run setup
```

**Windows**

```batch
install.bat
```

## Usage

**GUI:** `mise run gui` (or `run_gui.bat` on Windows)

**CLI:**

```bash
mise run split -- input.jpg my_prefix      # single image
mise run split -- ./panoramas ./output     # whole folder
```

Run `uv run pano-split --help` for all options.
```

Also correct the Output Details section, which currently states the
padding backwards. The truth: the panorama is centered on a white square
canvas 200px wider than the image, giving 100px of padding left and
right and a larger leftover gap top and bottom.

- [ ] **Step 6: Update CLAUDE.md**

Rewrite the Commands and Architecture sections to describe the new
layout: `mise run check` as the single verification command, the
`geometry` / `pipeline` / `cli` / `gui` split, and the fact that the
padding quirk is deliberate and locked by characterisation tests. Remove
the now-stale references to `panorama_splitter.py`, the venv, and
`requirements.txt`.

- [ ] **Step 7: Full verification from a clean state**

```bash
rm -rf .venv
mise run setup
mise run check
```

Expected: dependencies reinstall, ruff and mypy clean, all tests pass.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "build: remove venv bootstrap scripts and flat modules

The Homebrew and apt/dnf/pacman detection in install.sh existed to make
Pillow and tkinter work; both install cleanly from wheels under a
mise-managed Python, so roughly 200 lines of shell go away. Windows keeps
parity through thin uv wrappers.

Outputs verified byte-identical to the pre-refactor code."
```

---

## Self-Review

**Spec coverage:**

| Spec requirement | Task |
| ---------------- | ---- |
| mise pins Python and uv | 1 |
| uv lockfile committed | 1 |
| Ruff configured in pyproject | 1 |
| mypy over src and tests | 1 |
| pytest | 1 |
| pre-commit, tests on push | 7 |
| No CI | n/a, deliberate |
| `geometry.py` pure | 2, 3 |
| `pipeline.py` owns I/O and naming | 4 |
| `cli.py` argparse + tkinter guard | 5 |
| `gui.py` imports pipeline not geometry | 6 |
| Output naming deduplicated | 4, 6 |
| Batch loop deduplicated via callback | 4, 6 |
| Library never exits on import | 5 |
| Padding preserved, docs corrected | 2, 7 |
| Geometry tested in memory | 2, 3 |
| Pipeline tested via tmp_path | 4 |
| No golden images in git | 1 (reference/ is gitignored) |
| mise task surface | 1 |
| Windows uses uv wrappers | 7 |
| Files removed | 7 |
| Outputs byte-comparable | 1, 7 |

**Placeholder scan:** no TBDs, no "handle edge cases", every code step
carries real code.

**Type consistency:** `output_paths`, `process_image`, `process_folder`,
`find_panoramas`, `make_padded_square`, `make_section`, `section_bounds`,
`padded_square_size` are spelled identically everywhere they appear.
`ProgressCallback` is `(int, int, Path) -> None` in the definition, the
pipeline test, and the GUI's `report`.

One deliberate deviation from the spec is recorded here rather than
hidden: `find_panoramas` fixes a latent double-counting bug on
case-insensitive filesystems. It changes behaviour, but only by removing
duplicate processing of the same file, and it is covered by a test.
