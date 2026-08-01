"""Tests for the ribbon: the whole panorama with a window per detail frame.

Offscreen, like every other widget test here -- `conftest` sets
QT_QPA_PLATFORM before Qt is imported.
"""

from collections.abc import Sequence

import pytest
from PySide6.QtCore import QEvent, QPoint, QRect, Qt
from PySide6.QtGui import QFocusEvent
from pytestqt.qtbot import QtBot

from maskingframe import geometry
from maskingframe.gui.ribbon import MARGIN, RIBBON_HEIGHT, FrameRibbon, _uncovered
from tests import conftest

# A 1000x400 source at 1:1 gives a 400px frame -- 0.4 of the width, the
# window fraction `build` sets -- so the ribbon's picture and this ratio
# describe the same plan, and a frame may travel to 0.6.
SOURCE = (1000, 400)
RATIO = geometry.RATIOS["1:1"]


def build(qtbot: QtBot, positions: Sequence[float] = (0.0, 0.6)) -> FrameRibbon:
    ribbon = FrameRibbon()
    qtbot.addWidget(ribbon)
    ribbon.resize(600, RIBBON_HEIGHT)
    ribbon.set_source(conftest.synthetic_panorama(*SOURCE))
    ribbon.set_plan(positions, 0.4)
    return ribbon


def wire(ribbon: FrameRibbon) -> None:
    """Stand in for the Split tab: apply the shared rule and hand it back.

    The ribbon asks for a move and draws what it is given; the ordering rule
    lives in `geometry` so the contact strip's drag obeys the same one.
    """

    def moved(index: int, wanted: float) -> None:
        ribbon.set_plan(
            geometry.move_position(ribbon.positions(), index, wanted, *SOURCE, RATIO), 0.4
        )

    ribbon.frame_moved.connect(moved)


def test_the_picture_is_letterboxed_not_cropped(qtbot: QtBot) -> None:
    ribbon = build(qtbot)
    rect = ribbon.picture_rect()
    # A 2.5:1 picture in a 600-wide, fixed-height ribbon fits on width and
    # leaves space above and below rather than losing the top and bottom.
    assert rect.width() / rect.height() == pytest.approx(2.5, rel=0.02)
    assert rect.width() <= 600
    assert rect.height() <= RIBBON_HEIGHT


def test_one_window_per_position(qtbot: QtBot) -> None:
    ribbon = build(qtbot, (0.0, 0.3, 0.6))
    assert len(ribbon.window_rects()) == 3


def test_a_window_sits_where_its_position_says(qtbot: QtBot) -> None:
    ribbon = build(qtbot, (0.0, 0.6))
    picture = ribbon.picture_rect()
    first, second = ribbon.window_rects()
    assert first.left() == picture.left()
    assert second.left() == pytest.approx(picture.left() + 0.6 * picture.width(), abs=2)
    assert first.width() == pytest.approx(0.4 * picture.width(), abs=2)


def test_set_plan_is_silent(qtbot: QtBot) -> None:
    ribbon = build(qtbot)
    with qtbot.assertNotEmitted(ribbon.frame_moved):
        ribbon.set_plan((0.1, 0.5), 0.4)


def test_dragging_a_window_moves_only_that_frame(qtbot: QtBot) -> None:
    ribbon = build(qtbot, (0.0, 0.6))
    wire(ribbon)
    picture = ribbon.picture_rect()
    start = QPoint(picture.left() + 5, picture.center().y())

    qtbot.mousePress(ribbon, Qt.MouseButton.LeftButton, pos=start)  # type: ignore[no-untyped-call]
    qtbot.mouseMove(ribbon, QPoint(start.x() + int(0.2 * picture.width()), start.y()))  # type: ignore[no-untyped-call]

    moved = ribbon.positions()
    assert moved[0] == pytest.approx(0.2, abs=0.02)
    assert moved[1] == pytest.approx(0.6)


def test_a_drag_emits_while_moving_and_once_on_release(qtbot: QtBot) -> None:
    ribbon = build(qtbot, (0.0, 0.6))
    picture = ribbon.picture_rect()
    start = QPoint(picture.left() + 5, picture.center().y())

    with qtbot.waitSignal(ribbon.frame_moved, timeout=1000):
        qtbot.mousePress(ribbon, Qt.MouseButton.LeftButton, pos=start)  # type: ignore[no-untyped-call]
        qtbot.mouseMove(ribbon, QPoint(start.x() + 40, start.y()))  # type: ignore[no-untyped-call]

    with qtbot.waitSignal(ribbon.frame_settled, timeout=1000):
        qtbot.mouseRelease(ribbon, Qt.MouseButton.LeftButton, pos=QPoint(start.x() + 40, start.y()))  # type: ignore[no-untyped-call]


def test_a_frame_cannot_be_dragged_past_its_neighbour(qtbot: QtBot) -> None:
    ribbon = build(qtbot, (0.0, 0.3))
    wire(ribbon)
    picture = ribbon.picture_rect()
    start = QPoint(picture.left() + 5, picture.center().y())

    qtbot.mousePress(ribbon, Qt.MouseButton.LeftButton, pos=start)  # type: ignore[no-untyped-call]
    qtbot.mouseMove(ribbon, QPoint(picture.right() - 5, start.y()))  # type: ignore[no-untyped-call]

    moved = ribbon.positions()
    assert moved[0] == pytest.approx(0.3, abs=0.02)
    assert moved[1] == pytest.approx(0.3)


def test_a_frame_cannot_be_dragged_off_the_left_edge(qtbot: QtBot) -> None:
    ribbon = build(qtbot, (0.2, 0.6))
    wire(ribbon)
    picture = ribbon.picture_rect()
    start = QPoint(picture.left() + int(0.2 * picture.width()) + 5, picture.center().y())

    qtbot.mousePress(ribbon, Qt.MouseButton.LeftButton, pos=start)  # type: ignore[no-untyped-call]
    qtbot.mouseMove(ribbon, QPoint(picture.left() - 200, start.y()))  # type: ignore[no-untyped-call]

    assert ribbon.positions()[0] == 0.0


def test_uncovered_bands_include_the_pictures_rightmost_column() -> None:
    # A picture spanning x in [0, 99] (right() == 99) with the last window
    # ending at edge = 90 should get a trailing band covering [90, 99],
    # width 10 -- not [90, 98], which leaves the rightmost pixel undimmed.
    picture = QRect(0, 0, 100, 10)
    windows = [QRect(0, 0, 90, 10)]

    bands = _uncovered(picture, windows)

    covered_columns: set[int] = set()
    for window in windows:
        covered_columns.update(range(window.left(), window.right() + 1))
    for band in bands:
        covered_columns.update(range(band.left(), band.right() + 1))

    assert covered_columns == set(range(picture.left(), picture.right() + 1))


def test_a_scan_shaped_panorama_fills_half_the_ribbon(qtbot: QtBot) -> None:
    # The shape this project actually scans, in a ribbon the width the Split
    # tab gives it in a 1280-wide window. Half is the floor the height was
    # chosen against: at 2.4:1 the height binds, so the picture is
    # 2.4 * (RIBBON_HEIGHT - 2 * MARGIN) = 518px, and anything much under
    # half a ribbon is too small to judge where two crops overlap in.
    ribbon = FrameRibbon()
    qtbot.addWidget(ribbon)
    ribbon.resize(912, RIBBON_HEIGHT)
    ribbon.set_source(conftest.synthetic_panorama(600, 250))

    assert ribbon.picture_rect().height() == RIBBON_HEIGHT - 2 * MARGIN
    assert ribbon.picture_rect().width() >= 0.5 * ribbon.width()


def test_the_surface_stops_at_the_picture(qtbot: QtBot) -> None:
    # Like `ContactStrip.span`: a pale tail past the picture reads as an
    # empty panel rather than an object holding something.
    ribbon = build(qtbot)
    ribbon.resize(900, RIBBON_HEIGHT)
    picture = ribbon.picture_rect()
    surface = ribbon.surface_rect()

    assert surface.contains(picture)
    assert surface.width() < ribbon.width()
    assert surface.right() - picture.right() == picture.left() - surface.left()


def test_with_no_source_there_is_no_surface(qtbot: QtBot) -> None:
    ribbon = FrameRibbon()
    qtbot.addWidget(ribbon)
    ribbon.resize(600, RIBBON_HEIGHT)
    ribbon.set_source(None)

    assert ribbon.surface_rect().isNull()


def test_with_no_source_it_draws_nothing_and_does_not_crash(qtbot: QtBot) -> None:
    ribbon = FrameRibbon()
    qtbot.addWidget(ribbon)
    ribbon.resize(600, RIBBON_HEIGHT)
    ribbon.set_source(None)
    ribbon.set_plan((0.0, 0.5), 0.4)
    ribbon.repaint()
    assert ribbon.window_rects() == []


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
        qtbot.keyClick(ribbon, Qt.Key.Key_Right)  # type: ignore[no-untyped-call]
    assert blocker.args == [1, 1]


def test_left_arrow_nudges_the_other_way(qtbot: QtBot) -> None:
    ribbon = build(qtbot, (0.0, 0.6))
    ribbon.set_selected(1)
    with qtbot.waitSignal(ribbon.frame_nudged, timeout=1000) as blocker:
        qtbot.keyClick(ribbon, Qt.Key.Key_Left)  # type: ignore[no-untyped-call]
    assert blocker.args == [1, -1]


def test_shift_makes_the_step_ten_times_bigger(qtbot: QtBot) -> None:
    ribbon = build(qtbot, (0.0, 0.6))
    ribbon.set_selected(0)
    with qtbot.waitSignal(ribbon.frame_nudged, timeout=1000) as blocker:
        qtbot.keyClick(ribbon, Qt.Key.Key_Right, Qt.KeyboardModifier.ShiftModifier)  # type: ignore[no-untyped-call]
    assert blocker.args == [0, 10]


def test_home_and_end_span_the_whole_width(qtbot: QtBot) -> None:
    # A hundred steps is the whole panorama; the tab's clamp does the rest.
    ribbon = build(qtbot, (0.0, 0.6))
    ribbon.set_selected(1)
    with qtbot.waitSignal(ribbon.frame_nudged, timeout=1000) as blocker:
        qtbot.keyClick(ribbon, Qt.Key.Key_Home)  # type: ignore[no-untyped-call]
    assert blocker.args == [1, -100]
    with qtbot.waitSignal(ribbon.frame_nudged, timeout=1000) as blocker:
        qtbot.keyClick(ribbon, Qt.Key.Key_End)  # type: ignore[no-untyped-call]
    assert blocker.args == [1, 100]


def test_down_and_up_move_the_selection(qtbot: QtBot) -> None:
    ribbon = build(qtbot, (0.0, 0.3, 0.6))
    ribbon.set_selected(0)
    with qtbot.waitSignal(ribbon.selection_changed, timeout=1000) as blocker:
        qtbot.keyClick(ribbon, Qt.Key.Key_Down)  # type: ignore[no-untyped-call]
    assert blocker.args == [1]
    assert ribbon.selected() == 1
    with qtbot.waitSignal(ribbon.selection_changed, timeout=1000) as blocker:
        qtbot.keyClick(ribbon, Qt.Key.Key_Up)  # type: ignore[no-untyped-call]
    assert blocker.args == [0]


def test_the_selection_stops_at_the_ends_rather_than_wrapping(qtbot: QtBot) -> None:
    # Wrapping from the last frame back to the first loses your place on a
    # picture you are reading left to right.
    ribbon = build(qtbot, (0.0, 0.3, 0.6))
    ribbon.set_selected(2)
    with qtbot.assertNotEmitted(ribbon.selection_changed):
        qtbot.keyClick(ribbon, Qt.Key.Key_Down)  # type: ignore[no-untyped-call]
    assert ribbon.selected() == 2
    ribbon.set_selected(0)
    with qtbot.assertNotEmitted(ribbon.selection_changed):
        qtbot.keyClick(ribbon, Qt.Key.Key_Up)  # type: ignore[no-untyped-call]
    assert ribbon.selected() == 0


def test_keys_do_nothing_with_no_plan(qtbot: QtBot) -> None:
    ribbon = FrameRibbon()
    qtbot.addWidget(ribbon)
    ribbon.resize(600, RIBBON_HEIGHT)
    with qtbot.assertNotEmitted(ribbon.frame_nudged):
        qtbot.keyClick(ribbon, Qt.Key.Key_Right)  # type: ignore[no-untyped-call]


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


def test_a_shrunk_plan_drops_a_selection_it_can_no_longer_support(qtbot: QtBot) -> None:
    # The tab can select frame 2 of a three-frame plan, then change the
    # ratio so the ribbon's next plan only has two positions. Nothing else
    # updates `_selected`, so without a fix the stale index 2 would survive:
    # `_name_selection` would index the shrunk `_positions` and raise, and a
    # later key press would emit `frame_nudged` for a frame that no longer
    # exists. `set_plan` must drop a selection its own new plan can't
    # support, so nothing downstream ever sees index 2 again.
    ribbon = build(qtbot, (0.0, 0.3, 0.6))
    ribbon.set_selected(2)
    ribbon.set_plan((0.0, 0.6), 0.4)
    assert ribbon.selected() is None
    assert ribbon.marked_rect().isNull()

    # A key press still works -- it just can't be about the dropped frame.
    qtbot.keyClick(ribbon, Qt.Key.Key_Right)  # type: ignore[no-untyped-call]
    assert ribbon.selected() != 2
