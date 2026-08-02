# Remembering the detail frames per source

**Date:** 2026-08-02
**Status:** Design, approved for planning
**Bead:** maskingframe-78d

## The problem

A position is chosen by looking at one photograph, and it is thrown away when
the file is closed. Reopening yesterday's panorama gives yesterday's evenly
spread opening guess, not yesterday's crops.

## The model

### A plan belongs to a file, not to a filename

A stored plan is keyed on the source's **path, modification time and size** —
the same three facts `cached_preview_source` already keys its decode on, so
there is one answer in this codebase to "is this the same file". A stat, no
read: deciding whether to restore a handful of floats must not cost hundreds
of megabytes of I/O on a 132MP scan.

An edit that preserves both mtime and size is missed. That takes a deliberate
`touch`, and the cost is crops a few pixels off rather than anything
corrupted.

When any of the three disagrees, the plan does not apply and the source opens
on its even spread, exactly as it does today.

### What is stored

Per plan: the path, the mtime, the size, and the positions. A few hundred
bytes.

The ratio is **not** part of the key. A position is a fraction of the
panorama's width, which means the same thing at every ratio, and the count
has been the user's decision since the add and remove controls landed. A plan
of eight frames reopened at `1.91:1` is eight frames, not `section_count`'s
guess.

### Bounded at fifty

The fifty most recently used plans are kept. Storing a fifty-first evicts the
least recently used. Reading a plan counts as using it.

Fifty is tens of kilobytes and far more than anyone revisits. The point of a
count rather than an age is that the ceiling is a number that can be stated
rather than one that depends on how much work you happen to do.

### Storage

`gui/settings.py` stays the only module that constructs a `QSettings`. Plans
live under their own group, beside the existing style and preset keys.

A stored plan is untrusted input. Each is validated on read — the positions
must be a non-empty ascending run of floats in `0.0..1.0`, the mtime and size
must be numbers — and a malformed one is **dropped on its own**, following
`load_presets` rather than `load_style`: losing forty-nine good plans over one
bad one would be worse than the bug that wrote it.

A path containing `/` is not a problem the way a preset name was: a plan is
stored under a key derived from the path, not the path itself, so the
separator never reaches `QSettings` as a group.

## Saying so

Restoring changes what every output frame contains, and there is no other way
to tell a restored plan from a fresh one — the positions are just numbers.

The line under the ribbon already says either what the keys do
(`split_tab.KEY_HELP`) or why there is nothing to place
(`split_tab.NO_POSITIONS`). It gains a third thing to say:

```text
Frames restored from last time.
Left and Right move the selected frame, Shift by ten steps, ...
```

It reverts to the plain key help as soon as anything moves — the sentence is
about how the plan arrived, and once you have changed it, it did not arrive
that way.

## When a plan is written

On every change to the positions that the user made: a drag settling, a key
nudge settling, add, remove, and Even. Not on the header read that restores
one, which would rewrite what it has just read.

The Split tab already funnels every change through `_set_positions` and
already distinguishes a settle from a move, so the write goes where the
re-render goes.

Folder mode stores nothing. There is no one panorama, the ribbon is hidden,
and the frames are cut on the even default — all of which is already true and
stays true.

## Where it lives

- **`gui/settings.py`** — `load_plan(path)`, `save_plan(path, positions)`, the
  fifty-plan bound, and the validation. It stats the file itself, so a caller
  cannot forget to.
- **`gui/split_tab.py`** — restores after the header read, stores on a settle,
  and owns the restored-this-time sentence.

Nothing in `geometry`, `layout`, `compose`, `pipeline` or `cli` changes. The
CLI has no position flags and gains none: a position is chosen by looking at a
photograph.

## Testing

Against a redirected store, never the developer's own preferences.

- **`settings`**: a plan round-trips; a plan whose file has a new mtime is not
  returned; the same for a new size; a malformed plan is dropped while its
  neighbours survive; the fifty-first stored evicts the least recently used;
  reading a plan makes it recently used; a missing file returns nothing rather
  than raising.
- **The tab**: reopening a source restores its positions and says so; the
  sentence reverts to the key help on the first change; a source edited since
  storing opens on the even spread; folder mode stores nothing; restoring does
  not immediately write back.
