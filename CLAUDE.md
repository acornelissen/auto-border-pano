# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Masking Frame.** A masking frame is the darkroom device that holds printing paper under an enlarger: its blades mask the paper's edges, setting the format and leaving the white border. The name is the product, so keep the interface's vocabulary in that world — frames, formats, sources, the contact sheet.

Python tool that turns a panoramic JPG into a set of Instagram-ready images at a chosen aspect ratio (`4:5`/Portrait, `1:1`/Square, or `1.91:1`/Landscape): one white-padded frame holding the whole panorama, plus a variable number of zoomed detail frames derived from the ratio and the panorama's shape (minimum two). It can also compose two or three images — any mix of orientations — into a single diptych or triptych at one of those same ratios, with the arrangement chosen automatically. Ships as a CLI and a two-tab Qt (PySide6) GUI (Split, Compose).

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

Src-layout package at `src/maskingframe/`. Dependency direction is explicit and one-way: `geometry` and `layout` are leaves (neither imports the other, or anything else in the package); `compose` uses both `geometry` and `layout`; `pipeline` uses all three (`geometry`, `layout`, `compose`); `cli` and `gui/` use only `pipeline`, never `geometry`, `layout`, or `compose` directly.

- `geometry.py` — pure image transforms. Takes and returns `PIL.Image` objects, never touches the filesystem. Owns `AspectRatio` (the target-shape dataclass, with a `label` like "Portrait" and a `display` property like "Portrait (4:5)"), the `RATIOS` registry and `DEFAULT_RATIO`, `section_count()` (how many detail frames a panorama gets, floored at 2), `make_padded_frame()`, and `make_section()` (takes an index, a count, and a ratio). `RATIOS` is insertion-ordered Portrait, Square, Landscape (narrowest to widest) — that is the presentation order everywhere; never `sorted()` it, since alphabetical order puts `1.91:1` first and reads as noise. Fast to test in memory.
- `layout.py` — pure arithmetic, no PIL and no I/O. Solves composite arrangements by expressing each node's width as an affine function of its height, then scoring candidates on frame fill. For two images it tries a row and a column; for three it tries a row, a column, and the four variants with one large panel beside two stacked ones, and keeps whichever fills the frame best. Never crops, never permutes input order.
- `compose.py` — PIL in, PIL out, like `geometry.py`. Renders solved boxes onto an exact-size white canvas; refuses a box whose aspect disagrees with its image rather than distorting it.
- `pipeline.py` — the only module that touches the filesystem. Re-exports `AspectRatio`, `RATIOS` and `DEFAULT_RATIO` from `geometry` specifically so `cli.py` and `gui/` can offer ratio selection without importing `geometry` directly — that preserves the stated dependency direction. Do not "simplify" these re-exports away; that would force `cli`/`gui` to import `geometry` directly and break the invariant. `pipeline.py` also owns the output-filename contract (`{prefix}_1_padded.jpg`, `{prefix}_2_section1.jpg`, `{prefix}_3_section2.jpg`, ... one entry per detail frame) via `output_paths()`, plus `process_image()`, `find_panoramas()`, and `process_folder()`. `process_folder()` reports per-file failures in the returned `BatchResult` instead of raising, so one bad image doesn't abort a batch; callers (CLI, GUI) decide how to surface them. It also owns `compose_images()`, which solves a layout via `layout.solve()` and renders it via `compose.render()`, writing `{prefix}_diptych.jpg` or `{prefix}_triptych.jpg` and returning a `CompositeResult(path, layout_name)`. Unlike `process_image()`, `compose_images()` accepts portrait input — mixing orientations is the point.
- `cli.py` — argparse entry points (`maskingframe`, `maskingframe-gui`). Exposes `--ratio` (default `4:5`/Portrait) via a `type=` converter, not `choices=`, so it accepts both the bare ratio (`4:5`) and the name (`portrait`), case-insensitively; an unknown value is rejected with a message naming every accepted spelling. `--help` lists them in presentation order as `portrait|4:5, square|1:1, landscape|1.91:1`. Never exits on import; the PySide6-availability guard lives in `gui_main()`, not at module scope, so importing the package can never terminate the host process. Imports `run` from `gui`, the package, not from any specific submodule inside it.
- `gui/` — Qt (PySide6) front end. `theme.py` (the palette and one stylesheet; see "The theme" below), `shell.py` (the skeleton both tabs share: `RebateBand`, `TwoColumn`, the `section`/`help_label`/`data_label` helpers, `PathRow`, and two hand-drawn widgets — `Combo`, because flattening a combobox takes Qt's themed arrow with it, and `TabBand`, because `QTabWidget` centres its bar on macOS), `work.py` (running slow work off the GUI thread — read it before adding any), `app.py` (`MainWindow` and `run()`), `split_tab.py`, `compose_tab.py`, `strip.py` (`ContactStrip`) and `sources.py` (`SourcesList`). `gui/__init__.py` re-exports `run` and `MainWindow`; `cli.gui_main` imports `run` from the package, so that name must keep working. Only `pipeline` is imported from outside the package, never `geometry`, `layout` or `compose` directly.

Both tabs expose `subject`, `detail` and a `band_changed` signal, and nothing else. The band belongs to the shell rather than to either tab, so the tabs never know about the band or about each other.

### Concurrency

**This replaced the tkinter rule; it does not restate it.** There, nothing on a worker could touch any tk object and `root.after()` was the only sanctioned crossing back, so every worker hand-rolled that crossing with its own guard against the window closing mid-flight.

Qt queues a signal emitted from a worker thread to the receiver's thread automatically, and drops queued events for a destroyed receiver. So the rule is: **a job returns plain data, and the callback runs on the GUI thread.** Use `work.submit(job, on_done, on_failed)`. No marshalling, no window-closed guard, and never touch a widget inside a job.

Two things that did *not* go away:

- **Staleness.** A user can pick a second file before the first inspection returns, so every background answer carries a monotonically increasing token that the callback compares before it writes anything.
- **Passing context with the answer.** `inspect_source` runs off the GUI thread; if the callback re-read the ratio combobox it could caption one ratio's frame count with another ratio's name. Whatever the job was computed *for* travels back with its result.

### The theme

`gui/theme.py` is the design system, and it is presentation only. Two things about it are load-bearing:

- **The palette has range on purpose.** An earlier version was three greys within a few percent of each other with no white and no dark surface, and the whole interface read as a wash. `TABLE` → `PANEL` → `WELL` → `EDGE` → `INK`/`REBATE` spans white to near-black, and every text pairing clears WCAG AA. Don't add a value that sits between two existing ones without a reason.
- **`CHINAGRAPH` belongs to the primary action and to errors, and to nothing else.** It earns its salience by being the only saturated colour; a second accent costs the primary action its primacy. It is also why field focus is `INK` rather than red — a field turning red when you click into it reads as invalid.

No rounded corners, no drop shadows, no animation, anywhere. The direction is a light table and film rebate, both hard-edged; Qt making all three trivial is not a reason to spend them. `docs/design/2026-07-31-qt-port.md` records why the port happened and what the tkinter build got wrong.

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
