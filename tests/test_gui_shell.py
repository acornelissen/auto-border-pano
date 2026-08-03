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
from PySide6.QtWidgets import QCheckBox, QColorDialog, QLabel, QLayout, QWidget
from pytestqt.qtbot import QtBot

from maskingframe import pipeline
from maskingframe.gui import settings, shell, theme

RAIL_CONTENT_WIDTH = theme.RAIL_WIDTH - 2 * theme.L
"""How wide a rail child actually is: the rail, less its own margins."""


def _stacked_height(layout: QLayout, width: int) -> int:
    """What a column of children really needs at a given width.

    Word-wrapped labels answer this only through `heightForWidth`; their
    plain size hint is measured at whatever width Qt guessed for them.
    """
    total = 0
    for index in range(layout.count()):
        item = layout.itemAt(index)
        if item is None:
            continue
        if item.hasHeightForWidth():
            total += item.heightForWidth(width)
        else:
            total += item.sizeHint().height()
    return total


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
        controls.border_slider.setValue(15.0)
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
    with (
        qtbot.assertNotEmitted(controls.style_changed),
        qtbot.assertNotEmitted(controls.style_settled),
    ):
        controls.set_style(pipeline.FrameStyle(border_percent=20.0))


# --- settling: cheap on every move, expensive only when the hand stops -------


def test_dragging_a_slider_changes_the_style_without_settling_it(qtbot: QtBot) -> None:
    """A render per pixel of drag would make the app feel broken. The live
    overlay follows every move; the re-render waits for the hand to stop."""
    controls = shell.BorderControls(show_gutter=False, show_detail_toggle=False)
    qtbot.addWidget(controls)
    controls.border_slider.slider.setSliderDown(True)

    with (
        qtbot.assertNotEmitted(controls.style_settled),
        qtbot.waitSignal(controls.style_changed),
    ):
        controls.border_slider.setValue(15.0)


def test_releasing_a_dragged_slider_settles_it_once(qtbot: QtBot) -> None:
    controls = shell.BorderControls(show_gutter=False, show_detail_toggle=False)
    qtbot.addWidget(controls)
    settled: list[float] = []
    controls.style_settled.connect(lambda style: settled.append(style.border_percent))

    controls.border_slider.slider.setSliderDown(True)
    controls.border_slider.setValue(15.0)
    controls.border_slider.slider.setSliderDown(False)

    assert settled == [15.0]


def test_a_keyboard_change_settles_the_style(qtbot: QtBot) -> None:
    """Arrow and page keys produce no release event, so a settle that waited
    for one would leave the keyboard unable to re-render anything."""
    controls = shell.BorderControls(show_gutter=False, show_detail_toggle=False)
    qtbot.addWidget(controls)
    controls.show()
    qtbot.waitExposed(controls)
    controls.border_slider.slider.setFocus()

    with qtbot.waitSignal(controls.style_settled) as blocker:
        qtbot.keyClick(controls.border_slider.slider, Qt.Key.Key_Right)  # type: ignore[no-untyped-call]
    assert blocker.args[0].border_percent == pytest.approx(9.5)


def test_a_swatch_settles_immediately(qtbot: QtBot) -> None:
    """There is nothing to drag, so there is nothing to wait for."""
    controls = shell.BorderControls(show_gutter=False, show_detail_toggle=False)
    qtbot.addWidget(controls)
    with qtbot.waitSignal(controls.style_settled) as blocker:
        controls.border_swatch.set_colour("#000000")
    assert blocker.args[0].border_colour == "#000000"


def test_the_detail_toggle_settles_immediately(qtbot: QtBot) -> None:
    controls = shell.BorderControls(show_gutter=False, show_detail_toggle=True)
    qtbot.addWidget(controls)
    assert controls.detail_check is not None
    with qtbot.waitSignal(controls.style_settled) as blocker:
        controls.detail_check.setChecked(True)
    assert blocker.args[0].border_detail_frames is True


def test_gutter_controls_are_hidden_when_not_wanted(qtbot: QtBot) -> None:
    controls = shell.BorderControls(show_gutter=False, show_detail_toggle=False)
    qtbot.addWidget(controls)
    assert controls.gutter_slider is None
    assert controls.gutter_swatch is None
    assert controls.detail_check is None


def test_the_sliders_cannot_leave_the_allowed_range(qtbot: QtBot) -> None:
    controls = shell.BorderControls(show_gutter=True, show_detail_toggle=False)
    qtbot.addWidget(controls)
    assert controls.gutter_slider is not None
    for slider in (controls.border_slider, controls.gutter_slider):
        assert slider.minimum() == 0.0
        assert slider.maximum() == pipeline.MAX_PERCENT
        slider.setValue(-5.0)
        assert slider.value() == 0.0
        slider.setValue(pipeline.MAX_PERCENT + 5.0)
        assert slider.value() == pipeline.MAX_PERCENT


def test_every_control_is_keyboard_reachable(qtbot: QtBot) -> None:
    controls = shell.BorderControls(show_gutter=True, show_detail_toggle=True)
    qtbot.addWidget(controls)
    assert controls.gutter_slider is not None
    assert controls.gutter_swatch is not None
    assert controls.detail_check is not None
    for widget in (
        controls.border_slider,
        controls.border_swatch,
        controls.gutter_slider,
        controls.gutter_swatch,
        controls.detail_check,
    ):
        assert widget.focusPolicy() != Qt.FocusPolicy.NoFocus
        assert widget.accessibleName()


# --- The percent slider -----------------------------------------------------


def test_the_slider_keeps_half_and_tenth_percent_values(qtbot: QtBot) -> None:
    """A stored style must survive a round trip through the integer slider."""
    slider = shell.PercentSlider("Border width", 9.0)
    qtbot.addWidget(slider)
    for value in (0.0, 0.1, 9.0, 12.5, 33.3, pipeline.MAX_PERCENT):
        slider.setValue(value)
        assert slider.value() == pytest.approx(value)


def test_the_slider_reads_its_value_out(qtbot: QtBot) -> None:
    slider = shell.PercentSlider("Border width", 9.0)
    qtbot.addWidget(slider)
    assert slider.readout.text() == "9.0 %"
    slider.setValue(12.5)
    assert slider.readout.text() == "12.5 %"


def test_the_readout_does_not_change_width_with_the_value(qtbot: QtBot) -> None:
    """A row that jitters as you drag is a row you cannot aim at."""
    slider = shell.PercentSlider("Border width", 0.0)
    qtbot.addWidget(slider)
    narrow = slider.readout.width()
    slider.setValue(pipeline.MAX_PERCENT)
    assert slider.readout.width() == narrow


def test_the_slider_announces_itself_and_its_value(qtbot: QtBot) -> None:
    """The readout is decoration; the slider itself has to speak."""
    slider = shell.PercentSlider("Border width", 9.0)
    qtbot.addWidget(slider)
    assert slider.accessibleName() == "Border width"
    assert slider.slider.accessibleName() == "Border width"
    assert "9.0" in slider.slider.accessibleDescription()
    slider.setValue(12.5)
    assert "12.5" in slider.slider.accessibleDescription()


def test_the_slider_emits_once_per_change(qtbot: QtBot) -> None:
    slider = shell.PercentSlider("Border width", 9.0)
    qtbot.addWidget(slider)
    with qtbot.waitSignal(slider.valueChanged) as blocker:
        slider.setValue(12.5)
    assert blocker.args == [12.5]


def test_the_slider_is_silent_when_the_value_does_not_move(qtbot: QtBot) -> None:
    slider = shell.PercentSlider("Border width", 9.0)
    qtbot.addWidget(slider)
    with qtbot.assertNotEmitted(slider.valueChanged):
        slider.setValue(9.0)


def test_the_keyboard_still_drives_the_slider(qtbot: QtBot) -> None:
    """Styling a slider can cost it its groove and handle sub-controls, and
    with them the arrow keys. These are Qt's defaults; the test is that
    nothing here has taken them away."""
    slider = shell.PercentSlider("Border width", 9.0)
    qtbot.addWidget(slider)
    slider.show()
    qtbot.waitExposed(slider)
    slider.slider.setFocus()

    qtbot.keyClick(slider.slider, Qt.Key.Key_Right)  # type: ignore[no-untyped-call]
    assert slider.value() == pytest.approx(9.5)
    qtbot.keyClick(slider.slider, Qt.Key.Key_PageUp)  # type: ignore[no-untyped-call]
    assert slider.value() == pytest.approx(14.5)
    qtbot.keyClick(slider.slider, Qt.Key.Key_Home)  # type: ignore[no-untyped-call]
    assert slider.value() == 0.0
    qtbot.keyClick(slider.slider, Qt.Key.Key_End)  # type: ignore[no-untyped-call]
    assert slider.value() == pipeline.MAX_PERCENT


# --- Height, which is where the help text was being cut off -----------------


def test_border_controls_report_a_width_aware_height(qtbot: QtBot) -> None:
    """The regression: the wrapped help labels live one layout deeper than
    the rail's own, and a nested `heightForWidth` does not propagate unless
    the containing widget opts in. Without that the rail sized this widget
    from a hint measured at some other width and clipped the last line."""
    controls = shell.BorderControls(show_gutter=True, show_detail_toggle=True)
    qtbot.addWidget(controls)
    column = controls.layout()
    assert column is not None
    needed = _stacked_height(column, RAIL_CONTENT_WIDTH)

    assert controls.sizePolicy().hasHeightForWidth()
    assert controls.heightForWidth(RAIL_CONTENT_WIDTH) >= needed


def test_a_rail_reserves_the_height_the_border_section_needs(qtbot: QtBot) -> None:
    """The height hint has to survive the trip up to the rail, which is what
    the size policy is for: a layout only asks `heightForWidth` of an item
    whose widget claims to have one.
    """
    rail = shell.TwoColumn()
    qtbot.addWidget(rail)
    controls = shell.BorderControls(show_gutter=True, show_detail_toggle=True)
    rail.rail_layout.addWidget(controls)
    column = controls.layout()
    assert column is not None
    needed = _stacked_height(column, RAIL_CONTENT_WIDTH)

    item = rail.rail_layout.itemAt(0)
    assert item is not None
    assert item.hasHeightForWidth()
    assert item.heightForWidth(RAIL_CONTENT_WIDTH) >= needed
    # The floor, not just the preference: a short window must not be allowed
    # to squeeze the help text back down to one line.
    assert rail.rail_layout.minimumSize().height() >= needed


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
        qtbot.keyClick(row.box.lineEdit(), Qt.Key.Key_Return)  # type: ignore[no-untyped-call]

    assert by_button.args == by_key.args == ["Warm white"]


def test_saving_a_blank_name_does_nothing(qtbot: QtBot) -> None:
    row = shell.PresetRow()
    qtbot.addWidget(row)
    row.box.setEditText("   ")

    with qtbot.assertNotEmitted(row.saved):
        row.save_button.click()


def test_saving_a_name_with_a_separator_does_nothing(qtbot: QtBot) -> None:
    # `/` and `\` are group separators to `QSettings`; a name containing one
    # must never reach `saved`, the same as a blank name.
    row = shell.PresetRow()
    qtbot.addWidget(row)
    row.box.setEditText("before/after")

    assert not row.save_button.isEnabled()
    with qtbot.assertNotEmitted(row.saved):
        row.save_button.click()


def test_the_return_key_on_a_separator_name_does_nothing(qtbot: QtBot) -> None:
    # The Return key goes through `returnPressed`, not the button, so it
    # bypasses the button's enabled state entirely -- this is the path that
    # would break first if the check ever moved into `_sync_buttons` alone.
    row = shell.PresetRow()
    qtbot.addWidget(row)
    row.box.setEditText("before/after")

    with qtbot.assertNotEmitted(row.saved):
        qtbot.keyClick(row.box.lineEdit(), Qt.Key.Key_Return)  # type: ignore[no-untyped-call]


def test_the_return_key_on_a_blank_name_does_nothing(qtbot: QtBot) -> None:
    row = shell.PresetRow()
    qtbot.addWidget(row)
    row.box.setEditText("   ")

    with qtbot.assertNotEmitted(row.saved):
        qtbot.keyClick(row.box.lineEdit(), Qt.Key.Key_Return)  # type: ignore[no-untyped-call]


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


def _split_controls(qtbot: QtBot) -> tuple[shell.BorderControls, QCheckBox, shell.PercentSlider]:
    """A Split rail, with its frame 1 pair already narrowed.

    Both are Optional on the widget because Compose does not show them; a
    Split rail always does, and asserting that here once beats repeating a
    None check in every test."""
    built = shell.BorderControls(
        show_gutter=False, show_detail_toggle=True, scope=settings.SPLIT, show_frame1=True
    )
    qtbot.addWidget(built)
    assert built.frame1_check is not None
    assert built.frame1_slider is not None
    return built, built.frame1_check, built.frame1_slider


def test_the_frame_one_slider_is_off_until_it_is_asked_for(qtbot: QtBot) -> None:
    controls, check, slider = _split_controls(qtbot)

    assert not check.isChecked()
    assert not slider.isEnabled()
    assert controls.frame_style().padded_border_percent is None


def test_ticking_frame_one_adopts_the_shared_width(qtbot: QtBot) -> None:
    """Ticking must not move the frame. It starts from where you already
    were, so the checkbox reveals a control rather than applying a change."""
    controls, check, slider = _split_controls(qtbot)
    controls.border_slider.setValue(14.0)

    check.setChecked(True)

    assert slider.isEnabled()
    assert slider.value() == 14.0
    assert controls.frame_style().padded_border_percent == 14.0


def test_unticking_frame_one_gives_the_border_back(qtbot: QtBot) -> None:
    controls, check, slider = _split_controls(qtbot)
    check.setChecked(True)
    slider.setValue(1.0)

    check.setChecked(False)

    assert controls.frame_style().padded_border_percent is None


def test_a_frame_one_width_of_zero_survives_being_read_back(qtbot: QtBot) -> None:
    """0 is full bleed, a real choice, and must not read as 'unset'."""
    controls, check, _slider = _split_controls(qtbot)

    controls.set_style(pipeline.FrameStyle(padded_border_percent=0.0))

    assert check.isChecked()
    assert controls.frame_style().padded_border_percent == 0.0


def test_set_style_restores_the_frame_one_width(qtbot: QtBot) -> None:
    controls, check, slider = _split_controls(qtbot)

    controls.set_style(pipeline.FrameStyle(border_percent=9.0, padded_border_percent=3.0))

    assert check.isChecked()
    assert slider.value() == 3.0
    assert controls.frame_style().padded_border_percent == 3.0


def test_compose_is_not_offered_a_frame_one_border(qtbot: QtBot) -> None:
    """A composite has no frame 1, so the rail must not offer a control for
    one -- the same reason Compose has no detail-frames toggle."""
    built = shell.BorderControls(show_gutter=True, show_detail_toggle=False, scope=settings.COMPOSE)
    qtbot.addWidget(built)

    assert built.frame1_check is None
    assert built.frame_style().padded_border_percent is None


def test_a_short_window_scrolls_the_rail_rather_than_crushing_it(qtbot: QtBot) -> None:
    """The rail is a column of settings, and a window shorter than the
    column has to scroll it. Squeezing instead draws the controls on top of
    one another: at 860px the border section was given 102px of the 367 it
    needs, and every row inside it came out five pixels tall.
    """
    from maskingframe.gui.app import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    window.resize(1280, 700)
    window.show()
    qtbot.waitExposed(window)

    controls = window.split.border_controls
    assert controls.height() >= controls.heightForWidth(controls.width())


def test_the_rail_keeps_its_width_when_it_scrolls(qtbot: QtBot) -> None:
    """A scrollbar must not eat the rail's width -- the two columns are a
    fixed rail and everything else, and a rail that narrows when the window
    shortens would reflow every label in it."""
    from maskingframe.gui.app import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    window.show()

    window.resize(1280, 1400)
    qtbot.waitExposed(window)
    tall = window.split.border_controls.width()

    window.resize(1280, 700)
    qtbot.waitUntil(lambda: window.height() < 800, timeout=2000)

    assert window.split.border_controls.width() == tall


def test_each_tab_says_what_its_own_gap_separates(qtbot: QtBot) -> None:
    """One control and one stored field, but not one name: a composite's gap
    is between panels, and a split's is between frame 1's rows. Split used to
    be handed the composite's wording, and Split has no panels."""
    from maskingframe.gui.app import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)

    def help_texts(controls: shell.BorderControls) -> list[str]:
        return [label.text() for label in controls.findChildren(QLabel)]

    split = " ".join(help_texts(window.split.border_controls))
    compose = " ".join(help_texts(window.compose.border_controls))

    # Carried by the label on the control now, not by a sentence under it.
    assert "Row gap" in split
    assert "Panel gap" not in split
    assert "Panel gap" in compose


def test_the_preset_buttons_are_wide_enough_for_their_own_labels(qtbot: QtBot) -> None:
    """Their width is pinned so swapping Save for Update does not shove the
    delete button under the pointer. Pinning it from a spacing constant
    rather than from Qt's own measurement made it 6px short of the
    stylesheet's padding, and the delete button clipped its glyph."""
    row = shell.PresetRow()
    qtbot.addWidget(row)

    for button in (row.save_button, row.delete_button):
        assert button.width() >= button.sizeHint().width(), button.text()


def test_the_save_button_keeps_one_width_across_both_wordings(qtbot: QtBot) -> None:
    row = shell.PresetRow()
    qtbot.addWidget(row)

    row.save_button.setText("Save")
    saving = row.save_button.width()
    row.save_button.setText("Update")

    assert row.save_button.width() == saving
    assert saving >= row.save_button.sizeHint().width()


def test_the_primary_action_never_goes_below_the_fold(qtbot: QtBot) -> None:
    """A commit button you have to scroll to is the one convention this rail
    cannot afford to break. It sat at y=906 in an 812px viewport once the
    rail started scrolling, so it lives outside the scroll area now."""
    from maskingframe.gui.app import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    window.resize(1280, 700)
    window.show()
    qtbot.waitExposed(window)

    pairs = (
        (0, window.split, window.split.action_btn),
        (1, window.compose, window.compose.save_btn),
    )
    for index, tab, button in pairs:
        # Each tab has to be the current one to have been laid out at all.
        window.tabs.setCurrentIndex(index)
        laid_out = tab.columns.rail_shell

        def is_laid_out(widget: QWidget = laid_out) -> bool:
            return widget.height() > 100

        qtbot.waitUntil(is_laid_out, timeout=2000)
        shell_widget = tab.columns.rail_shell
        top = button.mapTo(shell_widget, button.rect().topLeft()).y()
        bottom = top + button.height()
        assert top >= 0, button.text()
        assert bottom <= shell_widget.height(), button.text()
        assert not tab.columns.rail.isAncestorOf(button), "the action scrolled away"


def test_checkboxes_are_styled_like_the_radios(qtbot: QtBot) -> None:
    """An unstyled QCheckBox draws the stock macOS tick in system blue. The
    radios are styled for exactly that reason -- one saturated hue, and it
    is chinagraph -- and the checkboxes had been missed."""
    sheet = theme.stylesheet()

    assert "QCheckBox::indicator" in sheet
    assert (
        f"QCheckBox::indicator:checked {{\n        border: 1px solid {theme.CHINAGRAPH};" in sheet
    )
    # Square, not round: the shape is what tells a checkbox from a radio.
    checkbox = sheet.split("QCheckBox::indicator {")[1].split("}")[0]
    assert "border-radius" not in checkbox


def test_no_rail_control_is_clipped_horizontally(qtbot: QtBot) -> None:
    """The rail scrolls vertically and must never need to scroll sideways.
    Adding a label column and a scrollbar pushed the ratio combo and the
    Choose button 35px past the edge, where they were simply cut off."""
    from maskingframe.gui.app import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    window.resize(1280, 900)
    window.show()
    qtbot.waitExposed(window)

    columns = window.split.columns
    needed = columns.rail_content.minimumSizeHint().width()
    assert needed <= columns.rail.viewport().width(), (
        f"{needed - columns.rail.viewport().width()}px over"
    )
