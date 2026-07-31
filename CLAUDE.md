# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Python tool that turns a panoramic JPG into four Instagram-ready images: one white-padded square holding the whole panorama, plus three 1080x1080 crops (left, middle, right thirds). Ships as a CLI and a tkinter GUI.

## Commands

Setup (installs Python and uv via mise, then syncs dependencies):

```bash
mise install
mise run setup
```

Run:

```bash
mise run gui                    # GUI
mise run split -- <input.jpg> [output_prefix]   # single file
mise run split -- <input_dir> [output_dir]      # batch, defaults output_dir to ./output
```

Verify:

```bash
mise run check   # ruff lint, mypy --strict, pytest — run this before committing
```

`mise run check` is the single command that must pass. It runs `lint`, `typecheck`, and `test` (see `.mise.toml` for the individual tasks).

## Architecture

Src-layout package at `src/auto_border_pano/`, four modules with one dependency direction: `geometry` <- `pipeline` <- `cli`/`gui`.

- `geometry.py` — pure image transforms. Takes and returns `PIL.Image` objects, never touches the filesystem. Owns `make_padded_square()` and `make_section()`. Fast to test in memory.
- `pipeline.py` — the only module that touches the filesystem. Owns the output-filename contract (`{prefix}_1_padded_square.jpg`, `{prefix}_2_section1.jpg`, `{prefix}_3_section2.jpg`, `{prefix}_4_section3.jpg`) via `output_paths()`, plus `process_image()`, `find_panoramas()`, and `process_folder()`. `process_folder()` reports per-file failures in the returned `BatchResult` instead of raising, so one bad image doesn't abort a batch; callers (CLI, GUI) decide how to surface them.
- `cli.py` — argparse entry points (`pano-split`, `pano-split-gui`). Never exits on import; the tkinter-availability guard lives in `gui_main()`, not at module scope, so importing the package can never terminate the host process.
- `gui.py` — tkinter front end. Imports `pipeline`, never `geometry`, and reuses `pipeline.output_paths()` for preview loading so the naming contract can't drift between the two.

### Padding behaviour worth knowing

The canvas size is `max(width + 200, height + 20)`; the panorama is then centered on that canvas. For any normal wide panorama the width term wins, so the real result is a square canvas 200px wider than the image with the panorama centered — the top/bottom gap is whatever's left over, not a fixed 10px. This is deliberate and is locked in place by characterisation tests in `tests/`; do not "fix" it without checking those tests first.

### Behaviour changes from the pre-refactor scripts

- `find_panoramas()` no longer double-counts files on case-insensitive filesystems (the old code globbed `*.jpg` and `*.JPG` separately, matching the same file twice).
- Folder mode defaults its output to `./output` when omitted; the old CLI required it and errored otherwise.
- Batch failures are reported rather than silently swallowed: the CLI exits non-zero and prints failures to stderr, and the GUI status reads "Processed N of M, K failed" instead of always claiming success.

### Concurrency

The GUI starts a plain `threading.Thread` per run and calls `messagebox`/`ttk` methods directly from it. Only widget mutation on completion (`_finish`, `_finish_batch`, `_set_progress`) is marshalled back via `root.after()`. If you touch the threading code, keep all widget updates on the main thread via `root.after()`.
