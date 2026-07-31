# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Python tool that turns a panoramic JPG into four Instagram-ready images: one white-padded square holding the whole panorama, plus three 1080x1080 crops (left, middle, right thirds). Ships as a CLI and a tkinter GUI.

## Commands

Setup (creates `venv/`, installs Pillow, and on macOS installs Homebrew image libs / on Linux installs `python3-tk`):

```bash
./install.sh          # macOS / Linux
install.bat           # Windows
```

Run:

```bash
./run_gui.sh                                              # GUI (auto-installs if venv missing)
python panorama_splitter.py <input.jpg> [output_prefix]   # single file
python panorama_splitter.py <input_dir> <output_dir>      # batch
```

There is no test suite, linter, or CI. Verify changes by processing a real panorama and inspecting the four outputs.

## Architecture

Two files, one dependency direction: the GUI imports from the CLI module, never the reverse.

- `panorama_splitter.py` — all image logic.
  - `process_panoramic_image(input_path, output_prefix)` is the only unit of work. It writes four files derived from the prefix: `{prefix}_1_padded_square.jpg`, `{prefix}_2_section1.jpg`, `{prefix}_3_section2.jpg`, `{prefix}_4_section3.jpg`. This naming is a contract — `PanoramaSplitterGUI.update_preview()` reconstructs the same four paths to load previews, so renaming outputs breaks the GUI silently.
  - `process_folder()` globs `*.jpg *.JPG *.jpeg *.JPEG`, derives each prefix from the input basename, and swallows per-file exceptions so one bad image doesn't abort the batch.
- `panorama_splitter_gui.py` — tkinter front end. Guards the `import tkinter` at module load and exits with per-platform install instructions if it's missing. `process_folder_batch()` deliberately re-implements the glob-and-loop instead of calling `process_folder()`, because it needs per-file progress updates.

### Padding behaviour worth knowing

The "100px sides / 10px top-bottom" padding only picks the canvas size (`max(width+200, height+20)`); the panorama is then centered on that canvas. For any normal wide panorama the width term wins, so the real result is a square canvas 200px wider than the image with the panorama vertically centered — the top/bottom gap is whatever's left over, not 10px. The README describes the padding inverted relative to the code.

### Concurrency

The GUI starts a plain `threading.Thread` per run and calls `messagebox`/`ttk` methods directly from it. Only `update_preview` is marshalled back via `root.after()`. If you touch the threading code, route widget updates through `root.after()`.
