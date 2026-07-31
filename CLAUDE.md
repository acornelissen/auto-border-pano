# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Python tool that turns a panoramic JPG into a set of Instagram-ready images at a chosen aspect ratio (`4:5`/Portrait, `1:1`/Square, or `1.91:1`/Landscape): one white-padded frame holding the whole panorama, plus a variable number of zoomed detail frames derived from the ratio and the panorama's shape (minimum two). It can also compose two or three images — any mix of orientations — into a single diptych or triptych at one of those same ratios, with the arrangement chosen automatically. Ships as a CLI and a two-tab tkinter GUI (Split, Compose).

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

Src-layout package at `src/auto_border_pano/`. Dependency direction is explicit and one-way: `geometry` and `layout` are leaves (neither imports the other, or anything else in the package); `compose` uses both `geometry` and `layout`; `pipeline` uses all three (`geometry`, `layout`, `compose`); `cli` and `gui/` use only `pipeline`, never `geometry`, `layout`, or `compose` directly.

- `geometry.py` — pure image transforms. Takes and returns `PIL.Image` objects, never touches the filesystem. Owns `AspectRatio` (the target-shape dataclass, with a `label` like "Portrait" and a `display` property like "Portrait (4:5)"), the `RATIOS` registry and `DEFAULT_RATIO`, `section_count()` (how many detail frames a panorama gets, floored at 2), `make_padded_frame()`, and `make_section()` (takes an index, a count, and a ratio). `RATIOS` is insertion-ordered Portrait, Square, Landscape (narrowest to widest) — that is the presentation order everywhere; never `sorted()` it, since alphabetical order puts `1.91:1` first and reads as noise. Fast to test in memory.
- `layout.py` — pure arithmetic, no PIL and no I/O. Solves composite arrangements by expressing each node's width as an affine function of its height, then scoring candidates on frame fill. For two images it tries a row and a column; for three it tries a row, a column, and the four variants with one large panel beside two stacked ones, and keeps whichever fills the frame best. Never crops, never permutes input order.
- `compose.py` — PIL in, PIL out, like `geometry.py`. Renders solved boxes onto an exact-size white canvas; refuses a box whose aspect disagrees with its image rather than distorting it.
- `pipeline.py` — the only module that touches the filesystem. Re-exports `AspectRatio`, `RATIOS` and `DEFAULT_RATIO` from `geometry` specifically so `cli.py` and `gui/` can offer ratio selection without importing `geometry` directly — that preserves the stated dependency direction. Do not "simplify" these re-exports away; that would force `cli`/`gui` to import `geometry` directly and break the invariant. `pipeline.py` also owns the output-filename contract (`{prefix}_1_padded.jpg`, `{prefix}_2_section1.jpg`, `{prefix}_3_section2.jpg`, ... one entry per detail frame) via `output_paths()`, plus `process_image()`, `find_panoramas()`, and `process_folder()`. `process_folder()` reports per-file failures in the returned `BatchResult` instead of raising, so one bad image doesn't abort a batch; callers (CLI, GUI) decide how to surface them. It also owns `compose_images()`, which solves a layout via `layout.solve()` and renders it via `compose.render()`, writing `{prefix}_diptych.jpg` or `{prefix}_triptych.jpg` and returning a `CompositeResult(path, layout_name)`. Unlike `process_image()`, `compose_images()` accepts portrait input — mixing orientations is the point.
- `cli.py` — argparse entry points (`pano-split`, `pano-split-gui`). Exposes `--ratio` (default `4:5`/Portrait) via a `type=` converter, not `choices=`, so it accepts both the bare ratio (`4:5`) and the name (`portrait`), case-insensitively; an unknown value is rejected with a message naming every accepted spelling. `--help` lists them in presentation order as `portrait|4:5, square|1:1, landscape|1.91:1`. Never exits on import; the tkinter-availability guard lives in `gui_main()`, not at module scope, so importing the package can never terminate the host process. Imports `run` from `gui`, the package, not from any specific submodule inside it.
- `gui/` — tkinter front end, now a package rather than a single module: `theme.py` (the light-table design system — five colour tokens, three font roles, one 6/12/24 spacing scale, and `apply()`, which switches ttk to the `clam` theme; see "The theme" below), `shell.py` (the layout skeleton both tabs are built on: `TwoColumn` — a fixed 340pt control rail plus a light table that takes the rest — the `section()` heading helper, and `RebateBand`, the drawn header. Both tabs' rails carry the same sections in the same order, subject → FORMAT → DESTINATION → primary action; that ordering is the point of the module and re-diverging it would undo it), `app.py` (the notebook shell — owns the root window and the two-tab `ttk.Notebook`, 900x700), `split_tab.py` (the original single-panorama/batch workflow, unchanged in behaviour), `compose_tab.py` (the diptych/triptych workflow: pick 2-3 images, reorder with Up/Down, pick a ratio, see the winning layout name), and `strip.py` (the `ContactStrip` Canvas shared by both tabs — one continuous film strip on a shared rebate, with frame numbers, per-frame stencils, and an unexposed empty state it renders from construction. It replaced `preview.py`'s `PreviewPanes`, whose four sunken boxes stayed literally empty until the first successful run). `gui/__init__.py` re-exports `run`, `PanoramaSplitterGUI` and `preview_titles` — `cli.gui_main` imports `run` from the package, and the test suite imports the other two, so those three names must keep working even if the internal module layout changes further; do not "tidy" the re-exports away. Only `pipeline` is imported from outside the package, never `geometry`, `layout`, or `compose` directly. The strip's frames are rebuilt on every run because the frame count varies with the ratio and the source images.

Two things in `strip.py` are load-bearing. Tk drops an image the instant its `PhotoImage` is garbage collected, rendering a blank, so the strip holds its own references — that discipline is inherited from `PreviewPanes` and a test forces a `gc.collect()` to keep it honest. And all chrome is drawn with native Canvas primitives, never pre-rendered bitmaps: an `ImageTk` blit maps image pixels to points and goes soft on a 2x display, so bitmaps are only ever used for the user's own photographs, where softness is invisible at thumbnail size. The design has no shadows, no rounded corners and no animation for related reasons — see the feasibility table in the design plan before adding any.

### The theme

`gui/theme.py` is the design system, and it is presentation only — no widget in it knows what a panorama is, and nothing outside `gui/` imports it. It is being applied in stages; `docs/design/2026-07-31-gui-design-plan.md` is the plan and `docs/design/IMPLEMENTATION-PROGRESS.md` tracks which stages have landed.

Three things about it are load-bearing rather than cosmetic:

- **`apply()` must run before any widget is built.** It calls `style.theme_use("clam")`, and a ttk theme change only reliably restyles widgets created after it. `app.run()` calls it first for that reason.
- **`clam` is a prerequisite, not a preference.** Under macOS's native `aqua` theme ttk silently ignores `background`, `fieldbackground` and `bordercolor`, so none of the palette would take effect. Losing the native look is the accepted trade. It also means the app is deliberately light-only — following the system dark mode would undo the light-table direction, and `clam` gives you no automatic appearance switch anyway.
- **`CHINAGRAPH` belongs to the primary action alone.** It is the only saturated colour in the app and it earns its salience by being alone; the moment a second element claims it the primary action stops reading as primary. `test_theme.py::test_primary_button_is_the_only_chinagraph_background` enforces this against every registered style, which is why the progress bar fills in `REBATE` rather than red.

Contrast is a floor, not a nicety: `SPROCKET` is 3.3:1 on `LIGHTBOX` and clears WCAG AA only at the 3:1 large-text threshold, so it is restricted to the 12pt bold stencil styles and to non-text rules. Anything smaller uses `INK_SECONDARY` (7.1:1). Don't reach for `SPROCKET` for body copy.

Caps are applied in the string, not by the style — ttk has no text-transform.

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
