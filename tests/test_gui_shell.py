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

from collections.abc import Iterator

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QLabel,
    QLayout,
    QWidget,
)
from pytestqt.qtbot import QtBot

from maskingframe import pipeline
from maskingframe.gui import settings, shell, theme

# Most tests here build `BorderControls` or `MainWindow`, both of which read
# the stored border, without ever naming `isolated_settings` -- so whether
# they saw the developer's real preferences used to depend on whether some
# other, isolated test had already run first in the same process and left
# `QSettings` pointed at a throwaway store. The module mark makes every test
# here isolated regardless of what it asks for by name (maskingframe-2rg.13).
pytestmark = pytest.mark.usefixtures("isolated_settings")

RAIL_CONTENT_WIDTH = theme.RAIL_WIDTH - 2 * theme.L
"""How wide a rail child actually is: the rail, less its own margins."""


def test_a_test_that_never_asks_for_isolation_is_still_isolated(qtbot: QtBot) -> None:
    """Guards the module mark above: proves isolation is a fact about every
    test in this file, not a courtesy the four tests that used to name
    `isolated_settings` extended to themselves alone."""
    controls = shell.BorderControls(show_gutter=True, show_detail_toggle=False)
    qtbot.addWidget(controls)
    controls.reload_presets()

    assert settings.ORGANISATION != "maskingframe"


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


def _column_index(controls: shell.BorderControls, widget: QWidget) -> int:
    """Where a direct child sits in the section's top-to-bottom column.

    `detail_check` and `frame1_section` are both added straight to
    `controls.layout()`, so their order there is the order a person actually
    sees -- the same fact `_stacked_height` reads for height, read here for
    position instead.
    """
    column = controls.layout()
    assert column is not None
    for index in range(column.count()):
        item = column.itemAt(index)
        if item is not None and item.widget() is widget:
            return index
    raise AssertionError(f"{widget} is not a direct child of the section's column")


def test_the_detail_toggle_sits_above_the_frame_one_fold(qtbot: QtBot) -> None:
    """maskingframe-2rg.8: a checkbox about every frame except frame 1 used
    to sit just under the folded FRAME 1 heading, closer to it than the L
    gap that separates every other break in the rail -- so it read as one of
    frame 1's own controls. It belongs with the rest of the shared border,
    above the fold that is frame 1's departure from it."""
    controls = shell.BorderControls(
        show_gutter=True, show_detail_toggle=True, scope=settings.SPLIT, show_frame1=True
    )
    qtbot.addWidget(controls)
    assert controls.detail_check is not None
    assert controls.frame1_section is not None

    assert _column_index(controls, controls.detail_check) < _column_index(
        controls, controls.frame1_section
    )


def _percent_sentence(controls: shell.BorderControls) -> str:
    matches = [
        label.text()
        for label in controls.findChildren(QLabel)
        if "percent of the frame's short side" in label.text()
    ]
    assert len(matches) == 1, matches
    return matches[0]


def test_the_percent_sentence_is_singular_when_only_width_is_showing(qtbot: QtBot) -> None:
    """On Split the row gap lives inside FRAME 1 -- it is frame 1's own
    setting, not a shared border one -- so above the fold there is exactly
    one width slider, and the sentence must say so rather than claim there
    are several."""
    controls = shell.BorderControls(
        show_gutter=True, show_detail_toggle=True, scope=settings.SPLIT, show_frame1=True
    )
    qtbot.addWidget(controls)

    assert _percent_sentence(controls) == "Width is a percent of the frame's short side."


def test_the_percent_sentence_is_plural_and_follows_the_gap_on_compose(qtbot: QtBot) -> None:
    """A composite's gap is a width slider like the border is, and it never
    folds away -- so the sentence describing both must say "Widths" and sit
    after both, not above the one it hadn't reached yet."""
    controls = shell.BorderControls(show_gutter=True, show_detail_toggle=False)
    qtbot.addWidget(controls)
    assert controls.gutter_slider is not None
    gutter_row = controls.gutter_slider.parentWidget()
    assert gutter_row is not None

    sentence = _percent_sentence(controls)
    sentence_label = next(
        label for label in controls.findChildren(QLabel) if label.text() == sentence
    )

    assert sentence == "Widths are a percent of the frame's short side."
    assert _column_index(controls, gutter_row) < _column_index(controls, sentence_label)


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


def test_the_preset_combo_carries_a_placeholder(qtbot: QtBot) -> None:
    """maskingframe-2rg.10: with no preset chosen the box shows blank, and an
    editable combo with no placeholder is visually indistinguishable from a
    `QLineEdit` nobody has filled in -- it is the only editable combo in the
    app, so nothing else teaches a user it is a picker."""
    row = shell.PresetRow()
    qtbot.addWidget(row)
    line_edit = row.box.lineEdit()
    assert line_edit is not None
    assert line_edit.placeholderText() == "No preset"


def test_the_preset_row_sits_on_the_shared_label_column(qtbot: QtBot) -> None:
    """The row obeys the same rule as every other control: a name on
    `theme.FIELD_LABEL_WIDTH`, put there by `shell.labelled` -- not a
    control that is the only one in BORDER left unlabelled."""
    controls = shell.BorderControls(show_gutter=True, show_detail_toggle=False)
    qtbot.addWidget(controls)

    holder = controls.presets.parentWidget()
    assert holder is not None
    layout = holder.layout()
    assert isinstance(layout, QLayout)
    assert layout.count() == 2
    first, second = layout.itemAt(0), layout.itemAt(1)
    assert first is not None and second is not None
    label = first.widget()
    assert isinstance(label, QLabel)
    assert label.objectName() == "FieldLabel"
    assert label.text() == "Preset"
    assert label.minimumWidth() == theme.FIELD_LABEL_WIDTH
    assert second.widget() is controls.presets


def test_the_preset_row_does_not_grow_with_a_saved_name(qtbot: QtBot) -> None:
    """A preset name is user-authored and unbounded, so the row's own width
    must not depend on how long the longest saved one happens to be --
    otherwise saving one long enough would eventually overflow the rail on
    its own, label or no label. `Save` and `Delete` are already sized to
    their own wordings rather than a neighbour's; the box gets a fixed floor
    of its own for the same reason.

    Checked on `row.minimumSizeHint()`, the number a layout actually acts
    on, rather than on `row.box.minimumSizeHint()` directly: an explicit
    `setMinimumWidth` changes what the layout treats as the box's floor
    without changing what `QComboBox.minimumSizeHint()` itself reports, so
    asking the box would still show growth after the fix and pass for the
    wrong reason.

    Compares two fresh rows rather than re-measuring one after `set_names`:
    `QComboBox`'s default `sizeAdjustPolicy` computes its hint once and
    caches it, so a box already measured empty would report the same width
    again regardless of what was added -- which would pass this test
    whether or not the row actually still tracked its content.
    """
    short = shell.PresetRow()
    qtbot.addWidget(short)
    short.set_names(["Plain white"])

    long = shell.PresetRow()
    qtbot.addWidget(long)
    long.set_names(["This is a considerably longer saved preset name than any built-in"])

    assert long.minimumSizeHint().width() == short.minimumSizeHint().width()


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


def test_the_destination_never_goes_below_the_fold(qtbot: QtBot) -> None:
    """The path the files land on is part of the commitment, not a setting.

    At 1100x700 Split scrolled DESTINATION away entirely and left a live Cut
    frames button pinned above it, so the one thing that could not be read
    was where the writing was about to go. Compose did the same at 1100x760
    (maskingframe-2rg.2). Both windows are the sizes the bug was filed at.
    """
    from maskingframe.gui.app import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)

    pairs = (
        (0, window.split, window.split.dest_row, (1100, 700)),
        (1, window.compose, window.compose.output_row, (1100, 760)),
    )
    for index, tab, row, (width, height) in pairs:
        # Each tab has to be the current one to have been laid out at all.
        window.tabs.setCurrentIndex(index)
        window.resize(width, height)
        laid_out = tab.columns.rail_shell

        def is_laid_out(widget: QWidget = laid_out) -> bool:
            return widget.height() > 100

        qtbot.waitUntil(is_laid_out, timeout=2000)
        top = row.mapTo(laid_out, row.rect().topLeft()).y()
        assert top >= 0, type(tab).__name__
        assert top + row.height() <= laid_out.height(), type(tab).__name__
        assert not tab.columns.rail.isAncestorOf(row), "the destination scrolled away"


def test_a_rule_says_where_the_rail_stops_scrolling(qtbot: QtBot) -> None:
    """At 700px the clipped scroll body ran straight into the pinned foot
    with nothing marking the join, which reads as a rendering fault rather
    than as a boundary. One hairline, owned by `TwoColumn` so both rails get
    it from one place."""
    columns = shell.TwoColumn()
    qtbot.addWidget(columns)

    rule = columns.rail_edge
    assert rule.height() == 1
    assert theme.EDGE in rule.styleSheet()
    column = columns.rail_shell.layout()
    assert isinstance(column, QLayout)
    order = [column.itemAt(index).widget() for index in range(column.count())]  # type: ignore[union-attr]
    assert order.index(rule) == order.index(columns.rail_foot) - 1


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


def _widest_offender(widget: QWidget, budget: int) -> QWidget:
    """Walk down from an over-budget widget to the child that names it.

    A `QVBoxLayout` reports its own minimum width as its widest child's, so
    every ancestor of an overflowing control reads as "too wide" once the
    control itself does -- `RailContent`, `BorderControls` and `Disclosure`
    all measured over budget the day this was one `QPushButton`. Descending
    to the child that has no over-budget child of its own left stops at the
    control, not the column it happens to sit in.
    """
    layout = widget.layout()
    if layout is not None:
        for index in range(layout.count()):
            item = layout.itemAt(index)
            child = item.widget() if item is not None else None
            if child is not None and child.minimumSizeHint().width() > budget:
                return _widest_offender(child, budget)
    return widget


def _describe(widget: QWidget) -> str:
    """Enough to find a widget by eye: its class, its object name if it has
    one, and its text if it has that too."""
    described = widget.__class__.__name__
    name = widget.objectName()
    if name:
        described += f"#{name}"
    text = getattr(widget, "text", lambda: "")()
    if text:
        described += f" {text!r}"
    return described


def test_no_rail_control_is_clipped_horizontally(qtbot: QtBot, themed_app: QApplication) -> None:
    """The rail scrolls vertically and must never need to scroll sideways.
    Adding a label column and a scrollbar pushed the ratio combo and the
    Choose button 35px past the edge, where they were simply cut off.

    Needs `themed_app`, not whatever the session `QApplication` happens to
    be carrying: the rail's vertical scrollbar is styled to a fixed 8px in
    `theme.stylesheet()`, and without that sheet macOS's own scrollbar
    claims a different width, which is what let a real 7px overflow in the
    FRAME 1 heading pass here while failing in isolation
    (maskingframe-2rg.11). The policy is set again explicitly rather than
    trusted to whatever `TwoColumn` currently ships with, for the same
    reason -- a viewport's width depends on whether that 8px is reserved at
    all, and this test owns that fact rather than inheriting it.

    `MainWindow()` restores whatever border was last stored, so this also
    relies on the module's `isolated_settings` mark to read a throwaway
    store rather than the developer's real, unpredictable preferences.

    Both tabs are checked: FRAME 1 lives only on Split, but a future
    overflow on Compose would be just as real and this used to only look.
    """
    from maskingframe.gui.app import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    window.resize(1280, 900)
    window.show()
    qtbot.waitExposed(window)

    for tab in (window.split, window.compose):
        columns = tab.columns
        columns.rail.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        qtbot.wait(0)
        margins = columns.rail_layout.contentsMargins()
        budget = columns.rail.viewport().width() - margins.left() - margins.right()
        needed = columns.rail_content.minimumSizeHint().width()
        offender = _widest_offender(columns.rail_content, budget)
        assert needed <= budget, (
            f"{type(tab).__name__} rail needs {needed}px against a {budget}px "
            f"viewport ({needed - budget}px over) -- {_describe(offender)} is "
            "the widest control"
        )


def test_no_frame1_summary_overflows_its_disclosure_header(
    qtbot: QtBot, themed_app: QApplication
) -> None:
    """Pins maskingframe-2rg.11 at the level the bug actually lived at: not
    one rendered state, but every state the FRAME 1 heading can show.

    `test_no_rail_control_is_clipped_horizontally` only ever sees whatever
    rows and border a fresh `SplitTab` opens on, which is why it missed
    this -- the default state fit, and the state that overflowed needed a
    row count and a stored border to both be set at once. This drives the
    rows combo and the "Its own border" checkbox through every reachable
    combination and measures the real header with real font metrics each
    time, rather than trusting that the one combination someone thought to
    render is the widest one.

    Driving the checkbox settles the border, which writes it -- relying on
    the module's `isolated_settings` mark to send that write to a throwaway
    store rather than the developer's real preferences file.

    The shared slider is pushed to one tenth below `MAX_PERCENT` before the
    loop starts. Left at its own default (9%) this would not have failed
    before the fix either -- "9% border" is short -- and the bug as filed
    came from a slider sitting on a longer reading (3.3%, 12.5%).
    `f"{own:g}%"` has no fixed width, and a round number formats shorter
    than one that isn't (`MAX_PERCENT` itself prints as "40", two
    characters), so 39.9 rather than 40.0 is what exercises the widest
    string the old scheme could ever print.
    """
    from maskingframe.gui.app import MainWindow
    from maskingframe.gui.split_tab import ROW_WORDS

    window = MainWindow()
    qtbot.addWidget(window)
    window.resize(1280, 900)
    window.show()
    qtbot.waitExposed(window)

    columns = window.split.columns
    columns.rail.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
    qtbot.wait(0)
    margins = columns.rail_layout.contentsMargins()
    budget = columns.rail.viewport().width() - margins.left() - margins.right()

    window.split.border_controls.border_slider.setValue(pipeline.MAX_PERCENT - 0.1)
    section = window.split.border_controls.frame1_section
    frame1_check = window.split.border_controls.frame1_check
    assert section is not None
    assert frame1_check is not None
    worst_width, worst_text = 0, ""
    for rows in (1, *ROW_WORDS):
        window.split.rows_combo.setCurrentIndex(rows - 1)
        for own_border in (False, True):
            frame1_check.setChecked(own_border)
            qtbot.wait(0)
            width = section.header.minimumSizeHint().width()
            if width > worst_width:
                worst_width, worst_text = width, section.header.text()

    assert worst_width <= budget, (
        f"{worst_width}px against a {budget}px budget -- {worst_text!r} is "
        "the widest reachable heading"
    )


def test_a_swatch_does_not_read_as_an_empty_field(qtbot: QtBot) -> None:
    """A field here is WELL with an EDGE keyline, and a white swatch was
    exactly that -- so the one control whose job is to show a colour looked
    like a text box you had forgotten to fill in. The keyline is what tells
    them apart, and it has to be the keyline rather than the fill, because
    the fill is whatever colour you chose."""
    sheet = theme.stylesheet()

    swatch = sheet.split("#Swatch {")[1].split("}")[0]
    field = sheet.split("QLineEdit {")[1].split("}")[0]

    assert theme.INK_DIM in swatch
    assert theme.EDGE in field
    assert theme.INK_DIM not in field


def test_a_rail_dropdown_has_a_background(qtbot: QtBot) -> None:
    """`#Rail QWidget` makes every plain widget in the rail transparent and
    carries an ID selector, so it beat the popup list's own background rule
    and the open dropdown drew straight over whatever was behind it."""
    sheet = theme.stylesheet()

    assert "#Rail QComboBox QAbstractItemView" in sheet
    popup = sheet.split("#Rail QComboBox QAbstractItemView {")[1].split("}")[0]
    assert theme.WELL in popup
    assert "transparent" not in popup


def _assert_on_the_label_column(combo: QComboBox) -> None:
    """The combo sits beside a `FieldLabel` on the rail's one label column,
    put there by `shell.labelled` -- never bare in the rail layout."""
    holder = combo.parentWidget()
    assert holder is not None, f"{combo.accessibleName()!r} has no labelled() holder"
    layout = holder.layout()
    assert isinstance(layout, QLayout)
    assert layout.count() == 2
    first, second = layout.itemAt(0), layout.itemAt(1)
    assert first is not None and second is not None
    label = first.widget()
    assert isinstance(label, QLabel), f"{combo.accessibleName()!r} has no label beside it"
    assert label.objectName() == "FieldLabel"
    assert label.minimumWidth() == theme.FIELD_LABEL_WIDTH
    assert second.widget() is combo


def test_every_field_combo_sits_on_the_shared_label_column(qtbot: QtBot) -> None:
    """Split's ratio combo has always lined up on the shared column; this
    pins Compose's to the same rule so the two rails cannot drift apart
    again (maskingframe-2rg.4)."""
    from maskingframe.gui.app import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)

    for combo in (
        window.split.ratio_box,
        window.split.rows_combo,
        window.compose.ratio_combo,
        window.compose.arrangement_combo,
    ):
        _assert_on_the_label_column(combo)


@pytest.fixture
def themed_app() -> Iterator[QApplication]:
    """`theme.stylesheet()` applied to the real `QApplication`, exactly as
    `run()` applies it, and restored after.

    A widget's font and a widget's `:disabled` rendering both come from the
    cascade the stylesheet builds, not from a constructor default -- a
    clipped label and a specificity fight that only bites inside `#Rail`
    are both invisible without it, which is how each one shipped.
    """
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    previous = app.styleSheet()
    app.setStyleSheet(theme.stylesheet())
    try:
        yield app
    finally:
        app.setStyleSheet(previous)


def test_no_field_label_clips_in_its_own_column(qtbot: QtBot, themed_app: QApplication) -> None:
    """Measures every `FieldLabel` in both rails against `FIELD_LABEL_WIDTH`
    with the real, stylesheet-driven font -- not a constructor default.

    "Arrangement" cleared review at 68px by eye and clipped to "Arrangeme" in
    the running app: a plain `QFont(family, 13)` measures point sizes, but
    the stylesheet sets `font-size: 13px`, and the two are not the same
    number of pixels. This is the second rail label to overflow its column
    silently, which is why the check is now measured rather than eyeballed.
    """
    from maskingframe.gui.app import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    labels = [label for label in window.findChildren(QLabel) if label.objectName() == "FieldLabel"]
    assert labels, "no FieldLabel found -- the selector or the fixture is broken"
    overflowing = [
        (label.text(), label.fontMetrics().horizontalAdvance(label.text()))
        for label in labels
        if label.fontMetrics().horizontalAdvance(label.text()) > theme.FIELD_LABEL_WIDTH
    ]
    assert overflowing == []


def test_a_disabled_primary_button_does_not_look_pressable(
    qtbot: QtBot, themed_app: QApplication
) -> None:
    """`isEnabled()` was already correct on both tabs' primary button at
    launch -- Cut frames and Save composite are both unpressable with
    nothing loaded. What was wrong is what that state rendered as:
    `#Rail QPushButton#Primary` (two IDs) outranks a bare
    `QPushButton#Primary:disabled` (one ID, one pseudo-class) on CSS
    specificity, so the enabled rule's solid chinagraph fill won regardless
    of enabled state, and a dead control looked identical to a live one
    (maskingframe-2rg.12). Only a render catches that -- `isEnabled()`
    alone would pass on the broken stylesheet exactly as it does on the
    fixed one.
    """
    from maskingframe.gui.app import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    window.resize(1180, 820)
    window.show()
    qtbot.waitExposed(window)

    for tab, button_name in ((window.split, "action_btn"), (window.compose, "save_btn")):
        button = getattr(tab, button_name)
        assert not button.isEnabled(), "the launch state the bug depended on"
        window.tabs.setCurrentWidget(tab)
        themed_app.processEvents()
        image = window.grab().toImage()
        # 8px in from the top-left corner: inside the fill, clear of both
        # the 1px border and the centred label -- "Cut frames" happens to
        # have a gap at its exact rect centre and "Save composite" does
        # not, which made the centre pixel a coin flip between plain fill
        # and a glyph's anti-aliased edge.
        corner = button.mapTo(window, button.rect().topLeft() + QPoint(8, 8))
        colour = image.pixelColor(corner)
        assert colour.name().upper() != theme.CHINAGRAPH, (
            f"{button_name} still renders solid chinagraph while disabled"
        )
        assert colour.name().upper() == theme.PANEL


def test_a_disabled_primary_button_does_not_look_like_an_error(
    qtbot: QtBot, themed_app: QApplication
) -> None:
    """Dropping the fill left the border in chinagraph, and on launch that
    is a white box outlined in red with nothing loaded -- the first thing on
    screen, saying something is wrong. In this theme chinagraph is the
    marking-up layer and the error label uses it, so an unavailable control
    wearing it reads as an invalid one. The palette already makes this
    argument about focus: field focus is INK rather than red, because a
    field turning red when you click into it reads as invalid.

    Every edge of the button is sampled, not one: the fill was already
    greyscale, so a corner probe passes on the broken sheet.
    """
    from maskingframe.gui.app import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    window.resize(1180, 820)
    window.show()
    qtbot.waitExposed(window)

    for tab, button_name in ((window.split, "action_btn"), (window.compose, "save_btn")):
        button = getattr(tab, button_name)
        assert not button.isEnabled(), "the launch state this is about"
        window.tabs.setCurrentWidget(tab)
        themed_app.processEvents()
        image = window.grab().toImage()
        box = button.rect()
        middles = (
            box.topLeft() + QPoint(box.width() // 2, 0),
            box.bottomLeft() + QPoint(box.width() // 2, -1),
            box.topLeft() + QPoint(0, box.height() // 2),
            box.topRight() + QPoint(-1, box.height() // 2),
        )
        for point in middles:
            colour = image.pixelColor(button.mapTo(window, point))
            red, green, blue = colour.red(), colour.green(), colour.blue()
            assert red <= max(green, blue) + 4, (
                f"{button_name} draws {colour.name()} while disabled, which is "
                "chinagraph rather than a grey"
            )
