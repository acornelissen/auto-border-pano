# Undoing frame placement

**Date:** 2026-08-03
**Status:** Design, approved for planning

## The problem

Placing the detail frames is the craft work in this application: each position
is chosen by looking at one photograph. There is no way back from a mistake.
`Even` discards every hand-placed position in one press, `−` drops a frame,
and a mis-drag moves the wrong one. The only recovery is to place them all
again, or to reload the file — which, since the plan is now remembered per
source, restores the mistake rather than what preceded it.

## The model

### A snapshot is the plan

Two facts: the positions tuple and the row count. Together they are how the
panorama is cut, which is exactly the work that has no other way back.

Not the selection. That is which frame you are looking at rather than work you
have done, and `_set_positions` already drops a selection the incoming plan
cannot support, so undo inherits the right behaviour without storing it.

Not the border, the gap or the colours. Those have presets, and they are
remembered between launches; a second recovery mechanism for them would make
one key sometimes move frames and sometimes change a colour, which is harder
to predict than one that always does the same kind of thing.

Not the ratio, the source or the destination. Those are not work.

### History

`gui/history.py` holds one class and no Qt: a list of snapshots with a cursor,
a label per entry, and `record`, `undo`, `redo`, `clear`, `undo_label`,
`redo_label`. Pure data, so it is tested in memory the way `geometry` is.

Recording after the cursor has moved back discards the redo tail, which is
what every undo stack does and what stops a redo restoring a plan that no
longer follows from what is on screen.

Bounded at `MAX_STEPS = 50`, dropping from the front. A snapshot is a handful
of floats, so fifty is nothing to hold and far more than anyone walks back.

### Where it hooks in

`SplitTab._remember()` is already called from exactly seven places, and they
are precisely the moments worth recording:

| Action | Label |
|---|---|
| a drag released | `move` |
| the arrow keys stopping | `move` |
| `add_frame` | `add frame` |
| `remove_frame` | `remove frame` |
| `reset_frames` | `Even` |
| the row count changing | `rows` |

`_remember()` means *write the plan to the store*. Recording history is a
second thing, so it becomes a second method: `_record(label)`. The seven sites
call both.

**Undo and redo call `_remember()` but never `_record()`.** That is what stops
them recording themselves, and it is the one invariant a test has to hold.

### Clearing

On every change of source, including to no source and to folder mode.

Undoing into a plan made for a different photograph would restore crops that
mean nothing. Carrying work between files is what the remembered plan already
does, and it does it correctly — keyed on the file's path, mtime and size.

### Persistence

Undo writes to the store like any other change, so quitting after an undo and
reopening gives back what was on screen. The alternative silently keeps the
version you undid, which would be the application disagreeing with its own
display.

## Reaching it

`QShortcut` built from `QKeySequence.StandardKey.Undo` and `.Redo` rather than
hardcoded keys, so macOS gets ⌘Z and ⇧⌘Z and every other platform gets its own
convention.

Scoped to the Split tab with `Qt.ShortcutContext.WidgetWithChildrenShortcut`.
These are the first shortcuts in the application, so where they are owned is a
decision rather than a default: ⌘Z on the Compose tab must do nothing, not
silently undo something on a tab you cannot see.

A line under the frame controls names what will come back:

```text
FORMAT
  Ratio      [Portrait (4:5)      v]
  9 frames    [−] [+] [Even]
  Undo Even                      ⌘Z
```

It reads `Undo <label>` when there is something to undo, `Redo <label>` when
there is not but there is something to redo, and is empty when there is
neither. The shortcut is printed because the application has no menu bar, so
there is nowhere else it could be advertised — an undo nobody knows about is
close to no undo.

The label is the risk, not the depth: a line that says `Undo Even` and then
restores something else is worse than no line. Each of the seven sites names
its own action, and the tests assert the label alongside the state.

## Where it lives

- **`gui/history.py`** — new. The stack, the cursor, the labels, the bound.
  No Qt and no I/O.
- **`gui/split_tab.py`** — owns one `History`, records at the seven sites,
  clears on a source change, applies a snapshot through `_set_positions` and
  the rows combo, writes the rail line, and holds the two shortcuts.

Nothing in `geometry`, `layout`, `compose`, `pipeline` or `cli` changes.
Compose gets nothing: its arrangement is already reversible by choosing
another, and its source list has explicit add and remove.

## Testing

- **`history`**, in memory: recording, undoing and redoing return the right
  snapshots and labels; recording after an undo discards the redo tail; the
  bound drops from the front and keeps the newest fifty; `clear` empties both
  directions; undoing an empty history returns nothing rather than raising.
- **The tab**: each of the seven actions is undoable and restores the exact
  prior plan, including the row count; the label matches the action for each;
  undo and redo do not themselves become undoable steps; a source change
  clears the history; undo writes to the store, so a tab rebuilt against the
  same store sees the undone plan; the rail line reads `Undo Even` after Even
  and empties when the history does.
- **The shortcuts**: ⌘Z reaches the Split tab, and does nothing when Compose
  is the current tab.
