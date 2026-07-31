# Selectable target aspect ratio

Date: 2026-07-31
Status: approved, not yet implemented

## Goal

Let the user choose which Instagram aspect ratio they are targeting — 1:1,
4:5, or 1.91:1 — and shape every output to it, including how many detail
frames the panorama is split into.

## What the outputs are for

This was clarified during design and drives everything below.

- **Frame 1** is the whole panorama on a white canvas. It is the establishing
  shot: the viewer sees the entire image at once.
- **Frames 2..N** are a *zoom*. They exist so a viewer can see detail that is
  illegible in frame 1. They are not merely a tiling of the panorama.

The consequence: a single detail frame is worthless, because one "zoomed"
frame showing the whole panorama is just frame 1 again. The section count
therefore has a floor of 2.

Instagram forces every image in a carousel to share one aspect ratio, so one
global ratio setting drives all outputs rather than per-output settings.

## Decisions

| Question | Decision |
| -------- | -------- |
| Which outputs does the ratio affect? | All of them |
| Does the detail-frame count depend on the ratio? | Yes, derived by tiling |
| Rounding | Round to nearest, floored at 2 |
| Default ratio | 4:5 |
| Frame 1 white space at 4:5 | Accepted; the border is the aesthetic |
| Portrait inputs | Rejected with a clear error |
| Decompression-bomb limit | Raised |

## Grounding in real panoramas

Design decisions were checked against 18 of the user's own scans rather than
synthetic examples. This corrected an early draft that assumed 3:1 inputs.

- 16 are landscape; aspect clusters at **2.2–2.5:1** (14 files), with two
  large-format scans at 3.0:1.
- 2 are portrait (0.43 and 0.45) and are not panoramas.
- All are RGB. Largest is 19921x6607, about 132 megapixels.

Resulting counts with the floor of 2 applied:

| Input aspect | 1.91:1 | 1:1 | 4:5 |
| ------------ | ------ | --- | --- |
| 2.2–2.5:1 (typical) | 2 | 2 | 3 |
| 3.0:1 (large format) | 2 | 3 | 4 |

At 4:5 the typical panorama gives 3 detail frames at 3x zoom, and the ten
2.40:1 scans tile at exactly 0.80 — a perfect 4:5 with no cropping at all.
This is why 4:5 is the default.

## The ratios

`AspectRatio` is a frozen dataclass carrying a name and an output pixel size,
so the ratio and the output dimensions cannot drift apart:

| Name | Output size |
| ---- | ----------- |
| `1:1` | 1080 x 1080 |
| `4:5` | 1080 x 1350 |
| `1.91:1` | 1080 x 566 |

All are 1080 wide, Instagram's working resolution. The ratio value used in
arithmetic is `output_width / output_height`.

## Detail-frame count

An exact tile is `pano_height * ratio` wide. The count is that divided into
the panorama width, rounded to nearest, floored at 2:

```text
tile = pano_height * ratio.value
count = max(2, round(pano_width / tile))
```

The floor is what makes the frames a zoom rather than a restatement of the
whole panorama. Without it, a 2.4:1 panorama at 1.91:1 yields a single frame
— the case that motivated this rule.

Frames then tile the full panorama width evenly (`pano_width // count`), so
each is slightly wider or narrower than a perfect tile and the cover-crop
absorbs the difference. Nothing is discarded except the integer-division
remainder at the right edge, as today.

Consequence, accepted deliberately: at 1:1 a typical panorama now produces
two detail frames where the current code produces three. The exact
pre-change output is not reachable at any setting.

## Rejecting portrait input

An input whose width is less than its height is not a panorama. Both
non-panoramas in the sample set are portrait shots that were included by
accident.

`pipeline.process_image` raises a `ValueError` naming the file and its
dimensions when `width < height`. In batch mode this lands in
`BatchResult.failed` like any other per-file failure, so the batch continues
and the CLI and GUI both report it. In single-file mode the CLI prints the
message to stderr and returns 1.

Square input (width == height) is allowed; it is degenerate but not wrong,
and rejecting it would need an arbitrary threshold.

## Decompression-bomb limit

The largest sample is 132MP against PIL's ~178MP default, so a larger
large-format scan would be rejected as a failed file with a message that
would not obviously explain why. `pipeline` raises `Image.MAX_IMAGE_PIXELS`
on import. The guard exists to protect against hostile downloads; these are
the user's own scans. The broadened exception handling added in the previous
branch remains the safety net for genuinely malformed files.

## Changes to geometry.py

- `AspectRatio` dataclass, the three instances, and a name-to-instance lookup
  for CLI and GUI parsing.
- `section_count(pano_width, pano_height, ratio) -> int` — new, per the
  formula above, including the floor of 2.
- `section_bounds(width, index, count)` — `count` becomes a parameter; the
  `SECTION_COUNT` module constant goes away.
- `make_section(image, index, count, ratio)` — scale by
  `max(target_w / crop_w, target_h / crop_h)` to cover the target, then
  center-crop. This one expression replaces the current
  `if crop_width > crop_height` two-branch form, which is the same logic
  specialised to a square target.
- `make_padded_square` becomes `make_padded_frame(image, ratio)`. Canvas
  width is `pano_width + 2 * SIDE_PADDING`, preserving the existing 100px
  side padding; canvas height is `round(canvas_width / ratio.value)`. If that
  height is less than `pano_height + 2 * VERTICAL_PADDING`, the canvas is
  instead sized from the height — `canvas_height = pano_height + 2 *
  VERTICAL_PADDING` and `canvas_width = round(canvas_height * ratio.value)` —
  so the ratio is always exact and the panorama always fits with at least the
  minimum padding on every side. The panorama stays centered, as today.

`SIDE_PADDING`, `VERTICAL_PADDING` and `BACKGROUND` are unchanged.

## Changes to pipeline.py

- `OUTPUT_SUFFIXES` stops being a fixed 4-tuple. `output_paths(prefix, count)`
  generates `{prefix}_1_padded.jpg` followed by `{prefix}_{n+1}_section{n}.jpg`
  for n in 1..count.
- The padded output is renamed from `_1_padded_square.jpg` to `_1_padded.jpg`.
  It is not square at two of the three ratios, so the old name would lie.
- `process_image(input_path, output_prefix, ratio)` gains the ratio parameter,
  rejects portrait input, and computes the count from the image's dimensions.
- `BatchResult.succeeded_count` can no longer divide by a constant 4, since
  the count now varies per file. It tracks an explicit counter — which also
  closes a residual flagged in the previous branch's review.

## Changes to cli.py

`--ratio {1:1,4:5,1.91:1}`, defaulting to `4:5`. An unknown value is an
argparse error. The chosen ratio and the resulting frame count are echoed per
file, so it is obvious which setting produced a given run.

## Changes to gui.py

A labelled combobox above the Process button listing the three ratios,
defaulting to 4:5. It is read on the main thread in `process_images` and
passed into the worker as a plain value, consistent with the existing
invariant that no worker thread touches a tk object.

The preview panel currently holds exactly four fixed labels. It must build
its labels per run, since the count now varies from 3 to 5 frames total.
Preview titles become "Whole" plus "Detail 1..N", replacing the current
hard-coded left/middle/right naming, which stops being meaningful once the
count varies.

## Testing

- `section_count` at each ratio, including: the floor of 2 actually applying
  where tiling wants 1; a panorama narrower than one tile; and a width that
  divides exactly.
- Portrait input rejected: a `ValueError` in single-file mode, and a recorded
  failure that does not abort the batch in folder mode.
- Pixel-position assertions for `make_section` and `make_padded_frame` at each
  ratio, in the style established previously — enough to kill an offset
  mutation.
- The existing single golden byte-identity test is replaced by one golden per
  ratio. This is a deliberate break: the old golden asserts three sections at
  1:1 and is now wrong. Per-ratio goldens also close the residual from the
  previous review, where the single 320x120 fixture exercised only one branch
  of `make_section`.
- The GUI's preview-title generation stays in step with the frame count,
  replacing the previous fixed-length assertion.

## Fix carried in with this work

The pre-commit hooks installed by the previous branch have never run: they
invoke `uv run …`, but `uv` is a mise-managed tool and is not on `PATH` when
git spawns a hook, so every hook fails with "Executable `uv` not found". The
hooks are repaired as part of this work, since every commit here depends on
them.

## Manual verification

The user's 18 real panoramas live in a gitignored `samples/` directory. After
implementation, a run over the landscape ones at each ratio is eyeballed to
confirm the frame counts and crops look right — a judgement no automated test
makes. The two portrait files double as a live check of the rejection path.

## Out of scope

- Per-output ratios, or a carousel mixing ratios
- A user-specified frame-count override
- Ratios beyond the three Instagram feed sizes
- Changing the padding constants
- Reachability of the exact pre-change output

## Success criteria

- `mise run check` passes, and the pre-commit hooks actually run.
- Each ratio produces frame 1 plus N detail frames at exactly the documented
  pixel dimensions, with N never below 2.
- A typical 2.4:1 panorama yields 2 detail frames at 1.91:1, 2 at 1:1, and 3
  at 4:5; a 3.0:1 panorama yields 2, 3 and 4.
- Portrait input is rejected with a message naming the file and its size, and
  does not abort a batch.
- The GUI's preview panel adapts to the frame count without leftover or
  missing panes when switching ratios between runs.
- README and CLAUDE.md describe the ratio option, the derived frame count,
  the portrait rejection, and the renamed padded output.
