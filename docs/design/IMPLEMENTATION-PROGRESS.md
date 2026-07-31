# Implementation progress — 2026-07-31 GUI design plan

Ralph loop state. One stage per iteration. Update this file at the end of
every iteration, before `mise run check` and the commit.

| Stage | What | State |
|---|---|---|
| 1 | Theme, palette, type (`gui/theme.py`, clam, 6/12/24 spacing) | done |
| 2 | Copy rewrite and modal removal | done |
| 3 | Two-column layout, radio pair, live readouts, file facts | done |
| 4 | Contact strip Canvas replacing `PreviewPanes` | done |
| 5 | Numbered negatives list replacing `tk.Listbox` | done |

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
