# Composing up to six panels

**Date:** 2026-08-02
**Status:** Design, approved for planning
**Bead:** maskingframe-dk9 (first of two specs)

## Scope

This spec raises the compose ceiling from three panels to six. It does not
add a way to override the automatic arrangement; that is the second spec, and
it will build on the candidate list this one defines. Everything here is
useful and shippable without it.

## The problem

`layout.candidates` is hand-enumerated for two and three panels and raises for
anything else. Order-preserving arrangements grow as the little Schröder
numbers — 2, 6, 22, 90, 394 for two through six — so hand-enumeration stops
being an option well before six.

Two things turned out to be true when measured, and both shape the design.

**Fill score stops being a good proxy past three panels.** Maximising the
fraction of the frame covered picks arrangements no one would draw. For six
identical 3:2 frames at `1:1` the unrestricted winner is
`C(1,R(2,3,C(4,5,6)))`; for a mixed set at `4:5` it is
`C(R(C(R(1,C(2,3)),4),5),6)`. The obvious two-rows-of-three sits 37th.

**The count is not the bottleneck.** Solving all 394 arrangements takes about
7 ms. Restricting the set is an aesthetic decision, not a performance one, and
this spec makes it on those grounds.

## The model

### One level of grouping

An arrangement is a root — a Row or a Column — whose parts are consecutive
blocks of the images in input order. A block of one image is a leaf. A block of
two or more is a group of the *opposite* orientation containing only leaves.
There is no third level.

That alternation is what makes the set canonical: without it `R(R(1,2),3)` and
`R(1,2,3)` would both be generated for the same picture.

| Panels | All arrangements | One level |
|---|---|---|
| 2 | 2 | 2 |
| 3 | 6 | 6 |
| 4 | 22 | 14 |
| 5 | 90 | 30 |
| 6 | 394 | 62 |

**The two- and three-panel sets are unchanged.** Every arrangement the
hand-written list yields has one level of grouping, so at the current ceiling
nothing moves except what an arrangement is called.

The cost at six panels is up to 13 fill points against the unrestricted best.
That is accepted: the arrangements given up are the ones quoted above.

### Names

A name is generated from the tree, never written by hand: `R(` or `C(`, the
parts separated by commas, closing paren, with images numbered from one so the
name matches the numerals the sources list already draws.

```
R(1,2)                    C(1,2)
R(1,2,3)                  R(1,C(2,3))        C(R(1,2),3)
C(R(1,2,3),R(4,5,6))      R(C(1,2),C(3,4),C(5,6))
```

Names are unique per arrangement — verified by construction up to seven
panels — so a name identifies an arrangement exactly. That is what makes it
usable as the identifier the second spec will accept.

This renames every existing arrangement. `row-one-then-two` becomes
`R(1,C(2,3))`. The old slugs appear in the compose tests and in `CompositeResult`
output; both change.

### Choosing between them

The score stays the fraction of the available box the panels cover. `solve`
stops keeping a running best and instead ranks every solved candidate by:

1. score, descending
2. depth, ascending — a flat root before a grouped one
3. name, ascending

Two scores are equal when they are within `1e-9`. Exact float comparison would
let a rounding artefact one part in 10^16 defeat the depth preference, which is
the whole reason the preference exists.

Ties are common in the case that matters most: six frames from one camera share
an aspect ratio, so several arrangements fill the frame identically.

The depth term turned out to be a guard rather than an active rule. A sweep over
every aspect combination, ratio and panel count finds no tie whose members
differ in depth — two arrangements that group their panels differently assemble
to different shapes, so they do not fill the frame to within `1e-9` of each
other. In practice the name decides. Depth is kept because it costs nothing and
states the preference if such a tie ever does arise, and
`test_no_tie_has_ever_been_found_between_two_depths` fails the day one does, so
this paragraph is checked rather than remembered.

### Counts

`layout.MIN_PANELS = 2` and `layout.MAX_PANELS = 6`. They live in `layout`
because that is the module that enforces them, and `pipeline` re-exports both so
`cli` and `gui` never import `layout` directly — the same reason `pipeline`
re-exports the ratio and style names.

`candidates` raises `ValueError` outside that range, naming the count it was
given.

## Vocabulary

`COMPOSITE_SUFFIXES` gains three entries, carrying on the Greek that `_diptych`
and `_triptych` started:

| Panels | Suffix | Save button |
|---|---|---|
| 2 | `_diptych.jpg` | Save diptych |
| 3 | `_triptych.jpg` | Save triptych |
| 4 | `_tetraptych.jpg` | Save tetraptych |
| 5 | `_pentaptych.jpg` | Save pentaptych |
| 6 | `_hexaptych.jpg` | Save hexaptych |

A test asserts the table's keys are exactly `MIN_PANELS..MAX_PANELS`, so raising
the ceiling again cannot leave a count without a filename to write to.

`compose_tab._composite_noun` and `_save_label` read that one table instead of
special-casing two and three.

## The rail

The solver names an arrangement in notation; the rail renders it as English.
That split already exists in `present_layout` and is kept — the rail should read
the way the rest of the interface talks, and the notation should stay exact for
the CLI. The parser changes, the layering does not.

`present_layout(name, count)` first reads the name into a root letter and the
sizes of its parts. Then, in order:

1. **Two panels, no grouping.** `R(1,2)` is "Side by side"; `C(1,2)` is "One
   above the other". A pair is not "a row of two". Unchanged from today.
2. **No grouping.** Every part is one image: "Row of three", "Column of five".
3. **Even grouping.** Every part is the same size, larger than one. A row of
   columns is "Three columns of two"; a column of rows is "Two rows of three".
4. **Two uneven parts.** There are exactly two positions to name, so the
   existing positional phrasing applies and today's three-panel copy is
   preserved verbatim: `R(1,C(2,3))` is "One left, two stacked right";
   `C(R(1,2),3)` is "Two side by side on top, one below".
5. **Three or more uneven parts.** Positional words run out, so the parts are
   listed in order: `C(1,R(2,3),R(4,5,6))` is "Column of three: one, two side
   by side, three side by side".

A name that does not parse falls back to itself rather than to a slug, as it
does today.

Rules 4 and 5 read the pairing word off the axis, as `_AXIS` already does: a
group inside a row is stacked, a group inside a column is side by side.

## Everything else

- `cli.py` — the compose help reads "join two to six images into a single
  composite"; the `-o` help lists the suffixes; the count error names both how
  many were given and the accepted range. Still `nargs="+"` with the count
  checked afterwards, for the reason already recorded.
- `gui/compose_tab.py` — `MAX_IMAGES` comes from `pipeline`; `EMPTY_STATE`
  reads "Add two to six sources."
- `gui/sources.py` — `EMPTY_CAPTION` matches, and the list's own limit rises.

Nothing in `geometry`, `compose`, or the split side changes. `evaluate`,
`_place`, `_coefficients`, the no-crop guarantee and the never-permute guarantee
are all untouched.

## Testing

- **Enumeration**: the counts are 2, 6, 14, 30, 62; every name is unique; the
  two- and three-panel sets equal the arrangements the current code yields;
  every arrangement uses each image exactly once, in input order; a count
  outside the range raises with the count in the message.
- **Ranking**: a deliberate tie between a flat and a grouped arrangement is won
  by the flat one; a tie between two of the same depth is won by the name that
  sorts first; a candidate that beats another by more than the tolerance wins on
  score regardless of depth.
- **Suffixes**: the table covers exactly `MIN_PANELS..MAX_PANELS`; six sources
  write `_hexaptych.jpg`.
- **`present_layout`**: one case per rule above, with the three-panel strings
  asserted against their current values so the rewrite cannot quietly reword
  them; and the existing walk over the solver's whole candidate list, which now
  covers 62 arrangements and still fails on one that cannot be read.
- **End to end**: six sources of mixed orientation compose, at each ratio,
  without cropping — every box's aspect matches its source's.
