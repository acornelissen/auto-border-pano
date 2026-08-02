# Forcing a compose arrangement

**Date:** 2026-08-02
**Status:** Design, approved for planning
**Bead:** maskingframe-95s (second of two specs from maskingframe-dk9)

## Scope

The first spec raised the compose ceiling to six panels and made the
candidate list generative. This one lets the automatic pick be rejected.
Nothing here changes what the solver considers or how it scores.

## The problem

`solve` computes every candidate and returns one. There is no way to say
"not that one" short of reordering the sources until the solver agrees, and
at six panels the automatic pick is likelier to be one you disagree with —
there are 62 to disagree with.

## The model

### A ranked list, with the winner at its head

`solve` throws away work it has already done. It gains a sibling:

```python
def rank(aspects, ratio, style=DEFAULT_STYLE) -> tuple[Layout, ...]
```

every solvable arrangement, best first, and `solve` becomes `rank(...)[0]`.

That consolidates the tie rule into one sort key,
`(-round(score, 9), depth, name)`. Rounding at nine decimals expresses the
same `1e-9` tolerance the current filter does: two scores closer than that
round equal and fall through to depth, then to name.

This is the one part of the change that touches shipped behaviour, so it is
held to a measured claim rather than an argument: the consolidated key
reproduces the current winner in all 9,060 combinations of six aspect ratios
across every panel count and every target ratio that were checked, with zero
mismatches. The existing tie tests are the acceptance criterion — if they
fail, the consolidation is wrong, not the tests.

An arrangement that cannot be placed is absent from the ranking, exactly as
it is absent from the winner today. `rank` returning empty is the same
condition `solve` already raises on.

### Two spellings, one arrangement

A one-level arrangement is exactly a root axis plus the sizes of its blocks,
so the parenthesised name has a shell-safe equivalent that says the same
thing:

| Name | Short | Reads as |
|---|---|---|
| `R(1,2,3,4)` | `R1.1.1.1` | Row of four |
| `R(C(1,2),C(3,4))` | `R2.2` | Two columns of two |
| `C(R(1,2,3),4)` | `C3.1` | Three side by side on top, one below |
| `R(C(1,2,3,4),C(5,6))` | `R4.2` | Four stacked left, two stacked right |

Both are unique per panel count — verified by construction for two through
six — so either identifies an arrangement exactly.

`layout` gains `short_name(node)` and `parse_name(text, count)`.
`parse_name` accepts either spelling, case-insensitively, and returns the
`Node` or `None`. It never raises; the caller decides what an unknown name
means.

`R4.2` exists because `R(C(1,2,3,4),C(5,6))` is a syntax error unquoted in
both zsh and bash, so the obvious copy-paste of what the tool just printed
fails with a shell error rather than a message from the tool. The cost is a
second name that could drift from the first; the mitigation is that both are
generated from the same tree and the round-trip is tested in both directions
at every count.

### What the pipeline exposes

`name_layout`, `compose_preview` and `compose_images` each take
`arrangement: str = ""`, empty meaning automatic. It goes **ahead of**
`style`, which stays last with its default, per the rule already recorded
for that parameter.

A name that does not parse, or that parses to an arrangement this many
sources cannot have, raises `ValueError` naming both accepted spellings and
the count that was given. An arrangement that parses but cannot be placed at
this ratio raises the same way `solve` does for no usable layout.

```python
def arrangements(paths, ratio, style=DEFAULT_STYLE) -> tuple[Arrangement, ...]
```

one entry per candidate, best first, each carrying `name`, `short_name` and
`fill` (the score, as a fraction). Deliberately no English: `present_layout`
lives in the GUI, and moving it down would put copy in a module that has
none.

## The Compose tab

A new ARRANGEMENT section above BORDER, holding one `Combo`.

```text
ARRANGEMENT
[ Automatic — two rows of three          v ]
    Automatic — two rows of three
    Two rows of three                  82%
    Three columns of two               82%
    One left, five stacked right       79%
    ...
    Row of six                          6%
```

The first entry is Automatic and names what the solver picked, so choosing
nothing still tells you what you are getting. The rest are every arrangement
best first, read by `present_layout` with its fill percent.

No two entries can read alike:
`test_present_layout_reads_the_solver_name_as_a_sentence` already asserts
that the English is unique within a panel count.

Choosing one re-renders through the same path a border settle uses. The
choice is held as a name string, not an index — an index would point at a
different arrangement the moment the ranking moved.

### When the choice is dropped

Only when the panel count changes. An arrangement names a shape for exactly
N panels, so adding or removing a source makes it meaningless.

Everything else keeps it: the ratio, the border, the gutter, reordering the
sources, and replacing a file. All of those leave the arrangement valid, and
dropping a deliberate choice for a reason the user did not ask about is what
makes a control feel unreliable.

It is not remembered between launches. A border is a house style, which is
why presets exist for it; an arrangement belongs to one particular set of
photographs.

## The CLI

`--arrangement`, accepting either spelling. The spelling is validated at
parse time by a `type=` converter, so a typo fails with argparse's own
message; the panel count cannot be checked there — argparse does not know it
— so that check happens in the run and names both the count given and the
arrangement asked for.

The success line prints both forms, so what you read is what you can type:

```text
Wrote out_hexaptych.jpg as R(C(1,2,3,4),C(5,6)) at Portrait (4:5)
  --arrangement R4.2
```

`--help` documents the short form and mentions that the long one needs
quoting.

## Testing

- **`layout`**: `rank` is ordered and its head equals `solve`; the existing
  tie tests pass unchanged; every arrangement round-trips through both
  spellings at every count; `short_name` is unique per count; `parse_name`
  returns `None` for an unknown name, a wrong count, and a well-formed name
  with an impossible block size, and accepts either case.
- **`pipeline`**: a forced arrangement is the one rendered, not the
  automatic one, at a count where the two differ; an unparseable name raises
  naming both spellings; `arrangements` lists every candidate exactly once,
  best first, with fills matching `rank`.
- **The tab**: the list opens on Automatic; choosing an entry re-renders and
  the composite uses it; adding or removing a source drops the choice, while
  a ratio change, a border change and a reorder each keep it; the list is
  rebuilt when the count changes.
- **The CLI**: both spellings compose the same file; a bad spelling fails at
  parse time; a good spelling with the wrong number of sources fails naming
  both numbers.
