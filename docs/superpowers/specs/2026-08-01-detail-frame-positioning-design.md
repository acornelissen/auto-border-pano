# Choosing where the detail frames land

**Date:** 2026-08-01
**Status:** Design, approved for planning

## The problem

A panorama's detail frames are currently cut by tiling: the width is divided
into `count` equal slices and each slice becomes a frame. The photographer has
no say in it. If the interesting thing sits on a tile boundary, it is cut in
half, and the only remedy is to change the ratio and hope.

This design lets the user place each detail frame along the panorama by hand,
in the GUI, while leaving the CLI and every existing caller working as before.

## The model

### A frame is a position

A detail frame is described by one number: `position`, the left edge of its
crop as a fraction of the panorama's width, in `[0, 1]`. A plan is a tuple of
those, ascending.

Width is not stored. It is derived:

```
frame_width_px = floor(pano_height * ratio.value + 0.5)
```

Every detail frame is therefore a **full-height crop at exactly the output
aspect ratio**. A frame's crop box is `(x, 0, x + frame_width_px, pano_height)`
where `x = floor(position * pano_width + 0.5)`, clamped so the box stays
inside the image.

### Why the width rule changes

Today `section_bounds` uses `width // count`, so a frame's width depends on how
many frames were asked for. That cannot survive hand placement: moving one
frame must not resize the others, and adding a sixth must not re-cut the first
five.

Fixing the width to `pano_height * ratio` is also the better rule on its own
merits. `section_count` already floors at two, so a 2.4:1 panorama at 1.91:1
gets two frames of `width // 2` — each 1.2:1, far narrower than the 1.91:1
output — and `make_section` scales to cover and then **centre-crops the top and
bottom away**. Under the new rule that panorama's frames are full height and
nothing vertical is discarded. The tiles no longer meet edge to edge, but they
never needed to: the detail frames are a zoom, not a tiling. That is why the
count floors at two in the first place.

This is a deliberate output change and is recorded in CLAUDE.md's
behaviour-changes list.

### Ordering, clamping, and the narrow-source case

- Positions are kept **ascending**. Frames may overlap, but they may not cross:
  dragging frame 2 past frame 3 clamps at frame 3's position, not beyond it.
  Numbering a carousel that runs backwards along the picture is confusing, and
  overlap is a legitimate choice (two tight crops on the same subject).
- A position is clamped to `[0, 1 - frame_width_px / pano_width]` so no frame
  hangs off an edge.
- If `frame_width_px >= pano_width` — a source narrower than one output tile,
  e.g. a 1.5:1 image at 1.91:1 — the clamp range collapses to `[0, 0]`. Every
  position is 0, the crop is the whole width, and `make_section` scales to
  cover exactly as it does now. Degenerate but must not raise.

### Default positions

`section_count()` is unchanged and still gives the opening count: how many
exact tiles fit across the panorama, floored at two. The default positions are
that many frames spread evenly across the available travel:

```
positions[i] = i * travel / (count - 1)     # travel = 1 - frame_width / pano_width
```

so the first frame starts at the left edge and the last ends at the right edge,
with the rest evenly between. For `count == 1` (unreachable today, but the
formula must not divide by zero) the single position is 0.

This is not identical to the old tiling for counts where the derived width
differs from `width // count`, which is the behaviour change above.

### Adding and removing

Adding a frame puts it in the **widest uncovered stretch** of the panorama,
centred in that stretch; if the frames already cover everything, it goes in the
widest gap between adjacent left edges. Removing takes the **last** frame. Both
keep the tuple ascending.

The count is a derived default the user may override, bounded below by
`MIN_SECTIONS` (2).

## The interaction

### The ribbon

A new widget above the contact strip on the light table shows the whole
panorama once, at a **fixed height with the picture fitted inside** it
(letterboxed, not cropped). A fixed height is required: at the table's width a
2.3:1 panorama would want a ~275px-tall ribbon and a 13:1 one a ~49px sliver,
and the layout must not jump when a different file is loaded.

The area outside the frames is dimmed. Each frame is a numbered window drawn in
the theme's existing vocabulary — a hairline edge and a chinagraph numeral,
consistent with the strip's frame numbering. Dragging a window moves that
frame; the drag is clamped by the rules above.

### Dragging in the frame

Dragging horizontally inside a contact strip frame nudges the same position,
with the actual crop in front of the user. No new furniture, and it shows
exactly what will be written.

Both views write to the same tuple of positions, held by the tab, so they
cannot disagree. A change from either re-renders the preview through the
existing settle mechanism — cheap feedback during the drag, a re-render when
the hand stops — reusing `PercentSlider`'s `valueChanged`/`settled` split
rather than inventing a second one.

### Folder mode

Positions are a single-file idea: they are chosen by looking at one
photograph. In folder mode the ribbon is hidden and every panorama is split
with the default even spacing. A one-line explanation appears where the ribbon
was, so its absence reads as a decision rather than a missing feature.

### The CLI

Unchanged. No position flags. Even spacing, as today, with the new width rule.

## Where it lives

Dependency direction is unchanged: `geometry` is a leaf, `gui` imports only
`pipeline`.

- **`geometry.py`** — gains `frame_width(pano_height, ratio) -> int`,
  `clamp_position`, `default_positions(pano_width, pano_height, ratio, count)`
  and `insert_position`/`drop_position` for add and remove. `section_bounds`
  changes to take a position and the derived width instead of an index and a
  count. `make_section` takes a position rather than `(index, count)`.
  `section_count` is untouched.
- **`pipeline.py`** — `process_image` and `preview_frames` gain an optional
  `positions: Sequence[float] | None = None`, defaulting to
  `geometry.default_positions(...)`. It goes before `style` so `style` stays
  last, and both are keyword-friendly with defaults, so no existing positional
  call breaks. `inspect_source` additionally reports the default positions, so
  the GUI gets them from the same header read it already does.
- **`gui/ribbon.py`** — new. The ribbon widget: a scaled panorama, the dim
  mask, the numbered windows, and drag handling. It emits normalised positions
  and knows nothing about pipelines or files. `strip.py` is already large and
  does a different job, so the ribbon does not go in it.
- **`gui/strip.py`** — gains horizontal drag inside a frame, emitting a delta
  for one frame index.
- **`gui/split_tab.py`** — owns the positions tuple, wires both views to it,
  hides the ribbon in folder mode, and passes positions into `preview_frames`
  and the run.

## Testing

- **`geometry`**: width derivation at each ratio, clamping at both ends,
  ascending-order enforcement including the crossing case, the narrow-source
  collapse, default spacing (first at 0, last flush right), and the add/remove
  rules. Pure and fast.
- **`pipeline`**: explicit positions produce the expected crops; omitting them
  reproduces the defaults; positions are honoured identically by
  `process_image` and `preview_frames`.
- **`gui`**: offscreen widget tests for the ribbon's drag-to-position mapping,
  the clamp at the edges and against a neighbour, and that folder mode hides
  the ribbon.
- **Golden hashes**: regenerated once, deliberately, in a single commit whose
  message records the old and new values and points at the width rule above.
