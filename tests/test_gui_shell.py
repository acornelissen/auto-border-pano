"""Tests for the shared rail widgets.

The border section appears on both rails and must behave identically on
each, so these are about the contract `BorderControls` offers its two
callers: it hands back a whole `FrameStyle`, it announces a change exactly
once, and it stays quiet while it is being restored from stored state.

The swatch gets its own tests because it is the one control here whose
meaning could hide in colour alone. They run headless under
`QT_QPA_PLATFORM=offscreen`; `qtbot` supplies the `QApplication`. No test
opens the colour dialog for real -- a modal would hang the suite -- so
`QColorDialog.getColor` is patched where the picker is exercised.
"""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QColorDialog
from pytestqt.qtbot import QtBot

from maskingframe import pipeline
from maskingframe.gui import shell


def test_swatch_reports_its_colour(qtbot: QtBot) -> None:
    swatch = shell.Swatch("#c9302a")
    qtbot.addWidget(swatch)
    assert swatch.colour == "#c9302a"


def test_swatch_normalises_what_it_is_given(qtbot: QtBot) -> None:
    swatch = shell.Swatch("C9302A")
    qtbot.addWidget(swatch)
    assert swatch.colour == "#c9302a"


def test_swatch_emits_on_change(qtbot: QtBot) -> None:
    swatch = shell.Swatch("#ffffff")
    qtbot.addWidget(swatch)
    with qtbot.waitSignal(swatch.colour_changed) as blocker:
        swatch.set_colour("#000000")
    assert blocker.args == ["#000000"]


def test_swatch_does_not_emit_when_the_colour_is_unchanged(qtbot: QtBot) -> None:
    swatch = shell.Swatch("#ffffff")
    qtbot.addWidget(swatch)
    with qtbot.assertNotEmitted(swatch.colour_changed):
        swatch.set_colour("#FFFFFF")


def test_swatch_names_its_colour_for_screen_readers(qtbot: QtBot) -> None:
    swatch = shell.Swatch("#c9302a")
    qtbot.addWidget(swatch)
    assert "c9302a" in swatch.accessibleName().lower()


def test_swatch_renames_itself_when_the_colour_changes(qtbot: QtBot) -> None:
    swatch = shell.Swatch("#ffffff", "Gap colour")
    qtbot.addWidget(swatch)
    swatch.set_colour("#000000")
    assert swatch.accessibleName() == "Gap colour #000000"


def test_swatch_is_keyboard_reachable(qtbot: QtBot) -> None:
    swatch = shell.Swatch("#ffffff")
    qtbot.addWidget(swatch)
    assert swatch.focusPolicy() != Qt.FocusPolicy.NoFocus


def test_swatch_takes_the_picked_colour(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    swatch = shell.Swatch("#ffffff")
    qtbot.addWidget(swatch)
    monkeypatch.setattr(QColorDialog, "getColor", lambda *a, **k: QColor("#c9302a"))
    swatch._choose()
    assert swatch.colour == "#c9302a"


def test_swatch_keeps_its_colour_when_the_picker_is_cancelled(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    swatch = shell.Swatch("#ffffff")
    qtbot.addWidget(swatch)
    monkeypatch.setattr(QColorDialog, "getColor", lambda *a, **k: QColor())
    swatch._choose()
    assert swatch.colour == "#ffffff"


def test_border_controls_start_at_the_default(qtbot: QtBot) -> None:
    controls = shell.BorderControls(show_gutter=True, show_detail_toggle=False)
    qtbot.addWidget(controls)
    assert controls.frame_style() == pipeline.DEFAULT_STYLE


def test_border_controls_round_trip_a_style(qtbot: QtBot) -> None:
    controls = shell.BorderControls(show_gutter=True, show_detail_toggle=True)
    qtbot.addWidget(controls)
    style = pipeline.FrameStyle(
        border_percent=12.5,
        border_colour="#c9302a",
        gutter_percent=1.0,
        gutter_colour="#000000",
        border_detail_frames=True,
    )
    controls.set_style(style)
    assert controls.frame_style() == style


def test_border_controls_emit_when_a_field_changes(qtbot: QtBot) -> None:
    controls = shell.BorderControls(show_gutter=False, show_detail_toggle=False)
    qtbot.addWidget(controls)
    with qtbot.waitSignal(controls.style_changed) as blocker:
        controls.border_spin.setValue(15.0)
    assert blocker.args[0].border_percent == 15.0


def test_border_controls_emit_when_a_swatch_changes(qtbot: QtBot) -> None:
    controls = shell.BorderControls(show_gutter=False, show_detail_toggle=False)
    qtbot.addWidget(controls)
    with qtbot.waitSignal(controls.style_changed) as blocker:
        controls.border_swatch.set_colour("#000000")
    assert blocker.args[0].border_colour == "#000000"


def test_set_style_does_not_re_emit(qtbot: QtBot) -> None:
    controls = shell.BorderControls(show_gutter=False, show_detail_toggle=False)
    qtbot.addWidget(controls)
    with qtbot.assertNotEmitted(controls.style_changed):
        controls.set_style(pipeline.FrameStyle(border_percent=20.0))


def test_gutter_controls_are_hidden_when_not_wanted(qtbot: QtBot) -> None:
    controls = shell.BorderControls(show_gutter=False, show_detail_toggle=False)
    qtbot.addWidget(controls)
    assert controls.gutter_spin is None
    assert controls.gutter_swatch is None
    assert controls.detail_check is None


def test_the_spin_boxes_cannot_leave_the_allowed_range(qtbot: QtBot) -> None:
    controls = shell.BorderControls(show_gutter=True, show_detail_toggle=False)
    qtbot.addWidget(controls)
    assert controls.gutter_spin is not None
    for spin in (controls.border_spin, controls.gutter_spin):
        assert spin.minimum() == 0.0
        assert spin.maximum() == pipeline.MAX_PERCENT


def test_every_control_is_keyboard_reachable(qtbot: QtBot) -> None:
    controls = shell.BorderControls(show_gutter=True, show_detail_toggle=True)
    qtbot.addWidget(controls)
    assert controls.gutter_spin is not None
    assert controls.gutter_swatch is not None
    assert controls.detail_check is not None
    for widget in (
        controls.border_spin,
        controls.border_swatch,
        controls.gutter_spin,
        controls.gutter_swatch,
        controls.detail_check,
    ):
        assert widget.focusPolicy() != Qt.FocusPolicy.NoFocus
        assert widget.accessibleName()
