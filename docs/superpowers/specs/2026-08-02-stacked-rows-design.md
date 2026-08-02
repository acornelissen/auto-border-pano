# Laying frame 1 out as stacked rows

**Date:** 2026-08-02
**Status:** Design, approved for planning
**Bead:** maskingframe-kvl

## The problem

Frame 1 fits the whole panorama inside the output frame, so at a tall ratio
the aspect mismatch leaves most of the frame as border. `padded_border_percent`
made that border independently adjustable but could not move the ceiling: a
2.33:1 panorama covers 34.3% of a `4:5` frame with no border at all, because
what leaves the space is the shape difference.

Cutting the panorama into full-width rows, read top to bottom the way a long
plate is laid out on a page, roughly doubles the fill at the tall ratios and
crops nothing — every pixel is still shown, exactly once.

## What it is worth

Measured, as a share of frame 1's area, at the default 9% border and 4% gap:

| Panorama | Ratio | Off | 2 rows | 3 rows | 4 rows |
|---|---|---|---|---|---|
| 2.33:1 | `4:5` | 23.1% | **49.5%** | 20.3% | 10.5% |
| 2.33:1 | `1:1` | 28.9% | **35.5%** | 14.2% | 7.2% |
| 2.33:1 | `1.91:1` | **67.2%** | 18.5% | 7.4% | 3.7% |
| 3:1 | `4:5` | 17.9% | **63.7%** | 26.2% | 13.6% |
| 6:1 | `4:5` | 9.0% | 35.9% | **52.4%** | 27.1% |
| 6:1 | `1.91:1` | 26.1% | **47.7%** | 19.1% | 9.6% |

Rows help at the tall ratios and hurt at the wide one, and the best count
moves with both the panorama's shape and the target ratio. That is why this is
a choice rather than something the application decides.

## The model

### One field

`FrameStyle` gains `padded_rows: int = 1`. One row is exactly today's
behaviour, so every stored style, stored preset, scripted run and golden hash
is unaffected until somebody sets it. Validated as an integer from 1 to
`MAX_ROWS` (4).

Four is the ceiling because five rows never wins at any ratio for any panorama
shape this tool accepts, and an unbounded count would offer choices that are
arithmetic rather than photographs.

### How the rows are cut

`padded_rows` equal full-height strips, left to right. Strip *i* runs from
`floor(i * W / n + 0.5)` to `floor((i + 1) * W / n + 0.5)`, so adjacent strips
share an edge exactly and the last one ends on `W`. Nothing is lost to
rounding and nothing appears twice.

Equal cuts are a consequence, not a preference. The rows share a display
width, so unequal source widths would give unequal heights and the stack would
stop being a stack.

### How they are fitted

Each row has aspect `pano / n`. With `n` rows sharing display width `w`, each
is `w * n / pano` tall and the block is `w * n² / pano + (n - 1) * g` tall,
where `g` is `gutter_px`. So

```
w = min(inset_width, (inset_height - (n - 1) * g) * pano / n²)
```

and the block is centred in the inset box, which is the box
`padded_border_px` already defines — so frame 1's own border, when it has one,
governs rows exactly as it governs the single-row case.

### The gap

`gutter_percent` wide, `gutter_colour` filled: the same field, the same
control and the same meaning a composite already gives it — the space between
two pictures that belong together. Split's rail currently hides those
controls and would show them, which narrows the drift between the two rails
rather than widening it.

The gaps are painted before the rows, as `compose.render` already paints a
composite, so a row's rounded edge cannot leave a hairline of the wrong
colour.

### Saying what each choice is worth

`geometry.padded_rows_fill(pano_width, pano_height, ratio, style, rows)`
returns the share of the frame that many rows would cover — pure arithmetic,
no PIL, no I/O. `pipeline.row_options(pano_width, pano_height, ratio, style)`
returns one entry per count from 1 to `MAX_ROWS`, so the rail can label every
choice without rendering anything.

## The controls

**CLI.** `--frame1-rows N`, splits only, validated at parse time as an integer
in range. Documented beside `--frame1-border`.

**GUI.** A `Combo` in the Split tab's FORMAT section, below the frame count:

```text
[ Off — the whole panorama · 23%   v ]
    Off — the whole panorama        23%
    Two rows                        49%
    Three rows                      20%
    Four rows                       11%
```

Recomputed whenever the ratio, the border, frame 1's border or the gap moves,
since every one of those changes the answer. Until a source is loaded there is
no panorama shape and so no percentages; the choices read without them.

## What does not change

`make_section`, `border_px`, the detail frames, the composite path, the
position model, and frame 1's promise to show the whole panorama. Rows change
how it is laid out, not what it contains.

## A note on where this is heading

`padded_border_percent` and `padded_rows` are now two fields on `FrameStyle`
that only frame 1 reads. That is still cheaper than a type of its own. If a
third appears, the honest move is a `Frame1Style` rather than more prefixed
fields.

## Testing

- **The cut**: the strips tile the panorama exactly — adjacent edges meet, the
  first starts at 0 and the last ends at `W` — at every count and at panorama
  widths that do not divide evenly.
- **The fit**: the block never exceeds the inset box; every row is the same
  size; each row's aspect matches `pano / n` within the rounding bound.
- **Backwards compatibility**: `padded_rows=1` is byte-identical to the field
  being absent, and the golden hashes do not move.
- **Frame 1's own border still governs**: rows fitted with
  `padded_border_percent` set use that inset box, not the shared one.
- **The advertised number is the real one**: for each count and ratio,
  `padded_rows_fill` is checked against the *rendered* frame — the non-border
  area measured off the actual image — not against a second copy of the same
  formula. This is the claim most likely to drift and the one a user acts on.
- **The table above**: the six measured rows are asserted, so the spec's own
  justification fails if the arithmetic moves.
- **`cli`**: `--frame1-rows` reaches the style; out of range fails at parse
  time; omitted leaves the field at 1.
- **The tab**: the combo lists every count with its fill; choosing one
  re-renders; the numbers change with the ratio and the border; with no source
  loaded the choices carry no percentages.
