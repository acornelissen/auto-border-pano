# Named border presets

**Date:** 2026-08-02
**Status:** Design, approved for planning
**Bead:** maskingframe-ikq

## The problem

A border is four decisions — width, colour, gap width, gap colour — plus, on
Split, whether the detail frames carry it. Setting a look you have already
settled on means moving four controls every time, and the only thing the
application remembers is the last one you used.

## The model

### A preset is a named style, per tab

Split and Compose keep separate preset lists, matching how their styles are
already stored separately: a split border and a composite border are different
decisions, and one list would offer each tab fields it cannot use.

- A **Split** preset holds `border_percent`, `border_colour` and
  `border_detail_frames`.
- A **Compose** preset holds `border_percent`, `border_colour`,
  `gutter_percent` and `gutter_colour`.

Neither carries a field its own tab cannot show. A preset is stored and
returned as a `FrameStyle` — the fields the tab does not use keep their
defaults — so nothing downstream learns a new type.

### Names

A name is trimmed, non-empty, and at most 40 characters. Saving under a name
that already exists replaces it. Order is alphabetical, case-insensitive: the
list grows, and insertion order stops being findable once it does.

### Built-ins

Three per tab, seeded into the store the first time the application runs and
thereafter ordinary presets that can be edited or deleted like any other:

| Name | Split | Compose |
|---|---|---|
| Plain white | 9%, `#ffffff`, detail off | 9% / 4%, both `#ffffff` |
| Gallery | 18%, `#ffffff`, detail off | 18% / 4%, both `#ffffff` |
| Black surround | 9%, `#14171a`, detail off | 9% / 4%, both `#14171a` |

Seeding is recorded by a flag, so deleting a built-in makes it stay deleted.
The cost is that a preset added in a later release will not appear for an
existing install. That is accepted: the alternative is a tombstone list and two
kinds of preset the interface then has to distinguish, which is more machinery
than three suggestions are worth.

## The controls

At the top of the BORDER section, above the width slider — you pick the look,
then adjust it:

```text
BORDER
[ Warm white (edited)  v ]  [Update]  [x]
  Border width  [===|------]  12 %   [#fff]
```

The box is an editable combo. **Enter saves and the button saves**, because
either is a reasonable thing to expect and neither costs anything. The button
reads **Save** when the typed name is new and **Update** when it already
exists — that is what replaces a confirmation dialog, and it tells you which
you are about to do before you do it. The `x` deletes the preset the box names,
and is available only when the box names one that exists.

Selecting a preset applies it whole, exactly as though every control had been
moved by hand, and settles — so the preview re-renders once, the way a slider
release already does.

### After editing

Move any control and the box reads `Warm white (edited)` until you save or pick
another. The suffix is display only. It is stripped before a name is saved,
matched or deleted, so a preset can never be called "Warm white (edited)".

With no preset chosen the box is empty, and moving a control leaves it empty —
there is nothing to have edited.

## Storage

`gui/settings.py` stays the only module that constructs a `QSettings`.

A stored preset is untrusted input, like the stored style, but the failure rule
differs: **a malformed preset is dropped on its own** rather than the whole
list falling back. Half a remembered style is more confusing than none, which
is why `load_style` falls back whole — but losing four good presets over one
bad one would be worse than the bug. Every preset is validated by constructing
a `FrameStyle`, so a colour or a percentage can never reach a renderer
malformed.

Presets live under `{scope}/presets/{name}/…`, beside the existing
`{scope}/border_percent` keys, so one store still holds everything.

## Where it lives

- **`gui/settings.py`** — `load_presets(scope)`, `save_preset(scope, name, style)`,
  `delete_preset(scope, name)`, the built-in table, and the one-time seed.
- **`gui/shell.py`** — a `PresetRow` widget inside `BorderControls`: the
  editable combo, the Save/Update button, the delete button, the `(edited)`
  marker, and signals for chosen, saved and deleted. It is presentation plus
  naming rules only; it does not touch `QSettings`.
- **`gui/split_tab.py`** and **`gui/compose_tab.py`** — each owns its scope,
  loads its list at startup, and connects the row to `settings`.

Nothing in `geometry`, `layout`, `compose`, `pipeline` or `cli` changes. No new
`FrameStyle` field.

## Testing

- **`settings`**: round-tripping a preset; a malformed one dropped while its
  neighbours survive; alphabetical order; overwrite by name; delete; the seed
  running once and a deleted built-in staying deleted. Against a redirected
  store, never the developer's real preferences.
- **`shell`**: the `(edited)` marker appearing and clearing, and never reaching
  a saved name; the button's text following whether the name exists; the delete
  button's availability; Enter and the button doing the same thing.
- **The tabs**: choosing a preset applies the whole style and settles once;
  each tab sees only its own scope's list.
