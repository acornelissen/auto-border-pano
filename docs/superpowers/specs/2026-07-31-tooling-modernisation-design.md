# Tooling and harness modernisation

Date: 2026-07-31
Status: approved, not yet implemented

## Goal

Put a modern toolchain and a test harness under `maskingframe` before new
features land. No user-visible change to the images the tool produces.

## Why now

The repository has no tests, no linter, no type checking, and no dependency
lockfile. Environment setup is four hand-written scripts (`install.sh`,
`install.bat`, `run_gui.sh`, `run_gui.bat`) totalling about 200 lines that
detect the operating system, shell out to Homebrew or apt/dnf/yum/zypper/pacman,
and build a `venv`. Every feature added on this base costs more than it should,
and the geometry code cannot be tested at all because each function opens and
writes files itself.

## Verified assumptions

The bootstrap scripts exist mainly to make tkinter and Pillow's system
libraries work. Both concerns were checked against a mise-managed Python
(3.13.13, python-build-standalone) before committing to this design:

- `import tkinter` works; Tk and Tcl both report 9.0.
- `tkinter.Tk()` instantiates.
- Pillow 12.3.0 installs as a prebuilt wheel, with no Homebrew libraries and
  no `CPPFLAGS`/`LDFLAGS` linking.
- `PIL.ImageTk.PhotoImage` works against Tk 9.0. This was the specific risk,
  since Pillow wheels historically targeted Tk 8.6.
- The existing `PanoramaSplitterGUI` widget tree builds under Tk 9.0.

The macOS branch of `install.sh` is therefore redundant, not merely awkward.

If a future Python pin regresses `ImageTk`, the fallback is to point mise at
the Homebrew Python on macOS. That is a configuration change, not a redesign.

## Toolchain

- **mise** manages the Python version and the `uv` binary. `.mise.toml` pins
  Python 3.13.13 and declares the task surface.
- **uv** manages dependencies and the lockfile. `uv.lock` is committed.
- **Ruff** for linting and formatting, configured in `pyproject.toml`.
- **mypy** for type checking, over `src/` and `tests/`. Chosen over `ty` because
  typeshed's tkinter stubs are mature and this codebase is small enough that
  strictness costs little.
- **pytest** for tests.
- **pre-commit** running ruff and mypy on commit, pytest on push. Tests are kept
  off the commit hook so commits stay fast.
- No CI, by choice. The repository does have a GitHub remote
  (`acornelissen/maskingframe`), so a workflow would run if added; it was
  declined in favour of the local pre-commit and pre-push hooks. Cheap to add
  later since `mise run check` is the single command a workflow would call.

## Structure

Move to a `src` layout package so the console-script entry points work
identically on all three platforms:

```text
src/maskingframe/
  geometry.py    Pure. PIL Image in, PIL Image out. No paths, no disk I/O.
  pipeline.py    Opens a file, calls geometry, saves four JPEGs. Owns the
                 output-filename contract and the batch loop.
  cli.py         argparse. Replaces the hand-rolled sys.argv branching.
                 Hosts the tkinter import guard on the GUI entry point.
  gui.py         tkinter front end. Imports pipeline, never geometry.
tests/
  test_geometry.py
  test_pipeline.py
```

Entry points declared in `pyproject.toml`: `maskingframe` and `maskingframe-gui`.

### Boundaries this fixes

**Output naming is duplicated.** `process_panoramic_image` builds the four
output paths and `PanoramaSplitterGUI.update_preview` independently rebuilds
the same four paths to load previews. Renaming an output silently breaks
previews. This becomes one function in `pipeline.py` that both callers use.

**The batch loop is duplicated.** `process_folder_batch` in the GUI
re-implements the glob-and-loop from `process_folder` solely to report
per-file progress. `pipeline.py` gets one batch function taking an optional
progress callback; the CLI passes nothing, the GUI passes its updater.

**The library exits the process on import.** `panorama_splitter_gui.py` calls
`sys.exit(1)` at module scope when tkinter is missing. That guard moves to the
GUI entry point in `cli.py`, so importing the package can never kill the host
process.

## Padding behaviour: preserved, not fixed

`process_panoramic_image` computes the canvas as `max(width + 200, height + 20)`
and then centers the panorama on it. For any normal wide panorama the width term
wins, so the result is 100px of padding left and right and a large leftover gap
top and bottom — not the 10px the comments claim. The README describes the two
paddings inverted on top of that.

The tests lock in the behaviour exactly as it is today. Comments and README are
corrected to describe centering with 100px side padding. No output changes.

Configurable padding is deferred to the feature work.

## Testing

Geometry is tested on in-memory images: construct a `PIL.Image` of a known
size, call the pure function, assert on canvas dimensions, crop offsets, and
output dimensions. Fast, no binary fixtures in git.

`test_pipeline.py` uses `tmp_path` and a synthetic panorama to assert the four
expected filenames appear with the right dimensions. This covers the I/O
wrapper without golden images, which were rejected as brittle across Pillow
versions.

Golden-image comparison is explicitly out of scope.

## Task surface

mise tasks, for macOS and Linux:

| Task | Does |
| ---- | ---- |
| `setup` | `uv sync` |
| `gui` | launch the GUI |
| `split` | run the CLI |
| `test` | pytest |
| `lint` | ruff check |
| `fmt` | ruff format |
| `typecheck` | mypy |
| `check` | lint, typecheck, and test together |

Windows cannot assume mise is present, and `uv` is the more commonly installed
of the two there. `install.bat` becomes `uv sync`; `run_gui.bat` becomes
`uv run maskingframe-gui`. Roughly three lines each.

`install.sh` and `run_gui.sh` are deleted; the mise tasks replace them.

## Files removed

- `install.sh`, `run_gui.sh` — replaced by mise tasks
- `requirements.txt` — replaced by `pyproject.toml` and `uv.lock`
- `panorama_splitter.py`, `panorama_splitter_gui.py` — split into the package

## Out of scope

- Any change to the produced images
- Configurable padding or section count
- Replacing tkinter
- CI
- Golden-image tests

## Success criteria

- `mise run check` passes from a clean clone.
- `mise run gui` launches the GUI and processes a real panorama.
- Output images are byte-comparable to those produced before the refactor for
  the same input.
- No `venv/` directory and no shell-script bootstrapping remain on the Unix path.
