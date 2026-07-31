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
