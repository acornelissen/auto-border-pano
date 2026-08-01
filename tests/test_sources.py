"""Tests for the Qt numbered sources list.

What these protect is the contract the Compose tab is written against --
`set_items`, `select`, `selected_index` and exactly one `selection_changed`
per actual change -- plus the two promises the design makes about the widget:
that the rows are numbered frames, and that an empty list says what to do
rather than showing a box.

The rows are drawn by a delegate rather than held as item text, so the render
is checked by painting the widget into a `QPixmap` and by reading the
accessible text Qt exposes for each row. Both would catch a row that failed
to render; neither pins the pixel positions the design is free to move.
"""

from collections.abc import Iterator

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from pytestqt.qtbot import QtBot

from maskingframe.gui import sources


@pytest.fixture
def built(qtbot: QtBot) -> Iterator[sources.SourcesList]:
    widget = sources.SourcesList()
    qtbot.addWidget(widget)
    widget.resize(340, 200)
    yield widget


def _rows(widget: sources.SourcesList) -> list[str]:
    """The accessible text of every row -- number, name and dimensions."""
    return [
        str(widget.item(index).data(Qt.ItemDataRole.AccessibleTextRole))
        for index in range(widget.model().rowCount())
    ]


def _paint(widget: sources.SourcesList) -> None:
    """Render the widget, so a delegate that raises fails a test.

    Nothing else here exercises `paint`, and a broken delegate is otherwise
    invisible: Qt swallows nothing, but no test would ever trigger it.
    """
    pixmap = QPixmap(widget.size())
    widget.render(pixmap)


def _items(count: int) -> list[sources.Source]:
    return [sources.Source(f"/tmp/source{index}.jpg", (4000, 1700)) for index in range(count)]


def test_the_empty_state_is_there_at_construction_with_no_call(
    built: sources.SourcesList,
) -> None:
    """The Listbox's empty state was a bare black box that told you nothing."""
    assert built.count == 0
    assert built.selected_index is None
    assert built.accessibleDescription() == sources.EMPTY_CAPTION
    _paint(built)


def test_a_row_carries_its_number_its_name_and_its_dimensions(
    built: sources.SourcesList,
) -> None:
    built.set_items([sources.Source("/photos/horizons3-hp5-4.jpg", (4000, 1700))])

    assert _rows(built) == ["1. horizons3-hp5-4.jpg, 4000 × 1700"]  # noqa: RUF001
    assert built.items[0].dimensions == "4000 × 1700"  # noqa: RUF001
    assert built.accessibleDescription() == ""
    _paint(built)


def test_the_numbers_renumber_when_the_order_changes(built: sources.SourcesList) -> None:
    first = sources.Source("/photos/a.jpg", (10, 10))
    second = sources.Source("/photos/b.jpg", (10, 10))
    built.set_items([first, second])

    built.set_items([second, first])

    assert _rows(built) == ["1. b.jpg, 10 × 10", "2. a.jpg, 10 × 10"]  # noqa: RUF001
    assert built.items == (second, first)


def test_a_row_renders_before_its_dimensions_have_been_read(
    built: sources.SourcesList,
) -> None:
    """Headers are read off the GUI thread, so a row exists before it knows
    its own size."""
    built.set_items([sources.Source("/photos/horizons3-hp5-4.jpg")])

    assert _rows(built) == [f"1. horizons3-hp5-4.jpg, {sources.PENDING_DIMENSIONS}"]
    _paint(built)


def test_the_height_follows_the_rows_rather_than_a_fixed_four(
    built: sources.SourcesList,
) -> None:
    """The Listbox was `height=4` for a list capped at 3, so one row was
    always dead space."""
    built.set_items(_items(2))
    two = built.height()

    built.set_items(_items(3))

    assert built.height() > two
    assert built.height() == 3 * sources.ROW_HEIGHT + 2 * sources.BORDER


def test_there_is_never_a_scrollbar(built: sources.SourcesList) -> None:
    """Three rows, hard capped. Nothing to scroll and nothing to virtualise."""
    built.set_items(_items(3))

    assert not built.verticalScrollBar().isVisible()
    assert not built.horizontalScrollBar().isVisible()


def test_clicking_a_row_selects_it_and_emits(qtbot: QtBot, built: sources.SourcesList) -> None:
    built.set_items(_items(3))
    middle = built.visualItemRect(built.item(1)).center()

    with qtbot.waitSignal(built.selection_changed) as blocker:
        qtbot.mouseClick(built.viewport(), Qt.MouseButton.LeftButton, pos=middle)  # type: ignore[no-untyped-call]

    assert built.selected_index == 1
    assert blocker.args == [1]


def test_the_arrow_keys_move_the_selection(qtbot: QtBot, built: sources.SourcesList) -> None:
    """Keyboard operability was the tkinter version's whole accessibility
    story; here it is `QListWidget`'s, and it still has to work."""
    built.set_items(_items(3))
    built.select(0)
    built.setFocus()

    qtbot.keyClick(built, Qt.Key.Key_Down)  # type: ignore[no-untyped-call]
    assert built.selected_index == 1
    qtbot.keyClick(built, Qt.Key.Key_Down)  # type: ignore[no-untyped-call]
    assert built.selected_index == 2
    qtbot.keyClick(built, Qt.Key.Key_Up)  # type: ignore[no-untyped-call]
    assert built.selected_index == 1


def test_the_arrow_keys_stop_at_the_ends(qtbot: QtBot, built: sources.SourcesList) -> None:
    """Clamped, not wrapped: wrapping a list whose order is its meaning is
    disorienting, and three rows have obvious ends."""
    built.set_items(_items(2))
    built.select(0)
    built.setFocus()

    for _ in range(3):
        qtbot.keyClick(built, Qt.Key.Key_Up)  # type: ignore[no-untyped-call]
    assert built.selected_index == 0

    for _ in range(5):
        qtbot.keyClick(built, Qt.Key.Key_Down)  # type: ignore[no-untyped-call]
    assert built.selected_index == 1


def test_a_first_arrow_press_lands_on_the_near_end(
    qtbot: QtBot, built: sources.SourcesList
) -> None:
    built.set_items(_items(3))
    built.setFocus()

    qtbot.keyClick(built, Qt.Key.Key_Up)  # type: ignore[no-untyped-call]

    assert built.selected_index == 2


def test_the_arrows_do_nothing_on_an_empty_list(qtbot: QtBot, built: sources.SourcesList) -> None:
    built.setFocus()

    qtbot.keyClick(built, Qt.Key.Key_Down)  # type: ignore[no-untyped-call]
    qtbot.keyClick(built, Qt.Key.Key_Up)  # type: ignore[no-untyped-call]

    assert built.selected_index is None


def test_the_widget_takes_focus(built: sources.SourcesList) -> None:
    assert built.focusPolicy() == Qt.FocusPolicy.StrongFocus


def test_the_selection_survives_a_reorder(qtbot: QtBot, built: sources.SourcesList) -> None:
    """A move is a `set_items` at the same length: the user stays on the row
    they just moved."""
    first = sources.Source("/photos/a.jpg", (10, 10))
    second = sources.Source("/photos/b.jpg", (10, 10))
    built.set_items([first, second])
    built.select(1)

    seen: list[int | None] = []
    built.selection_changed.connect(seen.append)
    built.set_items([second, first])

    assert built.selected_index == 1
    assert seen == []


def test_the_selection_is_clamped_when_the_last_row_goes(
    built: sources.SourcesList,
) -> None:
    built.set_items(_items(3))
    built.select(2)

    seen: list[int | None] = []
    built.selection_changed.connect(seen.append)
    built.set_items(_items(2))

    assert built.selected_index == 1
    assert seen == [1]


def test_the_selection_clears_when_the_list_empties(built: sources.SourcesList) -> None:
    built.set_items(_items(2))
    built.select(1)

    seen: list[int | None] = []
    built.selection_changed.connect(seen.append)
    built.set_items([])

    assert built.selected_index is None
    assert seen == [None]
    assert built.accessibleDescription() == sources.EMPTY_CAPTION


def test_selecting_out_of_range_clears_rather_than_raising(
    built: sources.SourcesList,
) -> None:
    built.set_items(_items(2))
    built.select(1)

    built.select(9)

    assert built.selected_index is None


def test_a_programmatic_select_emits(qtbot: QtBot, built: sources.SourcesList) -> None:
    """The Compose tab drives its Up/Down/Remove states off this, and it
    needs the programmatic moves as much as the clicks."""
    built.set_items(_items(2))

    with qtbot.waitSignal(built.selection_changed) as blocker:
        built.select(1)

    assert blocker.args == [1]


def test_reselecting_the_same_row_does_not_fire_again(built: sources.SourcesList) -> None:
    built.set_items(_items(2))
    seen: list[int | None] = []
    built.selection_changed.connect(seen.append)

    built.select(1)
    built.select(1)

    assert seen == [1]


def test_clearing_an_already_clear_selection_does_not_fire(
    built: sources.SourcesList,
) -> None:
    built.set_items(_items(2))
    seen: list[int | None] = []
    built.selection_changed.connect(seen.append)

    built.select(None)

    assert seen == []


def test_the_items_tuple_cannot_be_mutated_behind_the_widget(
    built: sources.SourcesList,
) -> None:
    given = _items(2)
    built.set_items(given)

    given.append(sources.Source("/photos/c.jpg"))

    assert built.count == 2
    assert isinstance(built.items, tuple)


def test_a_long_filename_still_renders(built: sources.SourcesList) -> None:
    """Elided from the front, because these names share a long prefix and
    differ in their last few characters."""
    built.set_items([sources.Source("/photos/" + "horizons-" * 12 + ".jpg", (10, 10))])

    _paint(built)
    assert built.count == 1
