# Label ratios — report

Status: complete. `mise run check` green. Golden hashes in tests/test_pipeline.py untouched (all 14 pipeline tests passed unchanged).

Commit: 73cbd50

Test summary: 71 tests passed (up from ~56 before), covering label/display properties, narrowest-to-widest ordering, `--ratio` accepting both bare ratios and names case-insensitively, the unknown-value error message, and the GUI label-to-ratio mapping happening on the main thread.

## `mise exec -- uv run pano-split --help`

```
usage: pano-split [-h] [--ratio RATIO] input [output]

Split a panorama into a whole-panorama frame plus zoomed detail frames, sized
for an Instagram carousel. Accepts a single image or a folder of images.

positional arguments:
  input          input image or folder
  output         output prefix for a single image, or output folder

options:
  -h, --help     show this help message and exit
  --ratio RATIO  target aspect ratio for every frame: portrait|4:5,
                 square|1:1, landscape|1.91:1 (default: portrait). The number
                 of detail frames is derived from this.
```

## Concerns

None outstanding. The pre-commit hook's ruff-format auto-fix caused the first `git commit` attempt to abort without committing (formatting was applied to gui.py and test_cli.py) — re-staged and committed cleanly on the second attempt, no --no-verify used.

## Fix round 1

Closed the Minor finding: the label-to-ratio lookup in `process_images` (gui.py) used `next(...)` over a generator scan and would raise a raw `StopIteration` on an unrecognised `self.ratio` value. Unreachable from the UI today (the combobox is readonly and populated from the same source), but a latent footgun for any future programmatic caller.

Fix: added a module-level `_RATIO_BY_DISPLAY` dict (built once, not scanned per run) and changed the lookup to `_RATIO_BY_DISPLAY.get(selected_display, pipeline.DEFAULT_RATIO.name)`, so an unrecognised value degrades to the documented default instead of crashing. The lookup and fallback both still happen on the main thread in `process_images`; the worker still receives only a plain string.

Added `test_process_images_falls_back_to_default_ratio_for_an_unrecognised_label` in tests/test_gui.py, mirroring the existing `test_process_images_threads_the_selected_ratio_not_the_default` pattern: sets `app.ratio` to a bogus label, stubs `threading.Thread`, and asserts the worker receives `pipeline.DEFAULT_RATIO.name` with no exception propagating.

`mise run check` green (72 tests passed, up from 71). Golden hashes in tests/test_pipeline.py untouched.

Commit: 47e7492
