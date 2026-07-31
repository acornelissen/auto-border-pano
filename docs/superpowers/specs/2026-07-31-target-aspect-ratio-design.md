# Selectable target aspect ratio

Date: 2026-07-31
Status: approved, not yet implemented

## Goal

Let the user choose which Instagram aspect ratio they are targeting — 1:1,
4:5, or 1.91:1 — and shape every output to it, including how many sections
the panorama is split into.

## Why

The tool currently hard-codes 1080x1080 squares and three sections. Instagram
now supports three feed ratios, and a wide panorama in a square frame wastes
a large amount of vertical space that a 1.91:1 frame would not.

Instagram forces every image in a carousel to share one aspect ratio; mixing
them causes cropping. One global ratio setting therefore drives all outputs,
rather than per-output settings.

## Decisions

| Question | Decision |
| -------- | -------- |
| Which outputs does the ratio affect? | All of them — the padded frame and every section |
| Does section count depend on the ratio? | Yes, derived to minimise cropping |
| Rounding | Round to nearest; each section is slightly wider than a perfect tile and gets center-cropped |
| Default ratio | 4:5 |

## The ratios

`AspectRatio` is a frozen dataclass carrying a name and an output pixel size,
so the ratio and the output dimensions cannot drift apart:

| Name | Output size |
| ---- | ----------- |
| `1:1` | 1080 x 1080 |
| `4:5` | 1080 x 1350 |
| `1.91:1` | 1080 x 566 |

All three are 1080 wide, which is Instagram's working resolution. The ratio
value used in arithmetic is `output_width / output_height`.

## Section count

An exact tile is `pano_height * ratio` wide. The count is that divided into
the panorama width, rounded to nearest, with a floor of 1:

```text
tile = pano_height * ratio.value
count = max(1, round(pano_width / tile))
```

For a 3000x800 panorama: 2 sections at 1.91:1, 4 at 1:1, 5 at 4:5.

Sections then tile the full panorama width evenly (`pano_width // count`),
so each is slightly wider or narrower than a perfect tile and the cover-crop
absorbs the difference. Nothing is discarded except the integer-division
remainder at the right edge, as today.

Consequence, accepted deliberately: at 1:1 this produces four sections where
the current code produces three. The exact pre-change output is no longer
reachable at any setting.

## Changes to geometry.py

- `AspectRatio` dataclass plus the three instances and a name-to-instance
  lookup for CLI and GUI parsing.
- `section_count(pano_width, pano_height, ratio) -> int` — new, per the
  formula above.
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
  It is no longer square at two of the three ratios, so the old name would be
  wrong.
- `process_image(input_path, output_prefix, ratio)` gains the ratio parameter
  and computes the section count from the opened image's dimensions.
- `BatchResult` is unchanged in shape, but `succeeded_count` can no longer
  divide by a constant 4. It tracks an explicit counter instead — which also
  closes a residual flagged in the previous branch's review.

## Changes to cli.py

`--ratio {1:1,4:5,1.91:1}`, defaulting to `4:5`. An unknown value is an
argparse error. The ratio is echoed in the per-file output so it is obvious
which setting produced a given run.

## Changes to gui.py

A labelled combobox above the Process button, listing the three ratios,
defaulting to 4:5. Read on the main thread in `process_images` and passed
into the worker as a plain value, consistent with the existing threading
invariant that no worker thread touches a tk object.

The preview panel currently holds exactly four fixed labels. It must build
its labels per run, since the count now varies from 1 to about 6. Preview
titles become "Padded" plus "Section 1..N" rather than the current
hard-coded left/middle/right naming.

## Testing

- Unit tests for `section_count` at each ratio, including the edge cases that
  motivated this section: a nearly-square input, a panorama narrower than one
  tile (must floor to 1, not 0), and a panorama whose width divides exactly.
- Pixel-position assertions for `make_section` and `make_padded_frame` at each
  ratio, in the style established previously — enough to kill an offset
  mutation.
- The existing single golden byte-identity test is replaced by one golden per
  ratio. This is a deliberate break: the old golden asserts three sections at
  1:1 and is now wrong. Per-ratio goldens also close the residual from the
  previous review, where the single 320x120 fixture only exercised one branch
  of `make_section` — a 1.91:1 golden covers the wide path and a 4:5 golden
  the tall one.
- A test asserting the GUI's preview-title generation stays in step with the
  section count, replacing the previous fixed-length assertion.

## Manual verification

The user is supplying roughly ten real panoramas, to be placed in a
gitignored `samples/` directory. These are for eyeballing whether the derived
section counts and crops look right at each ratio — a judgement no automated
test makes. `samples/` is added to `.gitignore`.

## Out of scope

- Per-output ratios, or a carousel mixing ratios
- A user-specified section count override
- Ratios beyond the three Instagram feed sizes
- Changing the padding constants
- Reachability of the exact pre-change output

## Success criteria

- `mise run check` passes.
- Each of the three ratios produces a padded frame and N sections at exactly
  the documented pixel dimensions.
- A 3000x800 panorama yields 2 sections at 1.91:1, 4 at 1:1, and 5 at 4:5.
- The GUI's preview panel adapts to the section count without leftover or
  missing panes when switching ratios between runs.
- README and CLAUDE.md describe the ratio option, the derived section count,
  and the renamed padded output.
