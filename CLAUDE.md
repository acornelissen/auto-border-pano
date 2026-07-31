# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Python tool that turns a panoramic JPG into a set of Instagram-ready images at a chosen aspect ratio (`4:5`/Portrait, `1:1`/Square, or `1.91:1`/Landscape): one white-padded frame holding the whole panorama, plus a variable number of zoomed detail frames derived from the ratio and the panorama's shape (minimum two). Ships as a CLI and a tkinter GUI.

## Commands

Setup (installs Python and uv via mise, then syncs dependencies):

```bash
mise install
mise run setup
```

`mise run setup` also installs the pre-commit hooks (`pre-commit install --hook-type pre-commit --hook-type pre-push`), so a fresh clone gets `ruff`/`ruff-format` on commit and `mypy`/`pytest` on push per `.pre-commit-config.yaml`.

Run:

```bash
mise run gui                    # GUI
mise run split -- <input.jpg> [output_prefix] --ratio 4:5   # single file
mise run split -- <input_dir> [output_dir] --ratio 1:1      # batch, defaults output_dir to ./output
```

Verify:

```bash
mise run check   # ruff lint, mypy --strict, pytest — run this before committing
```

`mise run check` is the single command that must pass. It runs `lint`, `typecheck`, and `test` (see `mise.toml` for the individual tasks).

## Architecture

Src-layout package at `src/auto_border_pano/`, four modules with one dependency direction: `geometry` <- `pipeline` <- `cli`/`gui`.

- `geometry.py` — pure image transforms. Takes and returns `PIL.Image` objects, never touches the filesystem. Owns `AspectRatio` (the target-shape dataclass, with a `label` like "Portrait" and a `display` property like "Portrait (4:5)"), the `RATIOS` registry and `DEFAULT_RATIO`, `section_count()` (how many detail frames a panorama gets, floored at 2), `make_padded_frame()`, and `make_section()` (takes an index, a count, and a ratio). `RATIOS` is insertion-ordered Portrait, Square, Landscape (narrowest to widest) — that is the presentation order everywhere; never `sorted()` it, since alphabetical order puts `1.91:1` first and reads as noise. Fast to test in memory.
- `pipeline.py` — the only module that touches the filesystem. Re-exports `AspectRatio`, `RATIOS` and `DEFAULT_RATIO` from `geometry` specifically so `cli.py` and `gui.py` can offer ratio selection without importing `geometry` directly — that preserves the stated dependency direction (`geometry` <- `pipeline` <- `cli`/`gui`). Do not "simplify" these re-exports away; that would force `cli`/`gui` to import `geometry` directly and break the invariant. `pipeline.py` also owns the output-filename contract (`{prefix}_1_padded.jpg`, `{prefix}_2_section1.jpg`, `{prefix}_3_section2.jpg`, ... one entry per detail frame) via `output_paths()`, plus `process_image()`, `find_panoramas()`, and `process_folder()`. `process_folder()` reports per-file failures in the returned `BatchResult` instead of raising, so one bad image doesn't abort a batch; callers (CLI, GUI) decide how to surface them.
- `cli.py` — argparse entry points (`pano-split`, `pano-split-gui`). Exposes `--ratio` (default `4:5`/Portrait) via a `type=` converter, not `choices=`, so it accepts both the bare ratio (`4:5`) and the name (`portrait`), case-insensitively; an unknown value is rejected with a message naming every accepted spelling. `--help` lists them in presentation order as `portrait|4:5, square|1:1, landscape|1.91:1`. Never exits on import; the tkinter-availability guard lives in `gui_main()`, not at module scope, so importing the package can never terminate the host process.
- `gui.py` — tkinter front end. Imports `pipeline`, never `geometry`, and reuses `pipeline.output_paths()` for preview loading so the naming contract can't drift between the two. The ratio combobox shows each `ratio.display` (e.g. "Portrait (4:5)") in presentation order; `process_images` maps the selected display string back to the bare ratio name on the main thread before handing a plain string to the worker thread — the mapping must stay on the main thread, since no worker thread may read or write any tkinter object. The preview panel is rebuilt on every run because the detail-frame count varies with the ratio and the source panorama.

### Padding behaviour worth knowing

`make_padded_frame()` fits the panorama inside the target output frame, inset by `SIDE_PADDING` (100px) on all four sides, preserving the panorama's own aspect ratio, then centers it on a full-size white canvas. `SIDE_PADDING` describes the finished output frame, not the source image — whichever axis binds gets exactly 100px, and the other axis gets whatever's left over. For a wide panorama at `1:1` or `4:5` that's normally the width; at `1.91:1` (inset box ratio 2.4:1) a panorama flatter than 2.4:1 — including this project's own 2.33:1 samples — binds on height instead, so watch which axis you're measuring before assuming 100px means "left and right". That asymmetry is inherent: the panorama's aspect doesn't match the frame's, and frame 1 must show the whole panorama uncropped, so the border can't be made even without cropping content away.

At a tall ratio like `4:5`, most of the padded frame is white border — that is the intended aesthetic, not a bug.

`make_padded_frame()` scales the panorama directly to its fitted size with `Image.Resampling.LANCZOS` and pastes it onto a white canvas already sized to `(ratio.width, ratio.height)` — the same pixel size as every detail frame — rather than compositing at source scale and downscaling. That keeps a large-format scan from briefly allocating a huge intermediate canvas as well as avoiding a many-megabyte first frame beside sub-megabyte detail frames.

### Behaviour changes from the pre-refactor scripts

- `find_panoramas()` no longer double-counts files on case-insensitive filesystems (the old code globbed `*.jpg` and `*.JPG` separately, matching the same file twice).
- Folder mode defaults its output to `./output` when omitted; the old CLI required it and errored otherwise.
- Batch failures are reported rather than silently swallowed: the CLI exits non-zero and prints failures to stderr, and the GUI status reads "Wrote N of M images at {ratio.display}, K failed" instead of always claiming success. The GUI also names the ratio and frame count for single-file runs ("Wrote N detail frames at {ratio.display}"), and shows an explicit "No panoramas found" dialog instead of a green success dialog when a folder has no JPEGs.
- `process_image()` converts the source to RGB (`.convert("RGB")`) before processing, so a grayscale or RGBA/P-mode source now produces RGB sections instead of preserving its original mode. The legacy script had no such conversion and crashed with "cannot write mode RGBA as JPEG" on non-RGB inputs; the refactor fixes that but means the "byte-identical to the legacy output" guarantee is scoped to RGB inputs.
- The output is no longer a fixed four images (one padded square plus three 1080x1080 sections). It is one padded frame plus a variable number of detail frames — never fewer than two — derived from the chosen ratio and the panorama's aspect ratio via `section_count()`. The frames after the first are a zoom, not a tiling, which is why the count floors at two rather than one.
- Portrait input (width < height) is rejected with a `ValueError` naming the offending file; in a batch this is caught per-file so the rest of the batch still runs.
- `Image.MAX_IMAGE_PIXELS` is set to `None` in `pipeline.py`. The user's own large-format scans can exceed Pillow's ~178MP decompression-bomb guard (the largest sample here is 132MP); lifting the guard stops a legitimate scan being reported as a corrupt file. Malformed input is still caught by the per-file exception handling in `process_folder()`.
- The padded output was renamed from `{prefix}_1_padded_square.jpg` to `{prefix}_1_padded.jpg`, since it is only square when the target ratio is `1:1`.

### Concurrency

`process_images()` reads the tk `StringVar`s on the main thread and passes them into the worker as plain strings via the thread's `args`. `_run_single`/`_run_batch` (running on the worker thread) call only into `pipeline` and touch no tk object at all; every result is handed to `self.root.after(...)`, which runs `_finish`, `_finish_batch`, and `_set_progress` back on the main thread. Invariant to preserve: nothing on the worker thread may read or write a tk object, including tk variables — `root.after()` is the only sanctioned crossing back to the main thread.
