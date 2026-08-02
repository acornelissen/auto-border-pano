# Border Presets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a border be saved under a name and chosen again from either tab.

**Architecture:** `gui/settings.py` — already the only module that touches `QSettings` — gains a list of named `FrameStyle`s per scope, three seeded built-ins, and per-preset validation. `gui/shell.py` gains a `PresetRow` widget that owns the naming rules and nothing else, placed at the top of `BorderControls`. Each tab connects the row to its own scope. Nothing outside `gui/` changes.

**Tech Stack:** Python 3.13, PySide6 (Qt), pytest + pytest-qt, mypy --strict, ruff, mise + uv.

## Global Constraints

- Dependency direction is one-way: `geometry` and `layout` are leaves; `compose` uses both; `pipeline` uses all three; `cli` and `gui/` use **only** `pipeline`. Nothing outside `gui/` changes in this plan, and no `FrameStyle` field is added.
- `gui/settings.py` is the only module that may construct a `QSettings`. It states format and scope explicitly — the two-argument `QSettings(organisation, application)` constructor pins itself to the platform's native format and then ignores `setPath`, which on macOS means a plist a test cannot redirect.
- A stored value is untrusted input. Every preset is validated by constructing a `FrameStyle`; a malformed preset is dropped **on its own**, leaving its neighbours intact. This differs deliberately from `load_style`, which falls back whole.
- `gui/shell.py` widgets take plain data and never touch `QSettings` themselves.
- `theme.CHINAGRAPH` is the marking-up layer: the primary action, selection, numbering, errors. The preset row's buttons are chrome and take `Secondary`.
- No rounded corners, no drop shadows, no animation.
- Round half-up with `math.floor(v + 0.5)`. Never Python's `round()`.
- Qt: a job returns plain data, callbacks run on the GUI thread via `work.submit` with `owner=self` when the callback touches a widget.
- Verification: `mise run check` (ruff lint, ruff format check, mypy --strict, pytest). It must pass before every commit.
- Run single tests with `mise exec -- uv run pytest <path> -v`. GUI tests run offscreen; `tests/conftest.py` sets `QT_QPA_PLATFORM` before Qt is imported, and the `isolated_settings` fixture redirects `QSettings` — **every test that reads or writes settings must use it**, or it will read the developer's real preferences.
- Conventional commits, imperative mood, plain English. **No Claude attribution trailers and no emoji** — pre-commit hooks reject both.
- Work directly on `master`. Trunk-based development; do not create a branch.
- Comments explain *why*, not *what*.

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `src/maskingframe/gui/settings.py` | Storing, validating and seeding presets | Modify |
| `src/maskingframe/gui/shell.py` | `PresetRow`, and its place in `BorderControls` | Modify |
| `src/maskingframe/gui/split_tab.py` | Wires the row to the `SPLIT` scope | Modify |
| `src/maskingframe/gui/compose_tab.py` | Wires the row to the `COMPOSE` scope | Modify |
| `tests/test_gui_settings.py` | Storage, validation, seeding | Modify |
| `tests/test_gui_shell.py` | The widget's naming rules | Modify |
| `tests/test_split_tab.py`, `tests/test_compose_tab.py` | The wiring | Modify |
| `CLAUDE.md` | Record the preset model | Modify |

**Task order:** 1 → 2 → 3 → 4. Task 3 touches both tabs and must not be split across concurrent agents.

---

### Task 1: Presets in the store

**Files:**
- Modify: `src/maskingframe/gui/settings.py`
- Test: `tests/test_gui_settings.py`

**Interfaces:**
- Consumes: `settings._store()`, `settings._percent()`, `settings._flag()`, `settings.SPLIT`, `settings.COMPOSE`, `pipeline.FrameStyle`, `pipeline.DEFAULT_STYLE`.
- Produces:
  - `settings.load_presets(scope: str) -> dict[str, pipeline.FrameStyle]` — alphabetical by name, case-insensitive
  - `settings.save_preset(scope: str, name: str, style: pipeline.FrameStyle) -> None`
  - `settings.delete_preset(scope: str, name: str) -> None`
  - `settings.MAX_NAME = 40`
  - `settings.clean_name(name: str) -> str` — trimmed and truncated; raises `ValueError` if empty once trimmed
  - `settings.BUILT_INS: dict[str, dict[str, pipeline.FrameStyle]]` — keyed by scope, then name
  - `settings.seed_presets() -> None` — runs once, recorded by a flag

- [x] **Step 1: Write the failing tests**

Add to `tests/test_gui_settings.py`. Every test takes the `isolated_settings` fixture — without it these write to the developer's real preferences:

```python
def test_a_preset_round_trips(isolated_settings: Path) -> None:
    style = pipeline.FrameStyle(border_percent=12.5, border_colour="#102030")
    settings.save_preset(settings.SPLIT, "Warm white", style)

    assert settings.load_presets(settings.SPLIT)["Warm white"] == style


def test_presets_come_back_alphabetically_whatever_order_they_went_in(
    isolated_settings: Path,
) -> None:
    # The list grows, and insertion order stops being findable once it does.
    for name in ("zinc", "Alder", "mahogany"):
        settings.save_preset(settings.SPLIT, name, pipeline.DEFAULT_STYLE)

    assert list(settings.load_presets(settings.SPLIT)) == ["Alder", "mahogany", "zinc"]


def test_the_two_scopes_keep_separate_lists(isolated_settings: Path) -> None:
    # A split border and a composite border are different decisions.
    settings.save_preset(settings.SPLIT, "Mine", pipeline.DEFAULT_STYLE)

    assert "Mine" in settings.load_presets(settings.SPLIT)
    assert "Mine" not in settings.load_presets(settings.COMPOSE)


def test_saving_under_an_existing_name_replaces_it(isolated_settings: Path) -> None:
    settings.save_preset(settings.SPLIT, "Mine", pipeline.DEFAULT_STYLE)
    wider = pipeline.FrameStyle(border_percent=20.0)
    settings.save_preset(settings.SPLIT, "Mine", wider)

    presets = settings.load_presets(settings.SPLIT)
    assert len(presets) == 1
    assert presets["Mine"] == wider


def test_deleting_removes_only_that_preset(isolated_settings: Path) -> None:
    settings.save_preset(settings.SPLIT, "Keep", pipeline.DEFAULT_STYLE)
    settings.save_preset(settings.SPLIT, "Drop", pipeline.DEFAULT_STYLE)

    settings.delete_preset(settings.SPLIT, "Drop")

    assert list(settings.load_presets(settings.SPLIT)) == ["Keep"]


def test_deleting_something_that_is_not_there_is_quiet(isolated_settings: Path) -> None:
    settings.delete_preset(settings.SPLIT, "Never existed")


def test_a_malformed_preset_is_dropped_without_taking_its_neighbours(
    isolated_settings: Path,
) -> None:
    # Losing four good presets over one bad one would be worse than the bug,
    # which is why this does not fall back whole the way load_style does.
    settings.save_preset(settings.SPLIT, "Good", pipeline.DEFAULT_STYLE)
    settings.save_preset(settings.SPLIT, "Bad", pipeline.DEFAULT_STYLE)
    store = settings._store()
    store.setValue(f"{settings.SPLIT}/presets/Bad/border_colour", "not a colour")
    store.sync()

    presets = settings.load_presets(settings.SPLIT)

    assert list(presets) == ["Good"]


def test_a_name_is_trimmed_and_bounded() -> None:
    assert settings.clean_name("  Warm white  ") == "Warm white"
    assert len(settings.clean_name("x" * 100)) == settings.MAX_NAME


def test_an_empty_name_is_refused() -> None:
    with pytest.raises(ValueError, match="name"):
        settings.clean_name("   ")


def test_seeding_puts_the_built_ins_in(isolated_settings: Path) -> None:
    settings.seed_presets()

    for scope in (settings.SPLIT, settings.COMPOSE):
        assert set(settings.load_presets(scope)) == set(settings.BUILT_INS[scope])


def test_a_deleted_built_in_stays_deleted(isolated_settings: Path) -> None:
    # Seeding once and then leaving them alone is what makes a built-in an
    # ordinary preset rather than furniture.
    settings.seed_presets()
    settings.delete_preset(settings.SPLIT, "Gallery")

    settings.seed_presets()

    assert "Gallery" not in settings.load_presets(settings.SPLIT)


def test_an_edited_built_in_is_not_put_back(isolated_settings: Path) -> None:
    settings.seed_presets()
    mine = pipeline.FrameStyle(border_percent=33.0)
    settings.save_preset(settings.SPLIT, "Gallery", mine)

    settings.seed_presets()

    assert settings.load_presets(settings.SPLIT)["Gallery"] == mine


def test_the_split_built_ins_carry_no_gap_decision(isolated_settings: Path) -> None:
    # Split has no gap to set, so a split preset must not smuggle one in.
    for style in settings.BUILT_INS[settings.SPLIT].values():
        assert style.gutter_percent == pipeline.DEFAULT_STYLE.gutter_percent
        assert style.gutter_colour == pipeline.DEFAULT_STYLE.gutter_colour
```

The file already imports `pytest`, `Path`, `settings` and `pipeline`; add whatever is missing.

- [x] **Step 2: Run the tests to verify they fail**

Run: `mise exec -- uv run pytest tests/test_gui_settings.py -v`
Expected: FAIL with `AttributeError: module 'maskingframe.gui.settings' has no attribute 'load_presets'`.

- [x] **Step 3: Implement**

Add to `settings.py`, after `save_style`:

```python
MAX_NAME = 40
"""How long a preset's name may be.

Long enough for a description, short enough that the combobox in a 320px
rail does not have to elide every entry.
"""

_SEEDED = "presets_seeded"
"""Records that the built-ins have been offered once.

Offered, not maintained: after the first run they are ordinary presets, so
deleting one keeps it deleted and editing one keeps the edit. The cost is
that a preset added in a later release will not appear for an existing
install -- accepted, because the alternative is a tombstone list and two
kinds of preset the interface then has to tell apart.
"""

BUILT_INS: dict[str, dict[str, pipeline.FrameStyle]] = {
    SPLIT: {
        "Plain white": pipeline.FrameStyle(),
        "Gallery": pipeline.FrameStyle(border_percent=18.0),
        "Black surround": pipeline.FrameStyle(border_colour="#14171a"),
    },
    COMPOSE: {
        "Plain white": pipeline.FrameStyle(),
        "Gallery": pipeline.FrameStyle(border_percent=18.0),
        "Black surround": pipeline.FrameStyle(
            border_colour="#14171a", gutter_colour="#14171a"
        ),
    },
}
"""A few to start from, one set per tab.

Each carries only what its own tab can show: the split entries leave the
gap at its default because Split has no gap control, and neither touches
`border_detail_frames`, which is a decision about a particular carousel
rather than about a look.
"""


def clean_name(name: str) -> str:
    """The name as it will be stored. Raises if there is nothing left of it."""
    cleaned = name.strip()[:MAX_NAME].strip()
    if not cleaned:
        raise ValueError("a preset needs a name")
    return cleaned


def _preset_key(scope: str, name: str) -> str:
    return f"{scope}/presets/{name}"


def load_presets(scope: str) -> dict[str, pipeline.FrameStyle]:
    """Every stored preset for this scope, alphabetically.

    A malformed preset is dropped on its own rather than the whole list
    falling back the way `load_style` does. Half a remembered style is more
    confusing than none, but losing four good presets over one bad one
    would be worse than the bug that wrote it.

    Sorted case-insensitively because the list grows: insertion order stops
    being findable once there are more than a handful.
    """
    store = _store()
    store.beginGroup(f"{scope}/presets")
    names = store.childGroups()
    store.endGroup()

    presets: dict[str, pipeline.FrameStyle] = {}
    default = pipeline.DEFAULT_STYLE
    for name in sorted(names, key=str.casefold):
        key = _preset_key(scope, name)
        try:
            presets[name] = pipeline.FrameStyle(
                border_percent=_percent(store, f"{key}/border_percent", default.border_percent),
                border_colour=str(store.value(f"{key}/border_colour", default.border_colour)),
                gutter_percent=_percent(store, f"{key}/gutter_percent", default.gutter_percent),
                gutter_colour=str(store.value(f"{key}/gutter_colour", default.gutter_colour)),
                border_detail_frames=_flag(store, f"{key}/border_detail_frames"),
            )
        except (TypeError, ValueError):
            continue
    return presets


def save_preset(scope: str, name: str, style: pipeline.FrameStyle) -> None:
    """Store one preset, replacing any of the same name."""
    key = _preset_key(scope, clean_name(name))
    store = _store()
    store.setValue(f"{key}/border_percent", style.border_percent)
    store.setValue(f"{key}/border_colour", style.border_colour)
    store.setValue(f"{key}/gutter_percent", style.gutter_percent)
    store.setValue(f"{key}/gutter_colour", style.gutter_colour)
    store.setValue(f"{key}/border_detail_frames", style.border_detail_frames)
    store.sync()


def delete_preset(scope: str, name: str) -> None:
    """Remove one preset. Quiet if it was not there."""
    store = _store()
    store.remove(_preset_key(scope, name.strip()))
    store.sync()


def seed_presets() -> None:
    """Offer the built-ins, once ever.

    Guarded by a flag rather than by whether the list is empty: a user who
    deletes all three has said what they think of them, and putting them
    back on the next launch would be the application arguing.
    """
    store = _store()
    if _flag(store, _SEEDED):
        return
    for scope, presets in BUILT_INS.items():
        for name, style in presets.items():
            save_preset(scope, name, style)
    store.setValue(_SEEDED, True)
    store.sync()
```

Call `seed_presets()` from `configure()`, so it happens once at startup beside the other one-time settings work.

- [x] **Step 4: Run the tests to verify they pass**

Run: `mise exec -- uv run pytest tests/test_gui_settings.py -v`
Expected: PASS, including every test already in the file.

- [x] **Step 5: Run the full gate and commit**

```bash
mise run check
git add src/maskingframe/gui/settings.py tests/test_gui_settings.py
git commit -m "feat(gui): store named border presets"
```

---

### Task 2: The preset row

A widget that owns the naming rules and the button's wording, and nothing else. It never touches `QSettings`.

**Files:**
- Modify: `src/maskingframe/gui/shell.py`
- Test: `tests/test_gui_shell.py`

**Interfaces:**
- Consumes: `theme`, `Combo` (the hand-drawn combobox in `shell.py`), `pipeline.FrameStyle`.
- Produces:
  - `shell.EDITED_SUFFIX = " (edited)"`
  - `class PresetRow(QWidget)` with:
    - `chosen = Signal(str)` — a preset was picked from the list
    - `saved = Signal(str)` — save or update was asked for, under this cleaned name
    - `deleted = Signal(str)` — delete was asked for, for this name
    - `set_names(names: Sequence[str]) -> None` — replace the list, silently
    - `set_current(name: str) -> None` — show this name, silently, unmarked
    - `mark_edited() -> None` — append the suffix if a name is shown
    - `current_name() -> str` — the shown name with any suffix stripped
    - `save_button: QPushButton`, `delete_button: QPushButton`, `box: Combo`

- [x] **Step 1: Write the failing tests**

Add to `tests/test_gui_shell.py`:

```python
def test_the_row_lists_the_names_it_is_given(qtbot: QtBot) -> None:
    row = shell.PresetRow()
    qtbot.addWidget(row)

    row.set_names(["Alder", "Gallery"])

    assert [row.box.itemText(i) for i in range(row.box.count())] == ["Alder", "Gallery"]


def test_setting_the_list_says_nothing(qtbot: QtBot) -> None:
    # Filling the list is not a user choice, and a tab that saved on
    # `chosen` would otherwise write back what it has just read.
    row = shell.PresetRow()
    qtbot.addWidget(row)
    with qtbot.assertNotEmitted(row.chosen):
        row.set_names(["Alder", "Gallery"])
        row.set_current("Gallery")


def test_choosing_from_the_list_announces_it(qtbot: QtBot) -> None:
    row = shell.PresetRow()
    qtbot.addWidget(row)
    row.set_names(["Alder", "Gallery"])

    with qtbot.waitSignal(row.chosen, timeout=1000) as blocker:
        row.box.setCurrentIndex(1)

    assert blocker.args == ["Gallery"]


def test_the_button_says_save_for_a_new_name_and_update_for_a_known_one(
    qtbot: QtBot,
) -> None:
    # This is what stands in for a confirmation dialog: it tells you which
    # you are about to do before you do it.
    row = shell.PresetRow()
    qtbot.addWidget(row)
    row.set_names(["Gallery"])

    row.box.setEditText("Gallery")
    assert row.save_button.text() == "Update"

    row.box.setEditText("Something else")
    assert row.save_button.text() == "Save"


def test_the_button_and_the_enter_key_do_the_same_thing(qtbot: QtBot) -> None:
    row = shell.PresetRow()
    qtbot.addWidget(row)

    row.box.setEditText("Warm white")
    with qtbot.waitSignal(row.saved, timeout=1000) as by_button:
        row.save_button.click()
    with qtbot.waitSignal(row.saved, timeout=1000) as by_key:
        qtbot.keyClick(row.box.lineEdit(), Qt.Key.Key_Return)

    assert by_button.args == by_key.args == ["Warm white"]


def test_saving_a_blank_name_does_nothing(qtbot: QtBot) -> None:
    row = shell.PresetRow()
    qtbot.addWidget(row)
    row.box.setEditText("   ")

    with qtbot.assertNotEmitted(row.saved):
        row.save_button.click()


def test_the_edited_marker_appears_and_never_reaches_a_name(qtbot: QtBot) -> None:
    row = shell.PresetRow()
    qtbot.addWidget(row)
    row.set_names(["Gallery"])
    row.set_current("Gallery")

    row.mark_edited()

    assert row.box.currentText() == "Gallery" + shell.EDITED_SUFFIX
    assert row.current_name() == "Gallery"
    with qtbot.waitSignal(row.saved, timeout=1000) as blocker:
        row.save_button.click()
    assert blocker.args == ["Gallery"]


def test_marking_twice_does_not_stack_the_suffix(qtbot: QtBot) -> None:
    row = shell.PresetRow()
    qtbot.addWidget(row)
    row.set_names(["Gallery"])
    row.set_current("Gallery")

    row.mark_edited()
    row.mark_edited()

    assert row.box.currentText() == "Gallery" + shell.EDITED_SUFFIX


def test_marking_an_empty_box_leaves_it_empty(qtbot: QtBot) -> None:
    # With no preset chosen there is nothing to have edited.
    row = shell.PresetRow()
    qtbot.addWidget(row)

    row.mark_edited()

    assert row.box.currentText() == ""


def test_setting_a_name_clears_the_marker(qtbot: QtBot) -> None:
    row = shell.PresetRow()
    qtbot.addWidget(row)
    row.set_names(["Gallery", "Alder"])
    row.set_current("Gallery")
    row.mark_edited()

    row.set_current("Alder")

    assert row.box.currentText() == "Alder"


def test_delete_is_available_only_for_a_name_that_exists(qtbot: QtBot) -> None:
    row = shell.PresetRow()
    qtbot.addWidget(row)
    row.set_names(["Gallery"])

    row.box.setEditText("Gallery")
    assert row.delete_button.isEnabled()

    row.box.setEditText("Never saved")
    assert not row.delete_button.isEnabled()


def test_deleting_announces_the_name(qtbot: QtBot) -> None:
    row = shell.PresetRow()
    qtbot.addWidget(row)
    row.set_names(["Gallery"])
    row.set_current("Gallery")
    row.mark_edited()

    with qtbot.waitSignal(row.deleted, timeout=1000) as blocker:
        row.delete_button.click()

    assert blocker.args == ["Gallery"]
```

Annotate `qtbot` input calls with `# type: ignore[no-untyped-call]` where mypy --strict requires it, matching the file's existing convention.

- [x] **Step 2: Run the tests to verify they fail**

Run: `mise exec -- uv run pytest tests/test_gui_shell.py -k preset -v`
Expected: FAIL with `AttributeError: module 'maskingframe.gui.shell' has no attribute 'PresetRow'`.

- [x] **Step 3: Implement**

Add to `shell.py`, above `BorderControls`:

```python
EDITED_SUFFIX = " (edited)"
"""Marks settings that started from a preset and have moved away from it.

Display only. It is stripped before a name is saved, matched or deleted, so
a preset can never end up called "Warm white (edited)"."""


class PresetRow(QWidget):
    """Pick a saved border, save the current one, or delete one.

    Owns the naming rules and the button's wording, and nothing else: it
    never touches `QSettings`, so a tab decides what a name means and where
    it is kept. That is the same split every other widget in this file
    makes -- the rail describes, the tab decides.
    """

    chosen = Signal(str)
    """A preset was picked from the list."""

    saved = Signal(str)
    """Save or update was asked for, under this cleaned name."""

    deleted = Signal(str)
    """Delete was asked for, for this name."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._quiet = False

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(theme.S)

        self.box = Combo()
        self.box.setEditable(True)
        self.box.setInsertPolicy(Combo.InsertPolicy.NoInsert)
        self.box.setAccessibleName("Border preset")
        line_edit = self.box.lineEdit()
        if line_edit is not None:
            # `Combo` draws its own chevron over its right-hand end, because
            # flattening the field takes Qt's themed arrow with it. An
            # editable combo fills that same space with a line edit, so a
            # long name would run underneath the mark. Reserve the room the
            # chevron actually occupies.
            line_edit.setTextMargins(0, 0, Combo.ARROW + theme.M, 0)
        self.box.activated.connect(self._on_activated)
        self.box.editTextChanged.connect(self._on_text_changed)
        line = self.box.lineEdit()
        if line is not None:
            line.returnPressed.connect(self._on_save)

        # Chrome, not the primary action: chinagraph is for marking up, and
        # a second filled block of it beside the one that writes to disk
        # would cost that one its primacy.
        self.save_button = QPushButton("Save")
        self.save_button.setObjectName("Secondary")
        self.save_button.clicked.connect(self._on_save)

        self.delete_button = QPushButton("x")
        self.delete_button.setObjectName("Secondary")
        self.delete_button.setAccessibleName("Delete this preset")
        self.delete_button.clicked.connect(self._on_delete)

        row.addWidget(self.box, 1)
        row.addWidget(self.save_button)
        row.addWidget(self.delete_button)
        self._sync_buttons()

    # --- what it is showing -------------------------------------------------

    def set_names(self, names: Sequence[str]) -> None:
        """Replace the list. Emits nothing."""
        current = self.box.currentText()
        self._quiet = True
        try:
            self.box.clear()
            self.box.addItems(list(names))
            self.box.setEditText(current)
        finally:
            self._quiet = False
        self._sync_buttons()

    def set_current(self, name: str) -> None:
        """Show this name, unmarked. Emits nothing."""
        self._quiet = True
        try:
            self.box.setEditText(name)
        finally:
            self._quiet = False
        self._sync_buttons()

    def current_name(self) -> str:
        """The shown name, with any marker stripped."""
        text = self.box.currentText()
        if text.endswith(EDITED_SUFFIX):
            text = text[: -len(EDITED_SUFFIX)]
        return text.strip()

    def mark_edited(self) -> None:
        """Say the settings have moved away from the preset they started as.

        Nothing happens with an empty box: with no preset chosen there is
        nothing to have edited.
        """
        name = self.current_name()
        if not name:
            return
        self.set_current(name + EDITED_SUFFIX)

    # --- acting -------------------------------------------------------------

    def _names(self) -> list[str]:
        return [self.box.itemText(index) for index in range(self.box.count())]

    def _sync_buttons(self) -> None:
        """The one place the two buttons' state is decided.

        The button's wording is what stands in for a confirmation dialog:
        it says whether a save will add or replace before it is pressed.
        """
        name = self.current_name()
        known = name in self._names()
        self.save_button.setText("Update" if known else "Save")
        self.save_button.setEnabled(bool(name))
        self.delete_button.setEnabled(known)

    def _on_text_changed(self, _text: str) -> None:
        self._sync_buttons()

    def _on_activated(self, index: int) -> None:
        if self._quiet or not 0 <= index < self.box.count():
            return
        name = self.box.itemText(index)
        self.set_current(name)
        self.chosen.emit(name)

    def _on_save(self) -> None:
        name = self.current_name()
        if not name:
            return
        self.set_current(name)
        self.saved.emit(name)

    def _on_delete(self) -> None:
        name = self.current_name()
        if name not in self._names():
            return
        self.deleted.emit(name)
```

Add `QComboBox`-adjacent imports as needed — `Sequence` from `collections.abc`, and `QPushButton` if `shell.py` does not already import it.

- [x] **Step 4: Run the tests to verify they pass**

Run: `mise exec -- uv run pytest tests/test_gui_shell.py -v`
Expected: PASS, including every test already in the file.

- [x] **Step 5: Run the full gate and commit**

```bash
mise run check
git add src/maskingframe/gui/shell.py tests/test_gui_shell.py
git commit -m "feat(gui): add the border preset row"
```

---

### Task 3: Wire it into both tabs

**Files:**
- Modify: `src/maskingframe/gui/shell.py` (`BorderControls`)
- Modify: `src/maskingframe/gui/split_tab.py`, `src/maskingframe/gui/compose_tab.py`
- Test: `tests/test_split_tab.py`, `tests/test_compose_tab.py`

**Interfaces:**
- Consumes: `PresetRow` (Task 2); `settings.load_presets`, `save_preset`, `delete_preset` (Task 1); the existing `BorderControls.frame_style()`, `set_style()`, `style_changed`, `style_settled`.
- Produces: `BorderControls.presets: PresetRow`, and `BorderControls.apply_preset(style)` — adopts a style and settles once, as a user action rather than a restore.

- [x] **Step 1: Write the failing tests**

Add to `tests/test_split_tab.py`:

```python
def test_choosing_a_preset_applies_the_whole_style(
    qtbot: QtBot, isolated_settings: Path
) -> None:
    settings.save_preset(
        settings.SPLIT,
        "Wide",
        pipeline.FrameStyle(border_percent=20.0, border_colour="#102030"),
    )
    tab = SplitTab()
    qtbot.addWidget(tab)
    tab.border_controls.reload_presets()

    tab.border_controls.presets.chosen.emit("Wide")

    style = tab.border_controls.frame_style()
    assert style.border_percent == 20.0
    assert style.border_colour == "#102030"


def test_choosing_a_preset_settles_once(qtbot: QtBot, isolated_settings: Path) -> None:
    # A preset is a user action, so the preview re-renders -- once, the way
    # a slider release does, not once per field it moved.
    settings.save_preset(settings.SPLIT, "Wide", pipeline.FrameStyle(border_percent=20.0))
    tab = SplitTab()
    qtbot.addWidget(tab)
    tab.border_controls.reload_presets()
    settled: list[object] = []
    tab.border_controls.style_settled.connect(settled.append)

    tab.border_controls.presets.chosen.emit("Wide")

    assert len(settled) == 1


def test_saving_a_preset_stores_what_the_rail_shows(
    qtbot: QtBot, isolated_settings: Path
) -> None:
    tab = SplitTab()
    qtbot.addWidget(tab)
    tab.border_controls.border_slider.setValue(15.0)

    tab.border_controls.presets.saved.emit("Mine")

    assert settings.load_presets(settings.SPLIT)["Mine"].border_percent == 15.0


def test_deleting_a_preset_takes_it_out_of_the_list(
    qtbot: QtBot, isolated_settings: Path
) -> None:
    settings.save_preset(settings.SPLIT, "Mine", pipeline.DEFAULT_STYLE)
    tab = SplitTab()
    qtbot.addWidget(tab)
    tab.border_controls.reload_presets()

    tab.border_controls.presets.deleted.emit("Mine")

    assert "Mine" not in settings.load_presets(settings.SPLIT)
    assert "Mine" not in [
        tab.border_controls.presets.box.itemText(i)
        for i in range(tab.border_controls.presets.box.count())
    ]


def test_moving_a_control_marks_the_preset_as_edited(
    qtbot: QtBot, isolated_settings: Path
) -> None:
    settings.save_preset(settings.SPLIT, "Wide", pipeline.FrameStyle(border_percent=20.0))
    tab = SplitTab()
    qtbot.addWidget(tab)
    tab.border_controls.reload_presets()
    tab.border_controls.presets.chosen.emit("Wide")

    tab.border_controls.border_slider.setValue(11.0)

    assert tab.border_controls.presets.box.currentText().endswith(shell.EDITED_SUFFIX)
```

Add the matching pair to `tests/test_compose_tab.py`, against `settings.COMPOSE` and `ComposeTab`, covering that a preset applies and that the tab sees only its own scope:

```python
def test_compose_sees_only_its_own_presets(qtbot: QtBot, isolated_settings: Path) -> None:
    # A split border and a composite border are different decisions, so the
    # two lists never mix.
    settings.save_preset(settings.SPLIT, "Split only", pipeline.DEFAULT_STYLE)
    settings.save_preset(settings.COMPOSE, "Compose only", pipeline.DEFAULT_STYLE)
    tab = ComposeTab()
    qtbot.addWidget(tab)
    tab.border_controls.reload_presets()

    names = [
        tab.border_controls.presets.box.itemText(i)
        for i in range(tab.border_controls.presets.box.count())
    ]
    assert "Compose only" in names
    assert "Split only" not in names


def test_choosing_a_compose_preset_applies_the_gap(
    qtbot: QtBot, isolated_settings: Path
) -> None:
    settings.save_preset(
        settings.COMPOSE,
        "Wide gap",
        pipeline.FrameStyle(gutter_percent=9.0, gutter_colour="#102030"),
    )
    tab = ComposeTab()
    qtbot.addWidget(tab)
    tab.border_controls.reload_presets()

    tab.border_controls.presets.chosen.emit("Wide gap")

    style = tab.border_controls.frame_style()
    assert style.gutter_percent == 9.0
    assert style.gutter_colour == "#102030"
```

Both files must import `settings` and use the `isolated_settings` fixture on every test that touches the store.

- [x] **Step 2: Run the tests to verify they fail**

Run: `mise exec -- uv run pytest tests/test_split_tab.py tests/test_compose_tab.py -k preset -v`
Expected: FAIL with `AttributeError: 'BorderControls' object has no attribute 'presets'`.

- [x] **Step 3: Put the row into `BorderControls`**

`BorderControls` takes a `scope` so it can load and store its own list. It is the one place the two tabs already share, so putting the wiring here rather than in each tab keeps them from drifting apart — which is the reason `BorderControls` exists.

In `__init__`, add a **`scope: str = settings.SPLIT` keyword parameter with a default**. Thirteen existing tests in `tests/test_gui_shell.py` construct `BorderControls(show_gutter=…, show_detail_toggle=…)` with no scope; a required parameter would break all of them for no gain. The default is safe because construction alone neither reads nor writes the store — `reload_presets()` is called explicitly, and saving only happens on a user action.

Build the row directly under the section heading, above the width slider — you pick the look, then adjust it:

```python
        column.addWidget(section("Border"))
        column.addSpacing(theme.S)
        self._scope = scope
        self.presets = PresetRow()
        self.presets.chosen.connect(self._on_preset_chosen)
        self.presets.saved.connect(self._on_preset_saved)
        self.presets.deleted.connect(self._on_preset_deleted)
        column.addWidget(self.presets)
        column.addSpacing(theme.S)
```

Add the handlers beside `_emit` and `_settle`:

```python
    def reload_presets(self) -> None:
        """Re-read the stored list. GUI thread only."""
        self._presets = settings.load_presets(self._scope)
        self.presets.set_names(list(self._presets))

    def apply_preset(self, style: pipeline.FrameStyle) -> None:
        """Adopt a style as a user action, not as a restore.

        `set_style` is silent because restoring stored state must not be
        written straight back. Choosing a preset is the opposite: the user
        did it on purpose, and the preview should follow -- once, the way a
        slider release does, rather than once per field it moved.
        """
        self.set_style(style)
        self._settle()

    def _on_preset_chosen(self, name: str) -> None:
        style = self._presets.get(name)
        if style is None:
            return
        self.apply_preset(style)

    def _on_preset_saved(self, name: str) -> None:
        settings.save_preset(self._scope, name, self.frame_style())
        self.reload_presets()
        self.presets.set_current(name)

    def _on_preset_deleted(self, name: str) -> None:
        settings.delete_preset(self._scope, name)
        self.reload_presets()
        self.presets.set_current("")
```

In `_emit`, mark the row after emitting, so a moved control says the settings are no longer the preset they started as:

```python
    def _emit(self, *_args: object) -> None:
        if self._quiet:
            return
        self.presets.mark_edited()
        self.style_changed.emit(self.frame_style())
```

Add `self._presets: dict[str, pipeline.FrameStyle] = {}` to `__init__` before the row is built, and `from maskingframe.gui import settings` to `shell.py`'s imports.

**Watch the import direction:** `settings.py` imports `pipeline`, and `shell.py` will now import `settings`. Confirm this introduces no cycle — if `settings.py` imports anything from `shell.py`, stop and report rather than working around it.

- [x] **Step 4: Wire both tabs**

In `split_tab.py`, pass the scope and load the list where the controls are built:

```python
        self.border_controls = shell.BorderControls(
            scope=settings.SPLIT, show_gutter=False, show_detail_toggle=True
        )
        self.border_controls.reload_presets()
        self.border_controls.set_style(settings.load_style(settings.SPLIT))
```

Do the same in `compose_tab.py` with `settings.COMPOSE` and its own `show_gutter`/`show_detail_toggle` values — read the existing call and keep them as they are.

`set_style` stays after `reload_presets` so the restored style does not mark a list that has not been filled yet.

- [x] **Step 5: Run the tests to verify they pass**

Run: `mise exec -- uv run pytest tests/test_split_tab.py tests/test_compose_tab.py tests/test_gui_shell.py -v`
Expected: PASS, including every test already in those files.

- [x] **Step 6: Look at it**

```bash
QT_QPA_PLATFORM=offscreen mise exec -- uv run python - <<'PY'
from PySide6.QtWidgets import QApplication
app = QApplication([])
from maskingframe.gui import settings
settings.seed_presets()
from maskingframe.gui.app import MainWindow
w = MainWindow(); w.resize(1280, 1000); w.show()
app.processEvents()
row = w.split.border_controls.presets
print("names:", [row.box.itemText(i) for i in range(row.box.count())])
print("button:", row.save_button.text(), "| delete enabled:", row.delete_button.isEnabled())
w.grab().save("/tmp/presets.png")
PY
```

Open `/tmp/presets.png`. Confirm the row fits the 320px rail without the combo or either button being clipped, that the buttons read as chrome rather than competing with the primary action, and that the BORDER section still reads top to bottom as one thing. Report what you saw.

- [x] **Step 7: Run the full gate and commit**

```bash
mise run check
git add src/maskingframe/gui/shell.py src/maskingframe/gui/split_tab.py src/maskingframe/gui/compose_tab.py tests/
git commit -m "feat(gui): choose a border by name"
```

---

### Task 4: Documentation

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Record the preset model**

In the "Remembering the border" section, after the paragraph about Split and Compose storing their styles under separate scopes, add:

```markdown
A border can also be saved under a name. Presets follow the scopes: Split and
Compose keep separate lists, and a preset carries only what its own tab can
show — the split entries leave the gap at its default, because Split has no gap
control.

A stored preset is untrusted input like a stored style, but the failure rule
differs on purpose. `load_style` falls back whole, because half a remembered
style is more confusing than none. `load_presets` drops a malformed preset on
its own, because losing four good presets over one bad one would be worse than
the bug that wrote it.

Three built-ins are seeded per scope on first run and are ordinary presets
afterwards: delete one and it stays deleted, edit one and the edit stands. The
cost is that a preset added in a later release will not reach an existing
install — accepted against a tombstone list and two kinds of preset the
interface would then have to tell apart.

`shell.PresetRow` owns the naming rules and the button's wording and never
touches `QSettings`; `BorderControls` holds the scope and does the storing. The
button reads Save for a new name and Update for one that exists — that is what
stands in for a confirmation dialog, and it says which you are about to do
before you do it. `shell.EDITED_SUFFIX` marks settings that have moved away
from the preset they started as, and is stripped before any name is saved,
matched or deleted.
```

- [ ] **Step 2: Run the full gate and commit**

```bash
mise run check
git add CLAUDE.md
git commit -m "docs: record how border presets are stored"
```

---

## Verification

- [ ] `mise run check` passes on a clean tree.
- [ ] Opening the GUI shows three presets in each tab's BORDER section; choosing one moves the controls and re-renders the preview once.
- [ ] Typing a new name and pressing Enter saves it; the button reads Save for a new name and Update for an existing one.
- [ ] Moving a control after choosing a preset appends `(edited)`, and saving then stores under the clean name.
- [ ] Deleting a preset removes it from the list, and it is still gone after a restart.
- [ ] A Split preset does not appear in Compose.
- [ ] `grep -rn "QSettings(" src/maskingframe/gui/ | grep -v settings.py` returns nothing.
