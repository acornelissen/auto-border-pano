# Undoing Frame Placement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the Split tab an undo and redo for where the detail frames land, so `Even`, a mis-drag or a stray `−` is recoverable.

**Architecture:** A new Qt-free `gui/history.py` holds a list of `(label, snapshot)` states with a cursor, where a snapshot is `(positions, rows)`. `SplitTab` owns one `History`, records at the seven existing `_remember()` call sites, applies a restored snapshot back through `_set_positions` and the rows combo, states what will come back in a line under the frame controls, and reaches it through two `QShortcut`s scoped to the tab.

**Tech Stack:** Python 3.13, PySide6, pytest + pytest-qt. Run everything through `mise` — there is no `uv` on PATH.

## Global Constraints

- **Dependency direction:** `gui/` imports only `pipeline` from the package, never `geometry`, `layout` or `compose` directly. `gui/history.py` imports neither Qt nor `pipeline` — it is pure data.
- **Undo and redo call `_remember()` but never `_record()`.** This is the one invariant a test must hold; without it undo records itself and the stack loops.
- **A snapshot is `(positions, rows)` only.** Not the selection, not the border, not the ratio, source or destination.
- **History clears on every change of source**, including to no source and to folder mode. It does *not* clear on a ratio change — a position is a fraction of the panorama's width and means the same thing at every ratio.
- **Undo writes to the store** via `_remember()`, so quitting after an undo and reopening gives back what was on screen.
- **`MAX_STEPS = 50`**, dropping from the front.
- **Every test that touches `QSettings` must use the `isolated_settings` fixture.** `tests/test_split_tab.py` already applies it module-wide via `pytestmark`; a new test module that touches settings must do the same.
- **No emoji, and no AI-attribution trailers, in commit messages.** Conventional commits, imperative mood.
- **Work straight on `master`.** No feature branch, no PR.
- **Verification command:** `mise run check` (ruff lint, ruff format check, mypy --strict, pytest). A single test file is `mise run test -- tests/test_x.py -q`.
- Every public function and class carries a docstring saying *why*, in the voice of the surrounding code: plain English, short sentences, active voice, no marketing words.

---

## File Structure

- **Create `src/maskingframe/gui/history.py`** — `Snapshot`, `History`, `MAX_STEPS`. The stack, the cursor, the labels, the bound. No Qt, no I/O, no `pipeline`.
- **Create `tests/test_gui_history.py`** — the in-memory tests for the above.
- **Modify `src/maskingframe/gui/split_tab.py`** — owns one `History`; records at the seven sites; clears on a source change; applies a snapshot; writes the rail line; holds the two shortcuts.
- **Modify `tests/test_split_tab.py`** — the tab-level tests.
- **Modify `CLAUDE.md`** — a section describing the behaviour, as every other feature here has.

Nothing in `geometry`, `layout`, `compose`, `pipeline` or `cli` changes.

---

### Task 1: The history stack

**Files:**
- Create: `src/maskingframe/gui/history.py`
- Test: `tests/test_gui_history.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `MAX_STEPS: int` (50)
  - `Snapshot` — frozen dataclass with `positions: tuple[float, ...]` and `rows: int`
  - `History` — `start(snapshot: Snapshot) -> None`, `record(label: str, snapshot: Snapshot) -> None`, `undo() -> Snapshot | None`, `redo() -> Snapshot | None`, `clear() -> None`, and read-only properties `can_undo: bool`, `can_redo: bool`, `undo_label: str`, `redo_label: str`.

Semantics the tests below pin down, stated once here so the implementation is not guessed at:

- The history holds *states*, not edits. `start` sets the baseline state — the plan as it arrived — and does nothing at all if there is already a state, so re-reading the same source's header does not wipe the stack.
- `record(label, snapshot)` discards anything ahead of the cursor, appends the new state with its label, and moves the cursor to it. `undo_label` is the label of the state you are leaving.
- `record` of a snapshot equal to the current state is ignored. A settle can fire without anything having moved — an arrow key held against the clamp, a drag that went nowhere — and recording those would give undo presses that visibly do nothing.
- The bound is 50 undoable steps, which is 51 states. Overflow drops from the front and moves the cursor with it.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_gui_history.py`:

```python
"""Tests for the undo stack behind the Split tab's frame placement.

No Qt here on purpose: the history is plain data, so it is tested in memory
the way `geometry` is.
"""

from maskingframe.gui.history import MAX_STEPS, History, Snapshot


def plan(*positions: float, rows: int = 1) -> Snapshot:
    return Snapshot(tuple(positions), rows)


def test_a_fresh_history_offers_nothing_in_either_direction() -> None:
    history = History()

    assert not history.can_undo
    assert not history.can_redo
    assert history.undo_label == ""
    assert history.redo_label == ""


def test_undoing_an_empty_history_returns_nothing_rather_than_raising() -> None:
    history = History()

    assert history.undo() is None
    assert history.redo() is None


def test_undo_returns_the_state_before_the_recorded_one() -> None:
    history = History()
    history.start(plan(0.0, 0.5))
    history.record("Even", plan(0.1, 0.6))

    assert history.undo() == plan(0.0, 0.5)


def test_the_label_names_the_action_being_undone() -> None:
    history = History()
    history.start(plan(0.0, 0.5))
    history.record("Even", plan(0.1, 0.6))

    assert history.undo_label == "Even"


def test_redo_puts_back_what_undo_took_away() -> None:
    history = History()
    history.start(plan(0.0, 0.5))
    history.record("move", plan(0.2, 0.5))
    history.undo()

    assert history.redo_label == "move"
    assert history.redo() == plan(0.2, 0.5)
    assert not history.can_redo


def test_the_row_count_travels_with_the_positions() -> None:
    """A snapshot is the plan, and the plan is both facts."""
    history = History()
    history.start(plan(0.0, 0.5, rows=1))
    history.record("rows", plan(0.0, 0.5, rows=3))

    assert history.undo() == plan(0.0, 0.5, rows=1)


def test_recording_after_an_undo_discards_the_redo_tail() -> None:
    """Otherwise a redo would restore a plan that no longer follows from
    what is on screen."""
    history = History()
    history.start(plan(0.0))
    history.record("move", plan(0.1))
    history.undo()

    history.record("add frame", plan(0.0, 0.5))

    assert not history.can_redo
    assert history.undo() == plan(0.0)


def test_recording_the_state_already_on_screen_is_ignored() -> None:
    """A settle can fire without anything having moved -- an arrow key held
    against the clamp. Recording it would give an undo press that does
    nothing visible."""
    history = History()
    history.start(plan(0.4))
    history.record("move", plan(0.4))

    assert not history.can_undo


def test_the_bound_keeps_the_newest_steps_and_drops_from_the_front() -> None:
    history = History()
    history.start(plan(0.0))
    for step in range(MAX_STEPS + 10):
        history.record("move", plan(float(step + 1) / 1000))

    undone = 0
    while history.can_undo:
        history.undo()
        undone += 1

    assert undone == MAX_STEPS


def test_clear_empties_both_directions() -> None:
    history = History()
    history.start(plan(0.0))
    history.record("move", plan(0.1))
    history.undo()

    history.clear()

    assert not history.can_undo
    assert not history.can_redo


def test_start_leaves_an_existing_history_alone() -> None:
    """Re-reading the same source's header must not wipe work."""
    history = History()
    history.start(plan(0.0))
    history.record("move", plan(0.1))

    history.start(plan(0.9))

    assert history.can_undo
    assert history.undo() == plan(0.0)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `mise run test -- tests/test_gui_history.py -q`

Expected: collection error — `ModuleNotFoundError: No module named 'maskingframe.gui.history'`.

- [ ] **Step 3: Write the implementation**

Create `src/maskingframe/gui/history.py`:

```python
"""Undo for where the detail frames land.

Placing the frames is the craft work in this application: each position is
chosen by looking at one photograph, and `Even` discards every one of them
in a single press. This is the way back.

No Qt and no I/O, so it is tested in memory the way `geometry` is. It holds
*states* rather than edits -- the whole plan is a handful of floats, so
storing the picture is cheaper than storing the difference and cannot drift
from it.
"""

from __future__ import annotations

from dataclasses import dataclass

MAX_STEPS = 50
"""How far back you can walk.

A snapshot is a handful of floats, so this is nothing to hold and far more
than anyone walks back. The bound exists so a long session cannot grow the
list without limit, not because the memory matters."""


@dataclass(frozen=True)
class Snapshot:
    """A plan: where the detail frames are, and how frame 1 is laid out.

    Deliberately not the selection, which is which frame you are looking at
    rather than work you have done, and not the border or the ratio, which
    have their own ways back.
    """

    positions: tuple[float, ...]
    rows: int


class History:
    """A list of plans with a cursor on the one currently on screen."""

    def __init__(self) -> None:
        self._states: list[Snapshot] = []
        # `_labels[i]` names the action that produced `_states[i]`. The
        # baseline has no action behind it, so its label is empty.
        self._labels: list[str] = []
        self._cursor = 0

    def start(self, snapshot: Snapshot) -> None:
        """Set the baseline: the plan as it arrived, before any change.

        Does nothing when there is already a history. A source's header is
        re-read whenever the ratio changes, and wiping the stack on that
        would throw away work in response to a setting that does not touch
        the plan.
        """
        if self._states:
            return
        self._states = [snapshot]
        self._labels = [""]
        self._cursor = 0

    def record(self, label: str, snapshot: Snapshot) -> None:
        """Note that `label` has just produced `snapshot`.

        Anything ahead of the cursor goes: a redo after a fresh change would
        restore a plan that no longer follows from what is on screen.
        """
        if not self._states:
            self.start(snapshot)
            return
        # A settle can fire without anything having moved -- an arrow key
        # held against the clamp, a drag that went nowhere. Recording those
        # would give undo presses that visibly do nothing.
        if self._states[self._cursor] == snapshot:
            return
        del self._states[self._cursor + 1 :]
        del self._labels[self._cursor + 1 :]
        self._states.append(snapshot)
        self._labels.append(label)
        self._cursor = len(self._states) - 1
        # One more state than steps: the baseline is a state nobody stepped
        # into.
        overflow = len(self._states) - (MAX_STEPS + 1)
        if overflow > 0:
            del self._states[:overflow]
            del self._labels[:overflow]
            # The oldest surviving state is now the baseline, whatever
            # produced it.
            self._labels[0] = ""
            self._cursor -= overflow

    def clear(self) -> None:
        """Forget everything. Said of a new source, whose plan this is not."""
        self._states = []
        self._labels = []
        self._cursor = 0

    @property
    def can_undo(self) -> bool:
        return self._cursor > 0

    @property
    def can_redo(self) -> bool:
        return self._cursor + 1 < len(self._states)

    @property
    def undo_label(self) -> str:
        """What undo would take back, named. Empty when there is nothing."""
        return self._labels[self._cursor] if self.can_undo else ""

    @property
    def redo_label(self) -> str:
        """What redo would put back, named. Empty when there is nothing."""
        return self._labels[self._cursor + 1] if self.can_redo else ""

    def undo(self) -> Snapshot | None:
        """Step back one plan, or `None` when there is nowhere to go."""
        if not self.can_undo:
            return None
        self._cursor -= 1
        return self._states[self._cursor]

    def redo(self) -> Snapshot | None:
        """Step forward one plan, or `None` when there is nowhere to go."""
        if not self.can_redo:
            return None
        self._cursor += 1
        return self._states[self._cursor]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `mise run test -- tests/test_gui_history.py -q`

Expected: 11 passed.

- [ ] **Step 5: Run the whole gate**

Run: `mise run check`

Expected: ruff, mypy --strict and the full suite all pass.

- [ ] **Step 6: Commit**

```bash
git add src/maskingframe/gui/history.py tests/test_gui_history.py
git commit -m "feat(gui): add the undo stack behind frame placement"
```

---

### Task 2: The tab records, undoes and redoes

**Files:**
- Modify: `src/maskingframe/gui/split_tab.py` (imports; `SplitTab.__init__`; `_on_rows_change`; `_on_nudge_settled`; `_on_frame_settled`; `_on_frame_drag_settled`; `add_frame`; `reset_frames`; `remove_frame`; `_on_selection_changed`; `_apply_facts`)
- Test: `tests/test_split_tab.py`

**Interfaces:**
- Consumes: `maskingframe.gui.history` — `History`, `Snapshot` (see Task 1 for the full signatures).
- Produces, on `SplitTab`:
  - `undo() -> None` and `redo() -> None` — public, so a shortcut and a test can both reach them.
  - `_record(label: str) -> None`, `_snapshot() -> history.Snapshot`, `_apply_snapshot(snapshot: history.Snapshot) -> None`, `_state_undo() -> None`, and the attribute `self._history: history.History`.
  - `_state_undo()` is a no-op stub in this task and gains its body in Task 3. It is called from here so Task 3 changes one method rather than eleven call sites.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_split_tab.py`. `_panorama`, the `tab` fixture and the module-wide `isolated_settings` mark already exist in that file — use them, do not redefine them.

```python
def _loaded(qtbot: Any, tab: SplitTab, tmp_path: Path, name: str = "pano.jpg") -> Path:
    """Load one panorama and wait for its plan to arrive."""
    source = _panorama(tmp_path, name)
    tab.source_row.setText(str(source))
    qtbot.waitUntil(lambda: bool(tab.positions()))
    return source


def test_even_is_undoable_and_puts_the_hand_placed_frames_back(
    qtbot: Any, tab: SplitTab, tmp_path: Path
) -> None:
    """The press this whole feature exists for."""
    _loaded(qtbot, tab, tmp_path)
    tab._move_position(0, 0.42)
    tab._on_frame_settled(0)
    placed = tab.positions()

    tab.reset_frames()
    assert tab.positions() != placed

    tab.undo()
    assert tab.positions() == placed


def test_each_action_names_itself(qtbot: Any, tab: SplitTab, tmp_path: Path) -> None:
    """A line that says `Undo Even` and then restores something else is
    worse than no line, so the label is asserted beside the state."""
    _loaded(qtbot, tab, tmp_path)

    tab._move_position(0, 0.42)
    tab._on_frame_settled(0)
    assert tab._history.undo_label == "move"

    tab.add_frame()
    assert tab._history.undo_label == "add frame"

    tab.remove_frame()
    assert tab._history.undo_label == "remove frame"

    tab.reset_frames()
    assert tab._history.undo_label == "Even"

    tab.rows_combo.setCurrentIndex(2)
    assert tab._history.undo_label == "rows"


def test_undoing_a_row_change_moves_the_combo_back(
    qtbot: Any, tab: SplitTab, tmp_path: Path
) -> None:
    """The rows are part of the plan, so undo has to move the control that
    states them or the rail would describe a layout nobody has."""
    _loaded(qtbot, tab, tmp_path)
    tab.rows_combo.setCurrentIndex(2)
    assert tab.rows() == 3

    tab.undo()

    assert tab.rows() == 1
    assert tab.rows_combo.currentIndex() == 0


def test_add_and_remove_are_undoable(qtbot: Any, tab: SplitTab, tmp_path: Path) -> None:
    _loaded(qtbot, tab, tmp_path)
    before = tab.positions()

    tab.add_frame()
    tab.undo()
    assert tab.positions() == before

    tab.remove_frame()
    tab.undo()
    assert tab.positions() == before


def test_undo_and_redo_do_not_themselves_become_undoable_steps(
    qtbot: Any, tab: SplitTab, tmp_path: Path
) -> None:
    """The one invariant. Without it undo records itself and walking back
    twice lands where it started."""
    _loaded(qtbot, tab, tmp_path)
    first = tab.positions()
    tab.reset_frames()
    tab._move_position(0, 0.31)
    tab._on_frame_settled(0)

    tab.undo()
    tab.undo()

    assert tab.positions() == first
    assert not tab._history.can_undo


def test_redo_puts_back_what_undo_took_away(
    qtbot: Any, tab: SplitTab, tmp_path: Path
) -> None:
    _loaded(qtbot, tab, tmp_path)
    tab._move_position(0, 0.42)
    tab._on_frame_settled(0)
    placed = tab.positions()

    tab.undo()
    tab.redo()

    assert tab.positions() == placed


def test_a_new_source_clears_the_history(qtbot: Any, tab: SplitTab, tmp_path: Path) -> None:
    """Undoing into a plan made for a different photograph would restore
    crops that mean nothing."""
    _loaded(qtbot, tab, tmp_path, "first.jpg")
    tab.reset_frames()
    assert tab._history.can_undo

    _loaded(qtbot, tab, tmp_path, "second.jpg")

    assert not tab._history.can_undo


def test_folder_mode_clears_the_history(qtbot: Any, tab: SplitTab, tmp_path: Path) -> None:
    _loaded(qtbot, tab, tmp_path)
    tab.reset_frames()
    assert tab._history.can_undo

    tab.folder_radio.setChecked(True)

    assert not tab._history.can_undo


def test_a_ratio_change_keeps_the_history(qtbot: Any, tab: SplitTab, tmp_path: Path) -> None:
    """A position is a fraction of the panorama's width, which means the
    same thing at every ratio -- so the plan survives, and so does the way
    back to it."""
    _loaded(qtbot, tab, tmp_path)
    tab.reset_frames()

    tab.ratio_box.setCurrentText(pipeline.RATIOS["1:1"].display)

    # Asserted straight away, not after a wait: the clearing decision is
    # made synchronously in `_on_selection_changed`, so if a ratio change
    # were going to wipe the history it would already have done it.
    assert tab._history.can_undo


def test_undo_writes_the_restored_plan_to_the_store(
    qtbot: Any, tab: SplitTab, tmp_path: Path
) -> None:
    """Otherwise the application would quietly keep the version you undid,
    and disagree with its own display on the next launch."""
    source = _loaded(qtbot, tab, tmp_path)
    tab._move_position(0, 0.42)
    tab._on_frame_settled(0)
    placed = tab.positions()
    tab.reset_frames()

    tab.undo()

    stored = settings.load_plan(source)
    assert stored is not None
    assert stored.positions == placed


def test_undoing_with_nothing_to_undo_does_nothing(tab: SplitTab) -> None:
    """No source, no plan, no crash."""
    tab.undo()
    tab.redo()

    assert tab.positions() == ()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `mise run test -- tests/test_split_tab.py -q -k "undo or redo or names_itself or clears_the_history"`

Expected: FAIL with `AttributeError: 'SplitTab' object has no attribute 'undo'`.

- [ ] **Step 3: Add the import and the attributes**

In `src/maskingframe/gui/split_tab.py`, extend the existing package import line:

```python
from maskingframe.gui import history, settings, shell, theme
```

In `SplitTab.__init__`, immediately after the `self._filling_rows = False` line, add:

```python
        # The way back from `Even`, a mis-drag and a stray `−`. Cleared
        # whenever the source changes: undoing into a plan made for a
        # different photograph would restore crops that mean nothing.
        self._history = history.History()
        # Which source the history belongs to, "" for none and for folder
        # mode. Compared rather than reacted to, because the header is also
        # re-read on a ratio change and the plan survives that.
        self._history_source = ""
```

- [ ] **Step 4: Add the four new methods**

In `src/maskingframe/gui/split_tab.py`, immediately after `_remember`, add:

```python
    def _snapshot(self) -> history.Snapshot:
        """The plan as it now stands: where the frames are, and the rows."""
        return history.Snapshot(self._positions, self._rows)

    def _record(self, label: str) -> None:
        """Note a change worth walking back from.

        Separate from `_remember`, which writes to the store, because the
        two answer different questions -- and because undo and redo call
        `_remember` and must never call this. That is what stops them
        recording themselves.
        """
        self._history.record(label, self._snapshot())
        self._state_undo()

    def _state_undo(self) -> None:
        """Say what would come back. Given its body in the next task."""

    def _apply_snapshot(self, snapshot: history.Snapshot) -> None:
        """Put a plan back on screen, and into the store.

        Rows first, because `_fill_rows_combo` reads `self._rows` and moves
        the combobox to match -- under `_filling_rows`, so the move is not
        mistaken for a choice and cannot record a step of its own.
        """
        if snapshot.rows != self._rows:
            self._rows = snapshot.rows
            self._fill_rows_combo()
            self._state_frame1()
            self._refresh_border_preview()
        self._set_positions(snapshot.positions)
        # Written to the store like any other change: quitting after an
        # undo and reopening must give back what was on screen.
        self._remember()
        self._state_undo()
        self._rerender()

    def undo(self) -> None:
        """Step back one plan. Does nothing when there is nowhere to go."""
        snapshot = self._history.undo()
        if snapshot is not None:
            self._apply_snapshot(snapshot)

    def redo(self) -> None:
        """Step forward one plan. Does nothing when there is nowhere to go."""
        snapshot = self._history.redo()
        if snapshot is not None:
            self._apply_snapshot(snapshot)
```

- [ ] **Step 5: Record at the seven sites**

Each of these already calls `self._remember()`. Add the `self._record(...)` line directly after it, so the pair reads as one thought.

In `_on_rows_change`:

```python
        self._remember()
        self._record("rows")
```

In `_on_nudge_settled`:

```python
        self._remember()
        self._record("move")
```

In `_on_frame_settled`:

```python
        self._remember()
        self._record("move")
```

In `_on_frame_drag_settled`:

```python
        self._remember()
        self._record("move")
```

In `add_frame`:

```python
        self._remember()
        self._record("add frame")
```

In `reset_frames`:

```python
        self._remember()
        self._record("Even")
```

In `remove_frame`:

```python
        self._remember()
        self._record("remove frame")
```

- [ ] **Step 6: Clear on a source change**

In `_on_selection_changed`, directly after the existing `source = self.source_row.text()` line, add:

```python
        # A change of source, including to none and to folder mode. Compared
        # rather than reacted to: this method also runs on a ratio change,
        # and a position is a fraction of the panorama's width, which means
        # the same thing at every ratio -- so the plan survives it, and the
        # way back to the plan should too.
        belongs_to = "" if self.folder_radio.isChecked() else source
        if belongs_to != self._history_source:
            self._history_source = belongs_to
            self._history.clear()
            self._state_undo()
```

- [ ] **Step 7: Set the baseline when the plan arrives**

In `_apply_facts`, directly after the existing line `self._restored = remembered is not None`, add:

```python
        # The plan as it arrived is what undo walks back to. `start` does
        # nothing when there is already a history, so a ratio change -- which
        # comes back through here -- does not wipe the way back.
        self._history.start(self._snapshot())
        self._state_undo()
```

- [ ] **Step 8: Run the tests to verify they pass**

Run: `mise run test -- tests/test_split_tab.py -q`

Expected: every test in the file passes, including the ones that were already there.

- [ ] **Step 9: Run the whole gate**

Run: `mise run check`

Expected: all green.

- [ ] **Step 10: Commit**

```bash
git add src/maskingframe/gui/split_tab.py tests/test_split_tab.py
git commit -m "feat(gui): undo and redo where the detail frames land"
```

---

### Task 3: The line that says what will come back

**Files:**
- Modify: `src/maskingframe/gui/split_tab.py` (module constants; `_build`; `_state_undo`)
- Test: `tests/test_split_tab.py`

**Interfaces:**
- Consumes: from Task 2 — `SplitTab._history` (a `history.History` with `can_undo`, `can_redo`, `undo_label`, `redo_label`), `SplitTab._state_undo()` (currently an empty stub), `SplitTab.undo()`, `SplitTab.redo()`.
- Produces: `SplitTab.undo_line` — a `QLabel` built by `shell.help_label`. Named `undo_line`, not `undo_label`, because `History.undo_label` is a string and having both spellings mean different things one attribute apart is a trap.

The line sits directly under the count controls, which is where the actions it names are. It reads `Undo <label>   <keys>` when there is something to undo, `Redo <label>   <keys>` when there is not but there is something to redo, and is empty when there is neither. The key names are asked of Qt rather than hardcoded, so macOS gets `⌘Z` and every other platform its own convention.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_split_tab.py`:

```python
def test_the_undo_line_is_empty_until_something_has_happened(tab: SplitTab) -> None:
    assert tab.undo_line.text() == ""


def test_the_undo_line_names_the_last_action(
    qtbot: Any, tab: SplitTab, tmp_path: Path
) -> None:
    """The shortcut is printed because the application has no menu bar, so
    there is nowhere else it could be advertised."""
    _loaded(qtbot, tab, tmp_path)
    tab.reset_frames()

    assert tab.undo_line.text().startswith("Undo Even")
    assert split_tab.UNDO_KEYS in tab.undo_line.text()


def test_the_undo_line_offers_the_redo_once_there_is_nothing_left_to_undo(
    qtbot: Any, tab: SplitTab, tmp_path: Path
) -> None:
    _loaded(qtbot, tab, tmp_path)
    tab.reset_frames()
    tab.undo()

    assert tab.undo_line.text().startswith("Redo Even")
    assert split_tab.REDO_KEYS in tab.undo_line.text()


def test_the_undo_line_empties_when_the_history_does(
    qtbot: Any, tab: SplitTab, tmp_path: Path
) -> None:
    _loaded(qtbot, tab, tmp_path, "first.jpg")
    tab.reset_frames()
    assert tab.undo_line.text() != ""

    _loaded(qtbot, tab, tmp_path, "second.jpg")

    assert tab.undo_line.text() == ""
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `mise run test -- tests/test_split_tab.py -q -k undo_line`

Expected: FAIL with `AttributeError: 'SplitTab' object has no attribute 'undo_line'`.

- [ ] **Step 3: Add the key-name constants**

In `src/maskingframe/gui/split_tab.py`, add to the imports:

```python
from PySide6.QtGui import QKeySequence
```

(If a `from PySide6.QtGui import ...` line already exists, extend it rather than adding a second.)

Then add, next to the other module constants such as `KEY_STEP`:

```python
def _key_name(key: QKeySequence.StandardKey) -> str:
    """What this platform calls a standard shortcut.

    Asked of Qt rather than written down, so macOS reads `⌘Z` and every
    other platform reads its own convention without this file knowing which
    platform it is on.
    """
    return QKeySequence(key).toString(QKeySequence.SequenceFormat.NativeText)


UNDO_KEYS = _key_name(QKeySequence.StandardKey.Undo)
REDO_KEYS = _key_name(QKeySequence.StandardKey.Redo)
```

- [ ] **Step 4: Build the line**

In `_build`, directly after the existing `rail.addWidget(counter)` line, add:

```python
        rail.addSpacing(theme.S)
        # Under the controls whose presses it takes back, and carrying the
        # shortcut: the application has no menu bar, so this is the only
        # place an undo could be advertised, and one nobody knows about is
        # close to no undo at all.
        self.undo_line = shell.help_label()
        rail.addWidget(self.undo_line)
```

- [ ] **Step 5: Give `_state_undo` its body**

Replace the stub added in Task 2 with:

```python
    def _state_undo(self) -> None:
        """Say what would come back, and which keys would bring it.

        Redo is offered only once undo has nothing left, rather than beside
        it: two directions on one line reads as a choice to make, and the
        one people want is almost always the way back.
        """
        if self._history.can_undo:
            self.undo_line.setText(f"Undo {self._history.undo_label}   {UNDO_KEYS}")
        elif self._history.can_redo:
            self.undo_line.setText(f"Redo {self._history.redo_label}   {REDO_KEYS}")
        else:
            self.undo_line.setText("")
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `mise run test -- tests/test_split_tab.py -q`

Expected: all pass.

- [ ] **Step 7: Run the whole gate**

Run: `mise run check`

Expected: all green.

- [ ] **Step 8: Commit**

```bash
git add src/maskingframe/gui/split_tab.py tests/test_split_tab.py
git commit -m "feat(gui): say what undo would bring back, and on which key"
```

---

### Task 4: The shortcuts, and the documentation

**Files:**
- Modify: `src/maskingframe/gui/split_tab.py` (imports; `_build`)
- Modify: `CLAUDE.md`
- Test: `tests/test_split_tab.py`

**Interfaces:**
- Consumes: from Task 2 — `SplitTab.undo()` and `SplitTab.redo()`.
- Produces: `SplitTab._undo_shortcut` and `SplitTab._redo_shortcut`, both `QShortcut`.

These are the first shortcuts in the application, so where they are owned is a decision rather than a default. `Qt.ShortcutContext.WidgetWithChildrenShortcut` means they fire only when focus is inside the Split tab: ⌘Z on the Compose tab must do nothing, not silently undo something on a tab you cannot see.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_split_tab.py`. The extra imports this needs — `Qt`, `QKeySequence`, `QShortcut` — go at the top of the file with the others.

```python
def test_the_undo_shortcut_is_the_platform_standard(tab: SplitTab) -> None:
    assert tab._undo_shortcut.key() == QKeySequence(QKeySequence.StandardKey.Undo)
    assert tab._redo_shortcut.key() == QKeySequence(QKeySequence.StandardKey.Redo)


def test_the_shortcuts_belong_to_the_split_tab_alone(tab: SplitTab) -> None:
    """These are the first shortcuts in the application, so the scope is a
    decision: the same keys on the Compose tab must do nothing rather than
    quietly change a tab you cannot see."""
    for shortcut in (tab._undo_shortcut, tab._redo_shortcut):
        assert shortcut.context() == Qt.ShortcutContext.WidgetWithChildrenShortcut
        assert shortcut.parentWidget() is tab


def test_the_undo_key_reaches_the_frames(qtbot: Any, tab: SplitTab, tmp_path: Path) -> None:
    """The shortcut, not the method: a scope that silently never fires would
    pass every other test in this file."""
    tab.show()
    qtbot.waitExposed(tab)
    _loaded(qtbot, tab, tmp_path)
    tab._move_position(0, 0.42)
    tab._on_frame_settled(0)
    placed = tab.positions()
    tab.reset_frames()

    tab.setFocus()
    qtbot.keyClick(tab, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)

    qtbot.waitUntil(lambda: tab.positions() == placed)
```

Note on that last test: `Qt.KeyboardModifier.ControlModifier` is the correct modifier to send on every platform, because Qt maps it to Command on macOS.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `mise run test -- tests/test_split_tab.py -q -k shortcut`

Expected: FAIL with `AttributeError: 'SplitTab' object has no attribute '_undo_shortcut'`.

- [ ] **Step 3: Add the shortcuts**

In `src/maskingframe/gui/split_tab.py`, extend the `PySide6.QtGui` import to include `QShortcut` alongside `QKeySequence`, and make sure `Qt` is imported from `PySide6.QtCore`.

At the end of `_build`, add:

```python
        # The first shortcuts in the application, so the scope is a decision
        # rather than a default: bound to this tab and its children, so the
        # same keys on Compose do nothing at all rather than quietly undoing
        # something on a tab you cannot see.
        self._undo_shortcut = QShortcut(QKeySequence.StandardKey.Undo, self)
        self._undo_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._undo_shortcut.activated.connect(self.undo)
        self._redo_shortcut = QShortcut(QKeySequence.StandardKey.Redo, self)
        self._redo_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._redo_shortcut.activated.connect(self.redo)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `mise run test -- tests/test_split_tab.py -q`

Expected: all pass.

- [ ] **Step 5: Document the behaviour**

In `CLAUDE.md`, immediately after the section headed `### Remembering where the frames were`, add:

```markdown
### Walking a placement back

Placing the detail frames is the craft work here, and `Even` discards every
hand-placed position in one press. `gui/history.py` is the way back: a list
of plans with a cursor, no Qt and no I/O, so it is tested in memory the way
`geometry` is.

A snapshot is the plan and nothing else — the positions and the row count.
Not the selection, which is which frame you are looking at rather than work
you have done, and which `_set_positions` already drops when a plan cannot
hold it. Not the border, the gap or the colours: those have presets and are
remembered between launches, and a key that sometimes moves frames and
sometimes changes a colour is harder to predict than one that always does
the same kind of thing.

`SplitTab._remember()` writes the plan to the store and `_record(label)`
notes it as a step, and the seven settles call both. **Undo and redo call
`_remember()` but never `_record()`** — that is what stops them recording
themselves, and it is the one invariant a test holds. Applying a snapshot
moves the rows combo under `_filling_rows`, so the move cannot be mistaken
for a choice and cannot record a step of its own either.

`record` ignores a snapshot equal to the one on screen. A settle fires
whether or not anything moved — an arrow key held against the clamp, a drag
that went nowhere — and recording those would give undo presses that
visibly do nothing.

The history clears on every change of source, including to none and to
folder mode: undoing into a plan made for a different photograph would
restore crops that mean nothing. It survives a ratio change, because a
position is a fraction of the panorama's width and means the same thing at
every ratio — which is also why the stored plan is not keyed on the ratio.

Undo writes to the store like any other change, so quitting after one and
reopening gives back what was on screen rather than the version you undid.

`MAX_STEPS` is 50, dropping from the front. A snapshot is a handful of
floats, so the bound is against a list growing without limit over a long
session rather than against the memory.

`QShortcut` is built from `QKeySequence.StandardKey.Undo` and `.Redo`
rather than hardcoded keys, and `UNDO_KEYS`/`REDO_KEYS` ask Qt what this
platform calls them, so macOS reads ⌘Z and every other platform reads its
own convention without this file knowing which one it is on. These are the
first shortcuts in the application, so the scope is a decision:
`WidgetWithChildrenShortcut` on the Split tab, so ⌘Z on Compose does
nothing rather than quietly changing a tab you cannot see.

`split_tab.undo_line` sits under the count controls and reads
`Undo Even   ⌘Z`, falling back to `Redo <label>` once undo has nothing
left and empty when there is neither. It carries the key because the
application has no menu bar, so there is nowhere else a shortcut could be
advertised — and an undo nobody knows about is close to no undo. The label
is the risk rather than the depth: a line that says `Undo Even` and then
restores something else is worse than no line, so each of the seven sites
names its own action and the tests assert the label beside the state.

It is `undo_line`, not `undo_label`, because `History.undo_label` is a
string and having the two spellings mean different things one attribute
apart is a trap.

Compose gets none of this: its arrangement is already reversible by
choosing another, and its source list has explicit add and remove.
```

Also add one line to the `### Behaviour changes from the pre-refactor scripts` list at the end of `CLAUDE.md`:

```markdown
- The Split tab's frame placement can be undone and redone (⌘Z and ⇧⌘Z, or the platform equivalent). Fifty steps, cleared when the source changes, and the undone plan is written to the store like any other change. Nothing on the CLI changes: a position is chosen by looking at a photograph, so there was never a flag to undo.
```

- [ ] **Step 6: Run the whole gate**

Run: `mise run check`

Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add src/maskingframe/gui/split_tab.py tests/test_split_tab.py CLAUDE.md
git commit -m "feat(gui): reach undo from the keyboard"
```

---

## Verification

- [ ] `mise run check` passes: ruff lint, ruff format check, mypy --strict, and the whole suite.
- [ ] `tests/test_gui_history.py` exists and its 11 tests pass with no Qt import in the file.
- [ ] A test asserts that undo and redo do not become undoable steps.
- [ ] A test asserts undo writes the restored plan to the store.
- [ ] A test asserts a source change clears the history and a ratio change does not.
- [ ] A test asserts the shortcut's context is `WidgetWithChildrenShortcut`.
- [ ] `grep -n "_record" src/maskingframe/gui/split_tab.py` shows exactly eight lines: the definition and the seven call sites. Neither `undo` nor `redo` is among them.
- [ ] Launch `mise run gui`, load a panorama, drag a frame, press `Even`, and confirm the line under the count controls reads `Undo Even   ⌘Z` and that pressing ⌘Z brings the dragged position back.
