# Placing the detail frames from the keyboard

**Date:** 2026-08-01
**Status:** Design, approved for planning
**Bead:** maskingframe-6h3

## The problem

The detail frames decide what every output frame in a carousel contains, and
they can only be placed with a pointer. `gui/ribbon.py` and `gui/strip.py` set
no focus policy, handle no key events and set no accessible names. This project
holds WCAG 2.2 AA as the floor, where keyboard navigation is not optional, so
a feature this central being pointer-only is a defect rather than a gap.

## The model

### The selection lives in the tab

`SplitTab` already owns the positions; it now also owns which detail frame is
selected — an index into the positions tuple, or `None` when there is nothing
to select. The ribbon and the strip are each told what is selected and can each
ask for it to change. Neither knows about the other, which is the rule they
already follow.

Frame 1 is never selectable. It is the whole panorama and has no position.

### The keys

Whichever of the two widgets has focus:

| Key | Effect |
|---|---|
| Left / Right | Move the selected frame by one step |
| Shift + Left / Right | Move it by ten steps |
| Home / End | Send it to the near or far end of its travel |
| Up / Down | Select the previous or next detail frame |

Up and Down are not decoration: without them frame 4 is unreachable, because a
widget takes focus as a whole rather than one window at a time. They stop at
the ends rather than wrapping — a selection that jumps from the last frame back
to the first loses your place on a picture you are reading left to right.

Nothing is selected until one of the two widgets takes focus, and taking focus
selects the first detail frame if nothing is selected yet. So the marking never
appears before the user has asked for it, and the keys always have something to
act on once they can be pressed.

**A step is 1% of the panorama's width**, and Shift makes it 10%. That is a
round number in the unit a position is actually stored in, so the help text can
state it exactly. Home and End are the same mechanism with a step count of 100,
which spans the whole width and lets the existing clamp do the rest.

### One rule for moving a frame

A key press goes through `geometry.move_position`, the same function both drags
already use. A frame stops at its neighbour rather than swapping with it, and
at the ends of its travel. A key press and a drag cannot disagree, because
there is only one rule.

### Who speaks which index

Each widget speaks its own numbering, and the tab converts — as it already does
for drags. The ribbon's windows are detail frames, so it speaks detail indices.
The strip's frames include frame 1, so it speaks strip indices, matching its
existing `frame_dragged`.

### The widgets stay dumb

A step size is policy, not presentation. The widgets emit a **count of steps**,
not a distance: `frame_nudged(index, steps)` where steps is ±1, ±10 or ±100.
The tab turns a step into 1% of the width. So `ribbon.py` and `strip.py` still
know nothing about panoramas, ratios or percentages.

## Saying what is selected

The selected window's numeral and edge go chinagraph; the rest stay ink. That
is what chinagraph is for — marking up the frame you have picked.

Colour alone would fail the AA floor, so the rail also reads
`Frame 3 · 42% along`, beneath the frame count. It is the visible non-colour
statement of the same fact, and it is the string the widgets hand to
`setAccessibleName`, so a screen reader announces the same thing.

Focus itself stays `INK`, as fields already do. A field turning chinagraph when
you tab into it would read as invalid; the same applies here.

## Tab order

Ribbon, then strip: source, then results, matching how they sit on the table.
Both take `Qt.StrongFocus` so they are reachable by Tab and by click.

## Where it lives

- **`gui/ribbon.py`** — `Qt.StrongFocus`, `keyPressEvent`, a `selected` index it
  is told, `frame_nudged(int, int)` and `selection_changed(int)`, chinagraph on
  the selected window's numeral and edge, and an accessible name.
- **`gui/strip.py`** — the same, in strip indices, and the selected frame's
  numeral drawn in chinagraph. Selection is drawn whether or not the strip is
  draggable, but the keys only do anything when it is.
- **`gui/split_tab.py`** — owns the selection, converts steps to a fraction,
  routes both widgets through `_move_position`, keeps the two views in step, and
  writes the rail readout.

Nothing in `geometry`, `pipeline`, `compose`, `layout` or `cli` changes.

## Testing

- Key handling per widget, offscreen: each key produces the expected signal, and
  produces nothing when there is no selection or no plan.
- In the tab: a Right arrow moves the selected frame 1% and Shift+Right 10%;
  Home and End reach the ends; Up and Down move the selection and wrap or stop
  at the ends; a key press clamps at a neighbour exactly as a drag does.
- The rail readout states the selected frame and its position, and clears when
  there is no selection.
- Both widgets are reachable by Tab and report an accessible name.
