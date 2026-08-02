# Keyboard Positioning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every detail-frame position reachable from the keyboard, with the selection marked visibly and named for a screen reader.

**Architecture:** The Split tab already owns the positions and applies the one move rule through `geometry.move_position`; it now also owns which detail frame is selected. The ribbon and the contact strip each take focus, handle keys, draw the selection, and emit a *count of steps* rather than a distance — so a step size stays policy in the tab and the two presentation widgets learn nothing about panoramas or ratios.

**Tech Stack:** Python 3.13, PySide6 (Qt), pytest + pytest-qt, mypy --strict, ruff, mise + uv.

## Global Constraints

- Dependency direction is one-way: `geometry` and `layout` are leaves; `compose` uses both; `pipeline` uses all three; `cli` and `gui/` use **only** `pipeline`. Nothing outside `gui/` changes in this plan.
- `gui/ribbon.py`, `gui/strip.py` and `gui/theme.py` are presentation only. They take plain data and must never learn what a `FrameStyle` or an `AspectRatio` is. A step size is policy: the widgets emit step counts, the tab turns a step into 1% of the panorama's width.
- Each widget speaks its own frame numbering. The ribbon's windows are detail frames, so it speaks detail indices. The strip's frames include frame 1, so it speaks strip indices, matching its existing `frame_dragged`. The tab converts.
- `theme.CHINAGRAPH` is the marking-up layer: the selected frame's numeral and edge. Focus stays `INK` — a field turning chinagraph when you tab into it reads as invalid.
- No rounded corners, no drop shadows, no animation.
- Selection must never be carried by colour alone. The rail states it in words, and the same words go to `setAccessibleName`.
- Qt concurrency rule: a job returns plain data, callbacks run on the GUI thread via `work.submit` with `owner=self` when the callback touches a widget, and background answers carry a monotonic token.
- Round half-up with `math.floor(v + 0.5)`. Never Python's `round()`.
- Verification: `mise run check` (ruff lint, ruff format check, mypy --strict, pytest). It must pass before every commit.
- Run single tests with `mise exec -- uv run pytest <path> -v`. GUI tests run offscreen; `tests/conftest.py` sets `QT_QPA_PLATFORM` before Qt is imported.
- Conventional commits, imperative mood, plain English. **No Claude attribution trailers and no emoji** — pre-commit hooks reject both.
- Work directly on `master`. Trunk-based development; do not create a branch.
- Comments explain *why*, not *what*.

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `src/maskingframe/gui/ribbon.py` | Focus, keys, selection drawing, step-count signals | Modify |
| `src/maskingframe/gui/strip.py` | The same, in strip indices | Modify |
| `src/maskingframe/gui/split_tab.py` | Owns the selection, converts steps, rail readout, tab order | Modify |
| `tests/test_ribbon.py` | Ribbon key handling and selection | Modify |
| `tests/test_strip.py` | Strip key handling and selection | Modify |
| `tests/test_split_tab.py` | The wiring, the readout, the clamp | Modify |
| `CLAUDE.md` | Record the keyboard model | Modify |

**Task order:** 1 and 2 are independent but must not run concurrently (shared git index). Then 3, then 4.

---

### Task 1: The ribbon takes focus and keys

**Files:**
- Modify: `src/maskingframe/gui/ribbon.py`
- Test: `tests/test_ribbon.py`

**Interfaces:**
- Consumes: the existing `FrameRibbon` — `frame_moved(int, float)`, `frame_settled(int)`, `set_source`, `set_plan(positions, window_fraction)`, `positions()`, `window_rects()`, `picture_rect()`, `surface_rect()`.
- Produces, on `FrameRibbon`:
  - `frame_nudged = Signal(int, int)` — (detail frame index, step count; ±1, ±10, ±100)
  - `selection_changed = Signal(int)` — (detail frame index)
  - `set_selected(index: int | None) -> None` — silent
  - `selected() -> int | None`

- [x] **Step 1: Write the failing tests**

Add to `tests/test_ribbon.py`:

```python
def test_the_ribbon_takes_focus(qtbot: QtBot) -> None:
    ribbon = build(qtbot)
    assert ribbon.focusPolicy() == Qt.FocusPolicy.StrongFocus


def test_taking_focus_selects_the_first_frame(qtbot: QtBot) -> None:
    # Nothing is marked until the user asks for it, and once the keys can be
    # pressed they always have something to act on.
    ribbon = build(qtbot)
    assert ribbon.selected() is None
    ribbon.setFocus()
    ribbon.focusInEvent(QFocusEvent(QEvent.Type.FocusIn))
    assert ribbon.selected() == 0


def test_set_selected_is_silent(qtbot: QtBot) -> None:
    ribbon = build(qtbot)
    with qtbot.assertNotEmitted(ribbon.selection_changed):
        ribbon.set_selected(1)
    assert ribbon.selected() == 1


def test_right_arrow_nudges_the_selected_frame_by_one_step(qtbot: QtBot) -> None:
    ribbon = build(qtbot, (0.0, 0.6))
    ribbon.set_selected(1)
    with qtbot.waitSignal(ribbon.frame_nudged, timeout=1000) as blocker:
        qtbot.keyClick(ribbon, Qt.Key.Key_Right)
    assert blocker.args == [1, 1]


def test_left_arrow_nudges_the_other_way(qtbot: QtBot) -> None:
    ribbon = build(qtbot, (0.0, 0.6))
    ribbon.set_selected(1)
    with qtbot.waitSignal(ribbon.frame_nudged, timeout=1000) as blocker:
        qtbot.keyClick(ribbon, Qt.Key.Key_Left)
    assert blocker.args == [1, -1]


def test_shift_makes_the_step_ten_times_bigger(qtbot: QtBot) -> None:
    ribbon = build(qtbot, (0.0, 0.6))
    ribbon.set_selected(0)
    with qtbot.waitSignal(ribbon.frame_nudged, timeout=1000) as blocker:
        qtbot.keyClick(ribbon, Qt.Key.Key_Right, Qt.KeyboardModifier.ShiftModifier)
    assert blocker.args == [0, 10]


def test_home_and_end_span_the_whole_width(qtbot: QtBot) -> None:
    # A hundred steps is the whole panorama; the tab's clamp does the rest.
    ribbon = build(qtbot, (0.0, 0.6))
    ribbon.set_selected(1)
    with qtbot.waitSignal(ribbon.frame_nudged, timeout=1000) as blocker:
        qtbot.keyClick(ribbon, Qt.Key.Key_Home)
    assert blocker.args == [1, -100]
    with qtbot.waitSignal(ribbon.frame_nudged, timeout=1000) as blocker:
        qtbot.keyClick(ribbon, Qt.Key.Key_End)
    assert blocker.args == [1, 100]


def test_down_and_up_move_the_selection(qtbot: QtBot) -> None:
    ribbon = build(qtbot, (0.0, 0.3, 0.6))
    ribbon.set_selected(0)
    with qtbot.waitSignal(ribbon.selection_changed, timeout=1000) as blocker:
        qtbot.keyClick(ribbon, Qt.Key.Key_Down)
    assert blocker.args == [1]
    assert ribbon.selected() == 1
    with qtbot.waitSignal(ribbon.selection_changed, timeout=1000) as blocker:
        qtbot.keyClick(ribbon, Qt.Key.Key_Up)
    assert blocker.args == [0]


def test_the_selection_stops_at_the_ends_rather_than_wrapping(qtbot: QtBot) -> None:
    # Wrapping from the last frame back to the first loses your place on a
    # picture you are reading left to right.
    ribbon = build(qtbot, (0.0, 0.3, 0.6))
    ribbon.set_selected(2)
    with qtbot.assertNotEmitted(ribbon.selection_changed):
        qtbot.keyClick(ribbon, Qt.Key.Key_Down)
    assert ribbon.selected() == 2
    ribbon.set_selected(0)
    with qtbot.assertNotEmitted(ribbon.selection_changed):
        qtbot.keyClick(ribbon, Qt.Key.Key_Up)
    assert ribbon.selected() == 0


def test_keys_do_nothing_with_no_plan(qtbot: QtBot) -> None:
    ribbon = FrameRibbon()
    qtbot.addWidget(ribbon)
    ribbon.resize(600, RIBBON_HEIGHT)
    with qtbot.assertNotEmitted(ribbon.frame_nudged):
        qtbot.keyClick(ribbon, Qt.Key.Key_Right)


def test_the_selected_window_is_marked_in_chinagraph(qtbot: QtBot) -> None:
    # Chinagraph is the marking-up layer: the frame you have picked.
    ribbon = build(qtbot, (0.0, 0.6))
    ribbon.set_selected(1)
    assert ribbon.marked_rect() == ribbon.window_rects()[1]
    ribbon.set_selected(None)
    assert ribbon.marked_rect().isNull()


def test_the_ribbon_names_what_is_selected(qtbot: QtBot) -> None:
    ribbon = build(qtbot, (0.0, 0.6))
    ribbon.set_selected(1)
    assert "3" in ribbon.accessibleName()
```

Add whatever imports these need to the top of the file: `QEvent`, `QFocusEvent`, and `Qt` if it is not already there.

- [x] **Step 2: Run the tests to verify they fail**

Run: `mise exec -- uv run pytest tests/test_ribbon.py -v`
Expected: FAIL with `AttributeError: 'FrameRibbon' object has no attribute 'selection_changed'`.

- [x] **Step 3: Implement**

Add the two signals under the existing ones, keeping the same documentation voice:

```python
    frame_nudged = Signal(int, int)
    """(frame index, step count). A count, not a distance: how far a step
    moves is policy, and the tab is the only thing that knows what a percent
    of this panorama is. Shift is ten steps; Home and End are a hundred,
    which spans the whole width and lets the tab's clamp do the rest."""

    selection_changed = Signal(int)
    """(frame index) when the keys move the selection. The tab owns which
    frame is selected -- the strip marks the same one -- so this asks rather
    than decides."""
```

In `__init__`, after the existing state:

```python
        self._selected: int | None = None
        # Reachable by Tab and by click. A window is a control, and a control
        # you can only reach with a pointer is not reachable at all.
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
```

Add the selection API next to `set_plan`:

```python
    def set_selected(self, index: int | None) -> None:
        """Mark one frame, or none. Emits nothing.

        Silent for the same reason `set_plan` is: the tab holds the one
        copy, and a widget that announced what it had just been told would
        write it straight back.
        """
        self._selected = index
        self._name_selection()
        self.update()

    def selected(self) -> int | None:
        return self._selected

    def marked_rect(self) -> QRect:
        """Where the selection is drawn, or a null rect. Exposed so the
        marking can be checked without sampling pixels."""
        if self._selected is None or not 0 <= self._selected < len(self._positions):
            return QRect()
        return self.window_rects()[self._selected]

    def _name_selection(self) -> None:
        """State the selection in words, for a screen reader.

        Numbered as the carousel is: frame 1 is the whole panorama, so
        detail frame 0 is frame 2. The rail says the same thing on screen,
        because a selection carried by colour alone fails the floor this
        project holds itself to.
        """
        if self._selected is None:
            self.setAccessibleName("Panorama overview")
            return
        position = self._positions[self._selected] if self._positions else 0.0
        self.setAccessibleName(
            f"Frame {self._selected + 2}, {math.floor(position * 100 + 0.5)} percent along"
        )
```

Add focus and key handling after the mouse handlers:

```python
    def focusInEvent(self, event: QFocusEvent) -> None:
        # Nothing is marked until the user asks for it; asking for it is
        # exactly what taking focus is.
        if self._selected is None and self._positions:
            self._selected = 0
            self._name_selection()
        super().focusInEvent(event)
        self.update()

    def focusOutEvent(self, event: QFocusEvent) -> None:
        super().focusOutEvent(event)
        self.update()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if not self._positions:
            super().keyPressEvent(event)
            return
        if self._selected is None:
            self._selected = 0
            self._name_selection()
        key = event.key()
        coarse = event.modifiers() & Qt.KeyboardModifier.ShiftModifier
        steps = {
            Qt.Key.Key_Left: -10 if coarse else -1,
            Qt.Key.Key_Right: 10 if coarse else 1,
            Qt.Key.Key_Home: -100,
            Qt.Key.Key_End: 100,
        }.get(key)
        if steps is not None:
            self.frame_nudged.emit(self._selected, steps)
            return
        if key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            wanted = self._selected + (1 if key == Qt.Key.Key_Down else -1)
            # Stops rather than wraps: a selection that jumped from the last
            # frame back to the first would lose your place on a picture you
            # are reading left to right.
            if 0 <= wanted < len(self._positions):
                self._selected = wanted
                self._name_selection()
                self.update()
                self.selection_changed.emit(wanted)
            return
        super().keyPressEvent(event)
```

In `paintEvent`, where each window's edge and numeral are drawn, make the selected one chinagraph. Replace the per-window drawing loop's pen choices so that the selected index uses `theme.CHINAGRAPH` for both the edge and the numeral, and every other window keeps `theme.INK` for the edge and its existing numeral colour. Do not change the edge's thickness or add any other decoration.

`Qt`, `QRect` and `math` are already imported; add `QFocusEvent` and `QKeyEvent` to the `PySide6.QtGui` import.

- [x] **Step 4: Run the tests to verify they pass**

Run: `mise exec -- uv run pytest tests/test_ribbon.py -v`
Expected: PASS, including every test that was already in the file.

- [x] **Step 5: Run the full gate and commit**

```bash
mise run check
git add src/maskingframe/gui/ribbon.py tests/test_ribbon.py
git commit -m "feat(gui): give the ribbon focus and keys"
```

---

### Task 2: The strip takes focus and keys

The same behaviour in the strip, in strip indices. Do not run this concurrently with Task 1 — they share a git index.

**Files:**
- Modify: `src/maskingframe/gui/strip.py`
- Test: `tests/test_strip.py`

**Interfaces:**
- Consumes: the existing `ContactStrip` — `frame_dragged(int, float)`, `frame_drag_settled(int)`, `set_draggable(bool)`, `frame_rect_at(index)`, `_frame_rect(index)`, `frame_count`.
- Produces, on `ContactStrip`:
  - `frame_nudged = Signal(int, int)` — (strip frame index, step count; ±1, ±10, ±100)
  - `selection_changed = Signal(int)` — (strip frame index)
  - `set_selected(index: int | None) -> None` — silent
  - `selected() -> int | None`

- [x] **Step 1: Write the failing tests**

Add to `tests/test_strip.py`:

```python
def test_the_strip_takes_focus(qtbot: QtBot) -> None:
    strip = ContactStrip(frames=4)
    qtbot.addWidget(strip)
    assert strip.focusPolicy() == Qt.FocusPolicy.StrongFocus


def test_taking_focus_selects_the_first_detail_frame(qtbot: QtBot) -> None:
    # Frame 0 is the whole panorama and has no position, so the first thing
    # worth selecting is frame 1.
    strip = ContactStrip(frames=4)
    qtbot.addWidget(strip)
    strip.set_draggable(True)
    strip.focusInEvent(QFocusEvent(QEvent.Type.FocusIn))
    assert strip.selected() == 1


def test_set_selected_is_silent_on_the_strip(qtbot: QtBot) -> None:
    strip = ContactStrip(frames=4)
    qtbot.addWidget(strip)
    with qtbot.assertNotEmitted(strip.selection_changed):
        strip.set_selected(2)
    assert strip.selected() == 2


def test_arrows_nudge_the_selected_strip_frame(qtbot: QtBot) -> None:
    strip = ContactStrip(frames=4)
    qtbot.addWidget(strip)
    strip.set_draggable(True)
    strip.set_selected(2)
    with qtbot.waitSignal(strip.frame_nudged, timeout=1000) as blocker:
        qtbot.keyClick(strip, Qt.Key.Key_Right)
    assert blocker.args == [2, 1]
    with qtbot.waitSignal(strip.frame_nudged, timeout=1000) as blocker:
        qtbot.keyClick(strip, Qt.Key.Key_Left, Qt.KeyboardModifier.ShiftModifier)
    assert blocker.args == [2, -10]


def test_home_and_end_span_the_width_on_the_strip(qtbot: QtBot) -> None:
    strip = ContactStrip(frames=4)
    qtbot.addWidget(strip)
    strip.set_draggable(True)
    strip.set_selected(1)
    with qtbot.waitSignal(strip.frame_nudged, timeout=1000) as blocker:
        qtbot.keyClick(strip, Qt.Key.Key_End)
    assert blocker.args == [1, 100]


def test_the_strip_selection_skips_the_whole_panorama_frame(qtbot: QtBot) -> None:
    strip = ContactStrip(frames=4)
    qtbot.addWidget(strip)
    strip.set_draggable(True)
    strip.set_selected(1)
    with qtbot.assertNotEmitted(strip.selection_changed):
        qtbot.keyClick(strip, Qt.Key.Key_Up)
    assert strip.selected() == 1


def test_strip_keys_do_nothing_when_not_draggable(qtbot: QtBot) -> None:
    # Folder mode: there is no one panorama whose frames could be placed.
    strip = ContactStrip(frames=4)
    qtbot.addWidget(strip)
    strip.set_selected(1)
    with qtbot.assertNotEmitted(strip.frame_nudged):
        qtbot.keyClick(strip, Qt.Key.Key_Right)


def test_the_selected_strip_frame_is_marked(qtbot: QtBot) -> None:
    strip = ContactStrip(frames=4)
    qtbot.addWidget(strip)
    strip.resize(600, 300)
    strip.set_selected(2)
    assert strip.marked_rect() == strip.frame_rect_at(2)
    strip.set_selected(None)
    assert strip.marked_rect().isNull()
```

Add `QEvent` and `QFocusEvent` to the file's imports if they are not there.

- [x] **Step 2: Run the tests to verify they fail**

Run: `mise exec -- uv run pytest tests/test_strip.py -k "focus or selected or nudge or marked" -v`
Expected: FAIL with `AttributeError: 'ContactStrip' object has no attribute 'selection_changed'`.

- [x] **Step 3: Implement**

Add the signals under the existing ones:

```python
    frame_nudged = Signal(int, int)
    """(frame index, step count). Strip indices, like `frame_dragged`, so
    this widget speaks one numbering throughout; the tab converts. A count
    rather than a distance, because how far a step moves is policy and the
    strip has never heard of a panorama's width."""

    selection_changed = Signal(int)
    """(frame index) when the keys move the selection."""
```

In `__init__`, beside the drag state:

```python
        self._selected: int | None = None
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
```

Add the selection API next to `set_draggable`:

```python
    def set_selected(self, index: int | None) -> None:
        """Mark one frame, or none. Emits nothing.

        Drawn whether or not the strip is draggable: in folder mode there is
        still a frame under the cursor worth naming, even though there is no
        position to move.
        """
        self._selected = index
        self.update()

    def selected(self) -> int | None:
        return self._selected

    def marked_rect(self) -> QRect:
        """Where the selection is drawn, or a null rect."""
        if self._selected is None or not 0 <= self._selected < len(self._frames):
            return QRect()
        return self._frame_rect(self._selected)
```

Add focus and key handling after the mouse handlers. Frame 0 is the whole panorama, so the selection floor is 1:

```python
    def focusInEvent(self, event: QFocusEvent) -> None:
        if self._selected is None and len(self._frames) > 1:
            self._selected = 1
        super().focusInEvent(event)
        self.update()

    def focusOutEvent(self, event: QFocusEvent) -> None:
        super().focusOutEvent(event)
        self.update()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        # Folder mode makes the strip a display: there is no one panorama
        # whose frames could be placed, so the keys have nothing to act on.
        if not self._draggable or len(self._frames) < 2:
            super().keyPressEvent(event)
            return
        if self._selected is None or self._selected < 1:
            self._selected = 1
        key = event.key()
        coarse = event.modifiers() & Qt.KeyboardModifier.ShiftModifier
        steps = {
            Qt.Key.Key_Left: -10 if coarse else -1,
            Qt.Key.Key_Right: 10 if coarse else 1,
            Qt.Key.Key_Home: -100,
            Qt.Key.Key_End: 100,
        }.get(key)
        if steps is not None:
            self.frame_nudged.emit(self._selected, steps)
            return
        if key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            wanted = self._selected + (1 if key == Qt.Key.Key_Down else -1)
            # Floor of 1: frame 0 shows the whole panorama, so there is no
            # position in it to select.
            if 1 <= wanted < len(self._frames):
                self._selected = wanted
                self.update()
                self.selection_changed.emit(wanted)
            return
        super().keyPressEvent(event)
```

In `_paint_frame`, draw the selected frame's numeral in `theme.CHINAGRAPH` and every other in its existing colour. Do not change the aperture hairline's weight, and add no other decoration.

Give the strip an accessible name that says the same thing, from the same
places `set_selected`, `focusInEvent` and `keyPressEvent` change the selection:

```python
    def _name_selection(self) -> None:
        """State the selection in words, for a screen reader.

        The rail says the same thing on screen. Both, not either: a state
        carried by colour alone fails the floor this project holds itself to.
        """
        if self._selected is None:
            self.setAccessibleName("Contact strip")
            return
        self.setAccessibleName(f"Frame {self._selected + 1} of {len(self._frames)}")
```

Numbered as the strip itself numbers them, because that is what the caption
under each frame says.

Add `QFocusEvent` and `QKeyEvent` to the `PySide6.QtGui` import.

- [x] **Step 4: Run the tests to verify they pass**

Run: `mise exec -- uv run pytest tests/test_strip.py -v`
Expected: PASS, including every test that was already in the file.

- [x] **Step 5: Run the full gate and commit**

```bash
mise run check
git add src/maskingframe/gui/strip.py tests/test_strip.py
git commit -m "feat(gui): give the contact strip focus and keys"
```

---

### Task 3: The tab owns the selection

**Files:**
- Modify: `src/maskingframe/gui/split_tab.py`
- Test: `tests/test_split_tab.py`

**Interfaces:**
- Consumes: `FrameRibbon.frame_nudged(int, int)`, `FrameRibbon.selection_changed(int)`, `FrameRibbon.set_selected(int | None)`; `ContactStrip.frame_nudged(int, int)`, `ContactStrip.selection_changed(int)`, `ContactStrip.set_selected(int | None)`; the existing `SplitTab._move_position(index, wanted, anchor=None)` and `SplitTab._positions`.
- Produces: `SplitTab.KEY_STEP`, `SplitTab.selected()`, `SplitTab.selection_label`.

- [x] **Step 1: Write the failing tests**

Add to `tests/test_split_tab.py`:

```python
def loaded(qtbot: QtBot, tmp_path: Path) -> SplitTab:
    """A tab with a panorama loaded and its plan settled."""
    source = tmp_path / "pano.jpg"
    conftest.synthetic_panorama(3000, 1000).save(source, "JPEG", quality=95)
    tab = SplitTab()
    qtbot.addWidget(tab)
    tab.show()
    tab.source_row.setText(str(source))
    qtbot.waitUntil(lambda: tab.positions() != (), timeout=3000)
    return tab


def test_a_step_moves_the_selected_frame_one_percent(qtbot: QtBot, tmp_path: Path) -> None:
    tab = loaded(qtbot, tmp_path)
    tab.ribbon.set_selected(1)
    before = tab.positions()

    tab.ribbon.frame_nudged.emit(1, 1)

    after = tab.positions()
    assert after[1] == pytest.approx(before[1] + 0.01)
    assert after[0] == before[0]
    assert after[2:] == before[2:]


def test_a_coarse_step_moves_it_ten_percent(qtbot: QtBot, tmp_path: Path) -> None:
    tab = loaded(qtbot, tmp_path)
    before = tab.positions()

    tab.ribbon.frame_nudged.emit(1, 10)

    assert tab.positions()[1] == pytest.approx(before[1] + 0.10)


def test_a_hundred_steps_reaches_the_end_of_the_travel(qtbot: QtBot, tmp_path: Path) -> None:
    tab = loaded(qtbot, tmp_path)
    last = len(tab.positions()) - 1

    tab.ribbon.frame_nudged.emit(last, 100)

    # Clamped by the same rule a drag obeys, so it lands on the travel's end.
    assert tab.positions()[last] == pytest.approx(
        pipeline.position_travel(3000, 1000, pipeline.RATIOS[tab._ratio_name()])
    )


def test_a_key_press_clamps_at_a_neighbour_exactly_as_a_drag_does(
    qtbot: QtBot, tmp_path: Path
) -> None:
    tab = loaded(qtbot, tmp_path)
    before = tab.positions()

    tab.ribbon.frame_nudged.emit(0, 100)

    after = tab.positions()
    assert after[0] == pytest.approx(before[1])
    assert after[1:] == before[1:]


def test_a_strip_nudge_moves_the_same_frame(qtbot: QtBot, tmp_path: Path) -> None:
    # Strip frame 2 is detail frame 1: frame 1 is the whole panorama.
    tab = loaded(qtbot, tmp_path)
    before = tab.positions()

    tab.strip.frame_nudged.emit(2, 1)

    assert tab.positions()[1] == pytest.approx(before[1] + 0.01)


def test_the_two_views_mark_the_same_frame(qtbot: QtBot, tmp_path: Path) -> None:
    tab = loaded(qtbot, tmp_path)

    tab.ribbon.selection_changed.emit(2)

    assert tab.selected() == 2
    assert tab.ribbon.selected() == 2
    # Strip indices are one further along: frame 1 is the whole panorama.
    assert tab.strip.selected() == 3


def test_a_strip_selection_reaches_the_ribbon(qtbot: QtBot, tmp_path: Path) -> None:
    tab = loaded(qtbot, tmp_path)

    tab.strip.selection_changed.emit(3)

    assert tab.selected() == 2
    assert tab.ribbon.selected() == 2


def test_the_rail_states_the_selection_without_relying_on_colour(
    qtbot: QtBot, tmp_path: Path
) -> None:
    tab = loaded(qtbot, tmp_path)

    tab.ribbon.selection_changed.emit(1)

    text = tab.selection_label.text()
    # Numbered as the carousel is: detail frame 1 is frame 3.
    assert "Frame 3" in text
    assert "%" in text


def test_the_readout_clears_when_the_source_goes(qtbot: QtBot, tmp_path: Path) -> None:
    tab = loaded(qtbot, tmp_path)
    tab.ribbon.selection_changed.emit(1)
    assert tab.selection_label.text() != ""

    tab.source_row.setText("")

    assert tab.selection_label.text() == ""
    assert tab.selected() is None


def test_the_ribbon_comes_before_the_strip_in_the_tab_order(
    qtbot: QtBot, tmp_path: Path
) -> None:
    # Source, then results, matching how they sit on the table.
    tab = loaded(qtbot, tmp_path)
    widget = tab.ribbon
    for _ in range(20):
        widget = widget.nextInFocusChain()
        if widget is tab.strip:
            break
        assert widget is not tab.ribbon, "walked the whole chain without reaching the strip"
    assert widget is tab.strip
```

The chain is walked rather than checked one step ahead because Qt puts a
widget's own children in it, so the strip is not necessarily the very next
entry after the ribbon.

- [x] **Step 2: Run the tests to verify they fail**

Run: `mise exec -- uv run pytest tests/test_split_tab.py -k "step or nudge or selection or readout or tab_order" -v`
Expected: FAIL with `AttributeError: 'SplitTab' object has no attribute 'selection_label'`.

- [x] **Step 3: Implement**

Add the constant near `NO_POSITIONS`:

```python
KEY_STEP = 0.01
"""How far one arrow press moves a frame, as a fraction of the panorama's
width. Shift is ten of these and Home/End a hundred, which spans the whole
width and lets the clamp do the rest.

A round number in the unit a position is actually stored in, so the help
text can state it exactly. The widgets emit a count of these rather than a
distance: how far a step moves is policy, and the tab is the only thing that
knows what a percent of this panorama is."""
```

In `_build`, after `count_label` and its counter row, add the readout:

```python
        rail.addSpacing(theme.S)
        # The selection in words. The marking on the picture is chinagraph,
        # and a state carried by colour alone fails the floor this project
        # holds itself to -- so it is also said here, and handed to the
        # widgets as their accessible name.
        self.selection_label = shell.data_label()
        rail.addWidget(self.selection_label)
```

After both widgets exist at the end of `_build`:

```python
        self.ribbon.frame_nudged.connect(self._on_frame_nudged)
        self.ribbon.selection_changed.connect(self._on_ribbon_selection)
        self.strip.frame_nudged.connect(self._on_strip_nudged)
        self.strip.selection_changed.connect(self._on_strip_selection)
        # Source, then results, matching how they sit on the table.
        self.setTabOrder(self.ribbon, self.strip)
```

Add the selection state to `__init__`:

```python
        self._selected: int | None = None
```

And the handlers, beside `_move_position`:

```python
    def selected(self) -> int | None:
        """Which detail frame is marked, in detail-frame indices."""
        return self._selected

    def _set_selected(self, index: int | None) -> None:
        """Mark one detail frame in both views, and say so in the rail.

        The tab holds the one copy, as it does for the positions: two views
        that disagreed about which frame was selected would be two features.
        The ribbon speaks detail indices and the strip speaks strip indices,
        so the conversion happens here -- the same place the drags convert.
        """
        self._selected = index
        self.ribbon.set_selected(index)
        self.strip.set_selected(None if index is None else index + 1)
        self._state_selection()

    def _state_selection(self) -> None:
        if self._selected is None or not 0 <= self._selected < len(self._positions):
            self.selection_label.setText("")
            return
        along = math.floor(self._positions[self._selected] * 100 + 0.5)
        self.selection_label.setText(f"Frame {self._selected + 2} · {along}% along")

    def _nudge(self, index: int, steps: int) -> None:
        """Move one detail frame by `steps` of `KEY_STEP`. GUI thread only.

        Straight through `_move_position`, so a key press and a drag obey
        the one ordering rule and cannot disagree.
        """
        if not 0 <= index < len(self._positions):
            return
        self._move_position(index, self._positions[index] + steps * KEY_STEP)
        self._state_selection()
        self._rerender()

    def _on_frame_nudged(self, index: int, steps: int) -> None:
        self._nudge(index, steps)

    def _on_strip_nudged(self, index: int, steps: int) -> None:
        # Strip frame 1 is detail frame 0: frame 1 is the whole panorama.
        self._nudge(index - 1, steps)

    def _on_ribbon_selection(self, index: int) -> None:
        self._set_selected(index)

    def _on_strip_selection(self, index: int) -> None:
        self._set_selected(index - 1)
```

Add `import math` if it is not already there.

In `_apply_facts`, after the positions are adopted, keep the readout honest:

```python
        self._state_selection()
```

In `_clear_facts`, drop the selection with everything else:

```python
        self._set_selected(None)
```

Every re-render a nudge triggers goes through the existing `_rerender`, so the preview follows the keys exactly as it follows a drag settle.

- [x] **Step 4: Run the tests to verify they pass**

Run: `mise exec -- uv run pytest tests/test_split_tab.py -v`
Expected: PASS, including every test that was already in the file.

- [x] **Step 5: Check it by hand, offscreen**

```bash
QT_QPA_PLATFORM=offscreen mise exec -- uv run python - <<'PY'
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
import time
app = QApplication([])
from maskingframe.gui.app import MainWindow
w = MainWindow(); w.resize(1280, 960); w.show()
tab = w.split
tab.source_row.setText("tests/fixtures/golden_wide.jpg")
for _ in range(300):
    app.processEvents(); time.sleep(0.02)
    if tab.ribbon.window_rects(): break
tab.ribbon.setFocus()
print("before:", tab.positions())
for _ in range(5):
    QTest.keyClick(tab.ribbon, Qt.Key.Key_Right)
    app.processEvents()
print("after five presses:", tab.positions())
print("rail says:", tab.selection_label.text())
print("accessible:", tab.ribbon.accessibleName())
w.grab().save("/tmp/keyboard.png")
PY
```

Five presses must move the selected frame by 5% and the rail must name it. Open `/tmp/keyboard.png` and confirm the selected window is marked in chinagraph and the others are not. Report what you saw.

- [x] **Step 6: Run the full gate and commit**

```bash
mise run check
git add src/maskingframe/gui/split_tab.py tests/test_split_tab.py
git commit -m "feat(gui): place the detail frames from the keyboard"
```

---

### Task 4: Documentation

**Files:**
- Modify: `CLAUDE.md`

- [x] **Step 1: Record the keyboard model**

In the section on where the detail frames land, after the paragraph about the ribbon and the strip both writing to one tuple, add:

```markdown
Both views also take focus and handle keys, because a feature that decides what
every output frame contains must not need a pointer. Left and Right move the
selected frame by `split_tab.KEY_STEP` (1% of the panorama's width), Shift makes
that ten steps, Home and End send it to the ends of its travel, and Up and Down
move the selection, stopping at the ends rather than wrapping. A key press goes
through `geometry.move_position`, the same rule both drags obey, so the two
cannot disagree.

The widgets emit a count of steps rather than a distance. How far a step moves
is policy, and the tab is the only thing that knows what a percent of this
panorama is — so `ribbon.py` and `strip.py` stay presentation only. Each widget
speaks its own numbering: the ribbon's windows are detail frames, the strip's
frames include frame 1, and the tab converts, exactly as it does for the drags.

The selection is marked in chinagraph on the selected frame's numeral and edge,
and stated in words in the rail (`Frame 3 · 42% along`). Both, not either: a
state carried by colour alone fails the WCAG 2.2 AA floor this project holds.
The rail's wording is what the widgets hand to `setAccessibleName`, so a screen
reader and the screen say the same thing.
```

Add `SplitTab.KEY_STEP` to the `gui/` bullet's description of `split_tab.py` if that bullet lists such things.

- [x] **Step 2: Run the full gate and commit**

```bash
mise run check
git add CLAUDE.md
git commit -m "docs: record how the keyboard places the detail frames"
```

---

## Verification

- [x] `mise run check` passes on a clean tree.
- [x] With a panorama loaded, Tab reaches the ribbon and then the strip, and both show a visible focus state.
- [x] Arrow keys move the selected frame; Shift moves it further; Home and End reach the ends; Up and Down change the selection and stop at the ends.
- [x] The rail names the selected frame and its position, and clears when the source is cleared.
- [x] The selected frame is marked in chinagraph in both views, and no other frame is.
- [x] In folder mode the strip's keys do nothing.
- [x] `grep -rn "import geometry" src/maskingframe/gui/` returns nothing.
