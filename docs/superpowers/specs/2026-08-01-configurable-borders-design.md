# Configurable border width and colour

Date: 2026-08-01

## Problem

Three constants decide every border in the output and none of them can be
changed without editing source: `geometry.SIDE_PADDING` (100), `layout.GUTTER`
(40) and `geometry.BACKGROUND` ("white"). A user wants to set the border on the
padded panorama frame, and separately to set the outer border and the gutter of
a composite, each with its own colour.

## Decisions

- Widths are a percent of the frame's **short side**, not absolute pixels, so
  one setting looks right at 4:5 and at 1.91:1.
- Defaults are 9% border and 4% gutter, both white. At 4:5 and 1:1 that is 97px
  and 43px, close enough to today's 100px and 40px to be indistinguishable; at
  1.91:1 the border drops from 100px to 51px, which is the point of the change.
- Gutter colour fills only the exact strips between adjacent panels. The outer
  border and the centring slack take the outer colour.
- Detail frames get a border only when the user asks for one.
- The style is a parameter threaded through the call chain, never module state,
  so a batch run and a preview cannot disagree about it.

## The model

`FrameStyle`, a frozen dataclass in `geometry.py`:

| Field | Type | Default |
| --- | --- | --- |
| `border_percent` | `float` | `9.0` |
| `border_colour` | `str` | `"#ffffff"` |
| `gutter_percent` | `float` | `4.0` |
| `gutter_colour` | `str` | `"#ffffff"` |
| `border_detail_frames` | `bool` | `False` |

It lives in `geometry` because `geometry` already owns `AspectRatio` and is the
leaf that both `layout` and `compose` import, so no dependency edges change.
`pipeline` re-exports `FrameStyle` and `DEFAULT_STYLE` alongside `AspectRatio`,
`RATIOS` and `DEFAULT_RATIO`, for the same reason those re-exports exist today:
`cli` and `gui` must not import `geometry`.

Percentages resolve against the ratio, not the caller:

```python
style.border_px(ratio)  # round(percent / 100 * min(ratio.width, ratio.height))
style.gutter_px(ratio)
```

Colours are stored as a validated `#rrggbb` string with an `.rgb` property.
`__post_init__` rejects anything else, and rejects a percent outside 0 to 40, so
no invalid value can reach PIL. One parser (`parse_colour`) is shared by the
dataclass, the CLI and the settings loader.

`SIDE_PADDING`, `GUTTER` and `BACKGROUND` are removed; `DEFAULT_STYLE` replaces
all three.

## Rendering

**`geometry.make_padded_frame(image, ratio, style)`** insets by
`style.border_px(ratio)` on all four sides and fills the canvas with
`style.border_colour`. The existing asymmetry note still holds: the border is
exact only on whichever axis binds.

**`geometry.make_section(image, index, count, ratio, style)`** is unchanged when
`border_detail_frames` is false. When it is true, the cover-crop targets the
inset box `(width - 2b, height - 2b)` and the result is pasted at `(b, b)` onto
a canvas filled with `border_colour`.

**`layout`** gains `Layout.gutters: tuple[Box, ...]` — the exact rectangles
between adjacent siblings, produced in `_place` where the spacing is already
computed. A zero gutter produces no boxes. `layout` stays pure arithmetic and
knows nothing about colour. `solve` and `evaluate` take a `FrameStyle` and a
ratio instead of loose `padding` and `gutter` ints.

**`compose.render(images, solved, ratio, style)`** fills the canvas with
`border_colour`, paints the gutter boxes in `gutter_colour`, then pastes the
panels. Same order as today, no new geometry.

## Pipeline and CLI

`process_image`, `process_folder`, `compose_images` and `compose_preview` each
take `style: FrameStyle = DEFAULT_STYLE` and pass it down.

The CLI gains five flags: `--border`, `--border-colour`, `--gutter`,
`--gutter-colour`, `--border-detail-frames`. The `--color` spellings are
accepted as hidden aliases. Widths take a float percent; colours go through
`parse_colour`. Both are validated at parse time with a message naming what was
wrong, so nothing fails at render time. The gutter flags apply to compose only
and their help text says so.

## GUI

A `BorderControls` widget in `gui/shell.py`, since both tabs need it and
`shell.py` is the shared skeleton. It reuses the existing `section` and
`help_label` helpers and adds one new widget, `Swatch`: a flat, hard-edged,
keyboard-focusable button showing the current colour and opening `QColorDialog`
on activation. Its accessible name states the colour, so the control does not
depend on colour perception alone. No rounding, no shadow, no animation, per the
theme.

The split tab shows border width, border colour and the detail-frames checkbox.
The compose tab shows border width, border colour, gutter width and gutter
colour. Each emits one `style_changed` signal carrying a whole `FrameStyle`,
which the tab feeds to its preview through the existing `work.submit` path and
staleness token. The tabs keep their `subject` / `detail` / `band_changed`
surface — nothing new is exposed to the shell.

`gui/settings.py` holds `load_style(scope)` and `save_style(scope, style)` over
`QSettings`, with the organisation and application names set once in `app.py`.
It is the only module in `gui/` that touches `QSettings`, and it validates on
read: a hand-edited or stale settings file falls back to defaults rather than
failing the launch. The two tabs store their styles under separate scopes,
because a split border and a compose border are different decisions.

## Testing

Tests are written before the code they describe.

- `geometry`: percent resolves to the expected pixel count at each ratio;
  colour and percent validation accept valid and reject invalid input; a
  bordered detail frame lands at the right offset over the right fill.
- `layout`: gutter boxes match the spacing exactly and never overlap a panel; a
  zero gutter yields none; existing no-crop and tie-break guarantees still hold.
- `compose`: sampled pixels are the expected colour in the outer border, in a
  gutter and inside a panel.
- `pipeline`: a non-default style round-trips to disk; `compose_images` and
  `compose_preview` still agree under a non-default style.
- `cli`: each flag parses, and each bad value is rejected with a useful message.
- `gui/settings`: round-trip, and a corrupt stored value falls back to the
  default.

The pixel-exact `SIDE_PADDING` assertions in `tests/test_geometry.py` and
`tests/test_compose.py` are rewritten against the percent contract.

## Out of scope

Per-frame overrides, gradients or textures, borders on batch output that differ
per file, and any change to the output filename contract.
