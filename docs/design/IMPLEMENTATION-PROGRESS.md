# Implementation progress — 2026-07-31 GUI design plan

Ralph loop state. One stage per iteration. Update this file at the end of
every iteration, before `mise run check` and the commit.

| Stage | What | State |
|---|---|---|
| 1 | Theme, palette, type (`gui/theme.py`, clam, 6/12/24 spacing) | done |
| 2 | Copy rewrite and modal removal | done |
| 3 | Two-column layout, radio pair, live readouts, file facts | done |
| 4 | Contact strip Canvas replacing `PreviewPanes` | done |
| 5 | Numbered sources list replacing `tk.Listbox` | done |

All five stages are in.

## Stop-and-reassess after Stage 3

The plan asks for a decision here: continue to the Canvas work, or stop and
have the Qt conversation instead. The signal it named was whether stages 1-3
fought `clam` — particularly whether the Notebook or the Combobox refused to
restyle.

They did not. Both took the palette, and the only real fight was `clam`
expanding the selected notebook tab, which `style.map(expand=...)` settled.
The app now reads as designed and the remaining gap is exactly the one the
plan predicted: the preview is still four sunken boxes that are empty until
the first run. So Stage 4 is worth it, and the Qt question stays closed.

## Notes

- Stage 3 collapsed the two Browse buttons into one `Choose…` that follows
  the radio pair. The mock has one input field, and the two buttons were the
  source of the alignment fight the audit opens with.
- `present_layout` derives its copy from the solver's own candidate names
  rather than a lookup table, so a new arrangement cannot go unnamed. Only
  the two-panel row and column get bespoke phrasing, because a diptych has
  an everyday name for its arrangement and a triptych does not.
- The `tk_root` fixture in `conftest.py` joins worker threads and destroys
  children before collecting garbage. That is load-bearing, not tidiness:
  without it a `tk.Variable` finaliser runs after its interpreter is gone and
  surfaces as an unraisable-exception warning against an unrelated test.

## Polish pass

Done after looking at the running app rather than at the plan. What the
screenshots showed, and what changed:

- **The strip was a black slab.** Lightened to the sleeve grey with a 1px
  rebate aperture per frame. Black at that size read as a hole in the light
  table rather than as film lying on it. `SPROCKET` is now nowhere on the
  sleeve as text — it is borderline against `LIGHTBOX` and fails against the
  paler sleeve, so stencils use `INK_SECONDARY`.
- **Stencil captions overlapped.** They were not clipped to their own frame,
  so "FRAME 1 · WHOLE PANORAMA" ran straight through frame 2's caption.
- **The strip stretched and then shrank.** Painting the whole cell made a
  five-frame strip into a large pale panel with a thin row of pictures in
  the middle of it. Sizing to content exposed a second bug: the canvas asks
  for its own height, so feeding the height it is given back into the frame
  size is a loop that walks the strip down to the minimum over a few
  resizes. Only the width comes from the widget now.
- **The sleeve ran the full column width** past the last frame. It ends
  where the film ends.
- **Paths showed their head and clipped the filename** — the only part of a
  path anybody recognises. `shell.path_entry` rides at the tail, and leaves
  the view alone while the field has focus.
- **The two rails had drifted apart again** in DESTINATION. There is now a
  test that walks both widget trees and fails if their shapes differ.
- **The progress bar was a dead grey slab at rest.** It only takes space
  while a run is in flight; the strip is the real indicator.
- **The band repeated the window title** directly below it. It leads with
  the subject now and carries what the front tab will produce on the right.
- The tabs sat flush against the window edge; they start at the rail gutter.
- The Compose rail overflowed an 860pt window, clipping its status line, so
  the window has a minimum size.

Two things found while polishing that were not cosmetic:

- `split_tab`'s workers called `root.after` unguarded. Closing the window
  mid-run killed the worker thread with an unhandled exception. Every
  crossing goes through one guarded `_report` now, as Compose already did.
- `_apply_facts` re-read the ratio combobox when the worker reported back,
  so a ratio changed mid-inspection would caption one ratio's frame count
  with another ratio's name. The ratio travels with the answer.

`shell.BandSubject` is a Protocol naming what the shell needs from a tab.
`app.run` is the only code that reads those variables and it ends in
`mainloop`, so a tab dropping one was a crash at launch with a green suite —
which nearly shipped. There is now a test that builds what `run` builds.
