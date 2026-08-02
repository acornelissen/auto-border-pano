# Giving frame 1 its own border

**Date:** 2026-08-02
**Status:** Design, approved for planning
**Bead:** maskingframe-yzg

## The problem

`make_padded_frame` fits the whole panorama inside the output frame inset by
the border on all four sides. At `4:5` most of the frame is border. That is
the intended aesthetic and stays the default, but there is no way to say
"fill more of it" short of changing the ratio — and turning the border down
changes every detail frame that carries one, and the composite, and the
gutter's neighbours.

## What this can and cannot do

Measured, for a 2.33:1 panorama, as a share of frame 1's area:

| Ratio | 9% (default) | 4% | 0% |
|---|---|---|---|
| `4:5` | 23.1% | 29.1% | 34.3% |
| `1:1` | 28.9% | 36.4% | 42.9% |
| `1.91:1` | 67.2% | 75.1% | 81.9% |

**At `4:5` the ceiling is 34.3%, however far the border is turned down.** What
leaves the space is the mismatch between a 2.33:1 picture and a 0.8:1 frame,
not the border. This spec makes the border reachable independently; it does
not and cannot make a panorama fill a portrait frame.

Filling more than that means either cropping — ruled out, frame 1 exists to
show the whole panorama — or cutting the panorama into stacked rows, which is
a different feature and is deliberately not in this spec.

## The model

`FrameStyle` gains one field:

```python
padded_border_percent: float | None = None
```

`None` means "whatever `border_percent` is", which is exactly today's
behaviour, so every stored style, every stored preset, every CLI invocation
and every golden hash is unaffected until someone sets it.

`padded_border_px(ratio)` resolves it, falling back to `border_px(ratio)`.
`make_padded_frame` is the only caller. `border_px` itself does not change,
so nothing about what the border means for a detail frame, a composite, or a
gutter moves.

The field is validated like the others: `0.0` to `MAX_PERCENT`, or `None`.

## The controls

**CLI.** `--frame1-border PERCENT`, validated by the existing percent
converter, defaulting to unset. Documented as "splits only", beside
`--border-detail-frames`, since a composite has no frame 1.

**GUI.** In the Split tab's BORDER section, below the existing width slider:
a checkbox, `Frame 1 border`, and a `PercentSlider` that is only enabled when
it is ticked. Unticked is `None` and the slider shows the shared width, so
ticking it starts from where you already were rather than jumping.

The checkbox is the `None`-or-a-number distinction made visible, and it
follows the `border_detail_frames` checkbox that already sits there.

Compose does not get it. `BorderControls` already takes `show_gutter` and
`show_detail_toggle`; this is a third flag of the same kind, and a Compose
rail must not offer a control for a frame it does not produce.

## Presets

A Split preset already carries what its own tab can show, so it gains this
field. An existing stored preset has no such key and reads back as `None`,
which is the behaviour it was saved with — so nothing anyone has saved
changes meaning.

## Testing

- **`geometry`**: `padded_border_px` equals `border_px` when the field is
  `None`; resolves independently when set; `make_padded_frame` insets by the
  frame-1 value while `make_section` with `border_detail_frames` on insets by
  the shared one; a style with the field set to the same number as
  `border_percent` produces a byte-identical frame to one with `None`.
- **The measured ceiling**: at `4:5` with the field at `0.0`, the fitted
  panorama is exactly the frame's full width, and its area is the 34.3% the
  table states. This is the claim the whole feature rests on and it should
  fail if the arithmetic moves.
- **`cli`**: `--frame1-border` reaches the style; omitted, the style's field
  is `None`; an out-of-range value fails at parse time.
- **The tab**: the slider is disabled until the checkbox is ticked; ticking it
  adopts the shared width rather than jumping; the style it produces has
  `None` while unticked; a saved preset round-trips the field; a preset stored
  before this feature reads back as `None`.
