"""The skeleton both tabs are built on.

There is one product here, not two. Both rails carry the same sections in
the same order -- subject, then FORMAT, then DESTINATION, then the primary
action -- so switching tabs does not re-lay-out the window.

Presentation only, like `theme`. Nothing here knows what a panorama is.
`pipeline` is imported for the `FrameStyle` type, its defaults and its
colour parser, and for nothing else -- no image work happens here. It is
imported from `pipeline` rather than `geometry` so the rule that `gui/`
depends on `pipeline` alone still holds.
"""

from collections.abc import Sequence

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QFontMetrics, QPainter, QPaintEvent, QPen, QResizeEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from maskingframe import pipeline
from maskingframe.gui import settings, theme

UPDATING_PREVIEW = "Updating the preview."
"""What both tabs say while a loaded render is being made again.

The old picture stays on the table until the new one lands, so this is the
only sign that it is a moment out of date. Present tense, help voice: it
reports work in hand, not a fault.
"""

STALE_PREVIEW = "Preview is out of date. Press Preview to render it again."
"""What both tabs say when the render on the table cannot be made again.

The usual answer to a changed setting is to render it again by itself. When
that is not possible -- the source has gone, or something else is already
running -- this says so plainly rather than leaving a picture of settings
nobody has any more without comment.
"""


class RebateBand(QWidget):
    """The black band a lab prints the frame's name onto.

    It leads with the subject. The tkinter build opened with the app's own
    name, which the window's title bar was already saying directly above it
    -- the band was spending its most prominent position on a duplicate.
    """

    NOTHING_LOADED = "No source loaded"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(theme.BAND_HEIGHT)
        self.setAutoFillBackground(True)
        self._subject = ""
        self._detail = ""

    def set_subject(self, text: str) -> None:
        self._subject = text
        self.update()

    def set_detail(self, text: str) -> None:
        self._detail = text
        self.update()

    @property
    def subject(self) -> str:
        return self._subject

    @property
    def detail(self) -> str:
        return self._detail

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.fillRect(self.rect(), theme.rgb(theme.REBATE))

        painter.setFont(theme.stencil_font(12, tracking=2.6))
        loaded = bool(self._subject)
        painter.setPen(theme.rgb(theme.TABLE if loaded else "#6C747B"))
        box = self.rect().adjusted(theme.L, 0, -theme.L, 0)
        painter.drawText(
            box,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            self._subject or self.NOTHING_LOADED,
        )

        if self._detail:
            painter.setFont(theme.stencil_font(11, tracking=2.0))
            painter.setPen(theme.rgb("#6C747B"))
            painter.drawText(
                box,
                int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                self._detail,
            )


class TwoColumn(QWidget):
    """A fixed control rail on the left, the light table on the right.

    The preview used to be whatever space was left at the bottom of the tab,
    which is how it came to own 45% of the window while showing nothing.
    Here it occupies the right column by design.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        # The rail scrolls. It is a column of settings that has grown with
        # every feature, and a window shorter than the column used to have
        # Qt squeeze the difference out of the controls -- at 860px the
        # border section was given 102px of the 367 it needs and every row
        # in it came out five pixels tall, drawn over its neighbours. A
        # scroll area is what makes "too tall" mean scrolling rather than
        # collapsing, and it keeps the next section that gets added from
        # doing the same thing again.
        self.rail_shell = QWidget(self)
        self.rail_shell.setObjectName("Rail")
        self.rail_shell.setFixedWidth(theme.RAIL_WIDTH)

        self.rail = QScrollArea()
        self.rail.setObjectName("RailScroll")
        self.rail.setWidgetResizable(True)
        self.rail.setFrameShape(QFrame.Shape.NoFrame)
        self.rail.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # Always on, not as-needed: a scrollbar that appears and disappears
        # reflows every wrapped label in the rail as the window is dragged,
        # and the labels here are pinned to a measured height.
        self.rail.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)

        self.rail_content = QWidget()
        self.rail_content.setObjectName("RailContent")
        self.rail.setWidget(self.rail_content)
        self.rail_layout = QVBoxLayout(self.rail_content)
        self.rail_layout.setContentsMargins(theme.L, theme.L, theme.L, theme.S)
        self.rail_layout.setSpacing(0)

        # The settings scroll; the thing that commits them does not. A
        # primary action that goes below the fold on a laptop window is the
        # one convention this rail cannot afford to break, and pinning it
        # also means it stops moving as the rail grows -- muscle memory
        # improves rather than suffers.
        self.rail_foot = QWidget()
        self.rail_foot.setObjectName("RailFoot")
        self.rail_foot_layout = QVBoxLayout(self.rail_foot)
        self.rail_foot_layout.setContentsMargins(theme.L, theme.S, theme.L, theme.L)
        self.rail_foot_layout.setSpacing(0)

        rail_column = QVBoxLayout(self.rail_shell)
        rail_column.setContentsMargins(0, 0, 0, 0)
        rail_column.setSpacing(0)
        rail_column.addWidget(self.rail, 1)
        rail_column.addWidget(self.rail_foot)

        self.table = QWidget(self)
        self.table.setObjectName("Table")
        self.table_layout = QVBoxLayout(self.table)
        self.table_layout.setContentsMargins(theme.L, theme.L, theme.L, theme.L)
        self.table_layout.setSpacing(0)

        row.addWidget(self.rail_shell)
        row.addWidget(self.table, 1)


class Disclosure(QWidget):
    """A section that folds away, carrying its state in the heading.

    The pattern every pro tool's inspector uses: a parameter sitting at its
    default and rarely touched should cost a word, not a row. Frame 1's
    settings are off for most panoramas and cost about 140px permanently.

    Collapsed it still *says* what it is set to, on the right of its own
    heading, so nothing is hidden in the bad sense -- you can read the state
    without opening it, which is the difference between folding a section
    away and burying it.

    Instant, never animated: the theme spends no motion, and a section that
    slid open would be the only thing in the application that moved.
    """

    toggled = Signal(bool)

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)

        self.header = QPushButton()
        self.header.setObjectName("Disclosure")
        self.header.setCheckable(True)
        self.header.setCursor(Qt.CursorShape.PointingHandCursor)
        self._title = title.upper()
        self.header.toggled.connect(self._on_toggled)
        column.addWidget(self.header)

        self.body = QWidget()
        self.body.setVisible(False)
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, theme.S, 0, 0)
        self.body_layout.setSpacing(0)
        column.addWidget(self.body)

        self._summary = ""
        self._paint_header()

    def set_summary(self, summary: str) -> None:
        """Say what the section is set to, without opening it."""
        self._summary = summary
        self._paint_header()

    def _paint_header(self) -> None:
        # The glyph is the affordance and the summary is the state. Both on
        # one line, because a heading that wrapped would defeat the point.
        glyph = "\u2212" if self.header.isChecked() else "+"
        summary = f"   {self._summary}" if self._summary and not self.header.isChecked() else ""
        self.header.setText(f"{glyph}  {self._title}{summary}")
        spoken = f"{self._title}, {self._summary}" if self._summary else self._title
        self.header.setAccessibleName(spoken)

    def _on_toggled(self, open_: bool) -> None:
        self.body.setVisible(open_)
        self._paint_header()
        self.toggled.emit(open_)

    def set_open(self, open_: bool) -> None:
        self.header.setChecked(open_)

    def is_open(self) -> bool:
        return bool(self.header.isChecked())


def labelled(label: str, control: QWidget) -> QWidget:
    """A control with its name beside it, on the rail's one label column.

    The same argument as `PercentSlider`'s own label: a combo whose only
    identification is a sentence printed underneath it makes you read past
    the control to learn what it was. The width is fixed and shared, so
    every field in every section lines its control up on one edge.
    """
    holder = QWidget()
    row = QHBoxLayout(holder)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(theme.S)
    name = QLabel(label)
    name.setObjectName("FieldLabel")
    name.setFixedWidth(theme.FIELD_LABEL_WIDTH)
    name.setBuddy(control)
    control.setAccessibleName(label)
    row.addWidget(name)
    row.addWidget(control, 1)
    return holder


def section(text: str) -> QLabel:
    """A rail section heading: SOURCE, FORMAT, DESTINATION.

    The rail is grouped by headings and whitespace rather than by rules --
    hairlines everywhere is the broadsheet default, and this is a utility
    panel, not a newspaper.
    """
    label = QLabel(text.upper())
    label.setObjectName("Section")
    return label


def help_label(text: str = "") -> QLabel:
    label = QLabel(text)
    label.setObjectName("Help")
    label.setWordWrap(True)
    return label


def data_label(text: str = "") -> QLabel:
    label = QLabel(text)
    label.setObjectName("Data")
    return label


def rule() -> QFrame:
    """One device pixel, which is a thing Qt can actually draw."""
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFixedHeight(1)
    line.setStyleSheet(f"background: {theme.EDGE}; border: none;")
    return line


class PathRow(QWidget):
    """A path field and its Choose button, identical on both rails.

    The field rides at its tail. A path is longer than the rail and Qt, like
    Tk, shows a field from its start -- so the rails displayed the volume and
    clipped the filename, the only part of a path anybody recognises.
    """

    def __init__(self, button_text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(theme.S)

        self.field = QLineEdit()
        self.field.textChanged.connect(self._show_tail)
        self.button = QPushButton(button_text)

        row.addWidget(self.field, 1)
        row.addWidget(self.button)

    def _show_tail(self, _text: str) -> None:
        # Not while it has focus: yanking the view out from under someone
        # typing, or with the caret mid-path, is the interface fighting them.
        if self.field.hasFocus():
            return
        self.field.setCursorPosition(len(self.field.text()))

    def text(self) -> str:
        return self.field.text()

    def setText(self, value: str) -> None:
        self.field.setText(value)


class Combo(QComboBox):
    """A combobox that draws its own chevron.

    Qt's stock arrow is a themed image, and turning the drop-down's border
    off to flatten the field takes the arrow with it. Drawing two lines is
    less work than shipping an asset, and it keeps the mark the same weight
    as the hairlines around it -- the old build's giveaway was a bevelled
    arrow button welded onto a bordered box.
    """

    ARROW = 9

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(theme.rgb(theme.INK_DIM))
        pen.setWidthF(1.4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)

        right = self.width() - theme.M
        middle = self.height() / 2
        half = self.ARROW / 2
        painter.drawLine(
            QPointF(right - self.ARROW, middle - half + 1),
            QPointF(right - half, middle + half - 1),
        )
        painter.drawLine(
            QPointF(right - half, middle + half - 1),
            QPointF(right, middle - half + 1),
        )


class TabBand(QTabBar):
    """The tab strip, living inside the rebate band.

    `QTabWidget` centres its bar on macOS when the tabs do not fill the
    width, which floats them in the middle of the band with nothing to line
    up against. Fixing the size hint keeps them at the rail's gutter.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setExpanding(False)
        self.setDrawBase(False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)


class Swatch(QPushButton):
    """A flat block of the current colour that opens a colour picker.

    A swatch alone would carry its meaning in colour only, so the button's
    accessible name and tooltip state the hex value: the control still works
    for someone who cannot distinguish the fill, and for a screen reader.
    """

    colour_changed = Signal(str)

    def __init__(
        self,
        colour: str,
        label: str = "Colour",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("Swatch")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._label = label
        self._colour = ""
        self.set_colour(colour, notify=False)
        self.clicked.connect(self._choose)

    @property
    def colour(self) -> str:
        return self._colour

    def set_colour(self, value: str, notify: bool = True) -> None:
        """Adopt a colour, announcing it only if it actually changed.

        Parsed through `pipeline.parse_colour`, so a stored setting or a
        picker result is normalised at this boundary and the widget can
        never hold a colour the renderer would reject.
        """
        normalised = pipeline.parse_colour(value)
        if normalised == self._colour:
            return
        self._colour = normalised
        # Qualified with the type so it outranks the rail's own
        # `#Rail QPushButton` fill; the border still comes from the sheet.
        self.setStyleSheet(f"QPushButton#Swatch {{ background: {normalised}; }}")
        self.setAccessibleName(f"{self._label} {normalised}")
        self.setToolTip(f"{self._label}: {normalised}")
        if notify:
            self.colour_changed.emit(normalised)

    def _choose(self) -> None:
        chosen = QColorDialog.getColor(theme.rgb(self._colour), self, f"Choose {self._label}")
        if chosen.isValid():
            self.set_colour(chosen.name())


class PercentSlider(QWidget):
    """A percentage, set by dragging rather than by typing.

    A spin box asks you to name a number for something you are judging by
    eye. A slider lets you sweep it and watch the preview follow, which is
    what a border width actually is.

    `QSlider` is integer-only, so the value is held in tenths of a percent:
    every value the old spin box could show -- it displayed one decimal --
    round-trips exactly, and 12.5 stays 12.5. The keyboard still moves in
    the sizes a person thinks in, because `singleStep` and `pageStep` are
    set in those units rather than left at the storage resolution: an arrow
    key is half a percent, Page Up five.
    """

    STEPS_PER_PERCENT = 10
    ARROW_PERCENT = 0.5
    PAGE_PERCENT = 5.0

    valueChanged = Signal(float)
    """Every movement, including each pixel of a drag."""

    settled = Signal(float)
    """The value the hand stopped on.

    `valueChanged` is right for anything cheap enough to redo on every
    pixel of a drag; a re-render is not. This fires once the value is one
    the user has actually chosen: on release after a drag, and immediately
    for a change that had no drag to release -- an arrow key, Page Up,
    Home, End, or a programmatic `setValue`. Those produce no release event
    at all, so a settle that waited for one would leave the keyboard unable
    to ask for anything.
    """

    def __init__(
        self,
        label: str,
        value: float,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(theme.S)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, self._steps(pipeline.MAX_PERCENT))
        self.slider.setSingleStep(self._steps(self.ARROW_PERCENT))
        self.slider.setPageStep(self._steps(self.PAGE_PERCENT))
        self.slider.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.slider.setAccessibleName(label)

        self.readout = data_label()
        self.readout.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )
        # Fixed to the widest reading it can ever show, so the row does not
        # shuffle sideways while you drag it.
        widest = f"{pipeline.MAX_PERCENT:.1f}%"
        self.readout.setFixedWidth(QFontMetrics(theme.data_font()).horizontalAdvance(widest) + 4)

        # Visible, not only accessible. This name used to reach
        # `setAccessibleName` and nowhere else, so a screen reader was told
        # which slider this was and a sighted user was not -- two identical
        # rows distinguished by a sentence printed *underneath* them, which
        # you have to read past the control to learn what the control was.
        # The label is what lets that sentence be deleted.
        self.name_label = QLabel(label)
        self.name_label.setObjectName("FieldLabel")
        self.name_label.setFixedWidth(theme.FIELD_LABEL_WIDTH)
        self.name_label.setBuddy(self.slider)

        row.addWidget(self.name_label)
        row.addWidget(self.slider, 1)
        row.addWidget(self.readout)

        # The label names the control; the value belongs to the slider too,
        # because the readout beside it is decoration a screen reader has no
        # reason to associate with anything.
        self.setAccessibleName(label)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFocusProxy(self.slider)

        self.slider.valueChanged.connect(self._changed)
        self.slider.sliderReleased.connect(self._released)
        self._describe()
        self.setValue(value)

    @classmethod
    def _steps(cls, percent: float) -> int:
        return round(percent * cls.STEPS_PER_PERCENT)

    def value(self) -> float:
        return self.slider.value() / self.STEPS_PER_PERCENT

    def setValue(self, percent: float) -> None:
        """Adopt a percentage, clamped to the range the pipeline accepts."""
        steps = min(max(self._steps(percent), self.slider.minimum()), self.slider.maximum())
        self.slider.setValue(steps)

    def minimum(self) -> float:
        return self.slider.minimum() / self.STEPS_PER_PERCENT

    def maximum(self) -> float:
        return self.slider.maximum() / self.STEPS_PER_PERCENT

    def _changed(self, _steps: int) -> None:
        self._describe()
        self.valueChanged.emit(self.value())
        # A change arriving with the handle up had no drag behind it, so
        # there is no release coming and this is already the chosen value.
        if not self.slider.isSliderDown():
            self.settled.emit(self.value())

    def _released(self) -> None:
        """The hand has come off the handle: whatever it landed on is chosen.

        Emitted even when the value ended where it started, which is a
        needless re-render at worst and never a wrong one -- Qt gives no way
        to tell "dragged and returned" from "pressed and let go".
        """
        self.settled.emit(self.value())

    def _describe(self) -> None:
        reading = f"{self.value():.1f} %"
        self.readout.setText(reading)
        self.slider.setAccessibleDescription(reading)
        self.setToolTip(f"{self.accessibleName()}: {reading}")


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
        # `currentIndexChanged` rather than `activated`: the latter is only
        # sent for a genuine user gesture on the popup, which a test cannot
        # simulate via `setCurrentIndex`. `currentIndexChanged` is not "the
        # user picked something", though -- `addItems` on an empty combo
        # fires it too (`currentIndexChanged(0)`, because filling the list
        # is itself an index change), so `set_names` needs the `_quiet`
        # guard. `set_current` uses `setEditText`, which changes no index
        # even when the typed text matches an item exactly -- it only fires
        # `editTextChanged` -- so it is `_quiet` there only for symmetry.
        # A tab that calls `box.setCurrentIndex()` directly, instead of
        # going through `set_current`, would emit `chosen` for a choice
        # nobody made.
        self.box.currentIndexChanged.connect(self._on_activated)
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

        self.delete_button = QPushButton("\u00d7")
        self.delete_button.setObjectName("Secondary")
        self.delete_button.setAccessibleName("Delete this preset")
        self.delete_button.setToolTip("Delete this preset")
        self.delete_button.clicked.connect(self._on_delete)

        # Qt gives every push button an 80px minimum width. On a 320px rail
        # that leaves the two buttons wider than the name they act on, and
        # the name is the part worth reading. Size each to its own text.
        # The save button is measured against its widest wording, not its
        # current one, so swapping "Save" for "Update" does not shove the
        # delete button sideways under the pointer.
        wordings = ((self.save_button, ("Save", "Update")), (self.delete_button, ("\u00d7",)))
        for button, labels in wordings:
            # Measured by asking Qt for each wording rather than by adding a
            # spacing constant to the text width: the real chrome is the
            # stylesheet's `padding: 7px 14px` plus a 1px border, 30px, and
            # the constant said 24 -- so the delete button came out 31px
            # against a 37px hint and clipped its own glyph.
            current = button.text()
            widest = 0
            for label in labels:
                button.setText(label)
                widest = max(widest, button.sizeHint().width())
            button.setText(current)
            button.setFixedWidth(widest)

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

    def _is_usable(self, name: str) -> bool:
        # A name reaching `save_preset` with a `/` or `\` in it would
        # silently corrupt the stored key path -- `settings.clean_name` is
        # the one place that rule lives, so it is asked rather than
        # restated here.
        try:
            settings.clean_name(name)
        except ValueError:
            return False
        return True

    def _sync_buttons(self) -> None:
        """The one place the two buttons' state is decided.

        The button's wording is what stands in for a confirmation dialog:
        it says whether a save will add or replace before it is pressed.
        """
        name = self.current_name()
        known = name in self._names()
        self.save_button.setText("Update" if known else "Save")
        self.save_button.setEnabled(self._is_usable(name))
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
        if not self._is_usable(name):
            return
        self.set_current(name)
        self.saved.emit(name)

    def _on_delete(self) -> None:
        name = self.current_name()
        if name not in self._names():
            return
        self.deleted.emit(name)


class BorderControls(QWidget):
    """The border section of a rail.

    Both tabs need it, and both must present it identically -- switching
    tabs should not re-lay-out the window. Compose additionally sets the gap
    between panels; split additionally chooses whether the detail frames
    carry the border too. Everything is emitted as one whole `FrameStyle`,
    so a consumer never has to reassemble the fields itself.
    """

    style_changed = Signal(object)
    """Every movement of every control, for whatever is cheap to redo."""

    style_settled = Signal(object)
    """The style the user has actually stopped on.

    Both signals carry a whole `FrameStyle`. The split is by cost, not by
    meaning: `style_changed` drives the live overlay, which is a few
    rectangles and can follow a drag pixel by pixel, and `style_settled`
    drives re-rendering the frames, which cannot. A control with nothing to
    drag -- a swatch, a checkbox -- settles the moment it changes.
    """

    def __init__(
        self,
        show_gutter: bool,
        show_detail_toggle: bool,
        parent: QWidget | None = None,
        *,
        # Keyword-only: fourth-positional would let a Compose rail be given
        # the Split list by a caller that miscounted, and omitting it
        # silently is the same mistake with no argument at all to spot.
        scope: str = settings.SPLIT,
        # A composite has no frame 1, so a Compose rail must not offer a
        # control for one. Keyword-only and defaulted off for the same
        # reason `scope` is: a fourth positional is a miscount waiting to
        # happen, and this one would put a split-only control on Compose.
        show_frame1: bool = False,
        # What the gap actually separates, which is not the same thing on
        # both tabs: panels on a composite, frame 1's rows on a split. One
        # control and one stored field, but the label says which -- that is
        # the distinction a sentence underneath used to carry.
        gutter_label: str = "Panel gap",
    ) -> None:
        super().__init__(parent)
        self._quiet = False
        self._scope = scope
        self._presets: dict[str, pipeline.FrameStyle] = {}
        self.gutter_slider: PercentSlider | None = None
        self.gutter_swatch: Swatch | None = None
        self.detail_check: QCheckBox | None = None
        self.frame1_check: QCheckBox | None = None
        self.frame1_section: Disclosure | None = None
        self.frame1_slider: PercentSlider | None = None

        # A word-wrapped label's height is a function of its width, and
        # `QLabel` says so by turning `heightForWidth` on in its size policy.
        # A plain `QWidget` wrapping such labels in its own layout does not,
        # so this section used to report a height measured at some width it
        # was never given, and the rail budgeted from that. Saying it has a
        # `heightForWidth` is what makes the number it reports honest.
        #
        # It is not on its own enough -- see `_pin_help_heights`.
        policy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)

        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)

        column.addWidget(section("Border"))
        column.addSpacing(theme.S)
        self.presets = PresetRow()
        self.presets.chosen.connect(self._on_preset_chosen)
        self.presets.saved.connect(self._on_preset_saved)
        self.presets.deleted.connect(self._on_preset_deleted)
        column.addWidget(self.presets)
        column.addSpacing(theme.S)
        self.border_slider, self.border_swatch, border_row = self._field(
            "Width",
            pipeline.DEFAULT_STYLE.border_percent,
            "Border colour",
            pipeline.DEFAULT_STYLE.border_colour,
        )
        column.addWidget(border_row)
        column.addSpacing(theme.S)
        # One line for the section, not one per control. Every width here is
        # a percent of the short side, which is the one thing a label cannot
        # say; what each slider *is* is now written on the slider.
        column.addWidget(help_label("Widths are a percent of the frame's short side."))

        gutter_row: QWidget | None = None
        if show_gutter:
            self.gutter_slider, self.gutter_swatch, gutter_row = self._field(
                gutter_label,
                pipeline.DEFAULT_STYLE.gutter_percent,
                "Gap colour",
                pipeline.DEFAULT_STYLE.gutter_colour,
            )

        if show_frame1:
            # Everything frame 1 alone decides, in one place that folds away.
            # It was scattered across two sections, each carrying a sentence
            # to re-explain the scope its heading now states once.
            #
            # The gap comes in here on this tab and stays in BORDER on the
            # other, because on a split the gap separates nothing but frame
            # 1's rows -- it is not a border setting at all.
            column.addSpacing(theme.L)
            self.frame1_section = Disclosure("Frame 1")
            body = self.frame1_section.body_layout
            if gutter_row is not None:
                body.addWidget(gutter_row)
                body.addSpacing(theme.S)
            self.frame1_check = QCheckBox("Its own border")
            self.frame1_check.setAccessibleName("Frame 1 has its own border")
            self.frame1_check.toggled.connect(self._on_frame1_toggled)
            body.addWidget(self.frame1_check)
            body.addSpacing(theme.S)
            self.frame1_slider = PercentSlider("Width", pipeline.DEFAULT_STYLE.border_percent)
            self.frame1_slider.setEnabled(False)
            self.frame1_slider.valueChanged.connect(self._emit)
            self.frame1_slider.settled.connect(self._settle)
            body.addWidget(self.frame1_slider)
            body.addSpacing(theme.S)
            # Kept, and only this one: that a tall frame stays mostly border
            # however far this is turned down is genuinely counterintuitive,
            # and no label can carry it.
            body.addWidget(
                help_label("A tall frame stays mostly border however far this goes down.")
            )
            column.addWidget(self.frame1_section)
        elif gutter_row is not None:
            column.addSpacing(theme.M)
            column.addWidget(gutter_row)

        if show_detail_toggle:
            column.addSpacing(theme.M)
            self.detail_check = QCheckBox("Border the detail frames too")
            self.detail_check.setAccessibleName("Border the detail frames too")
            self.detail_check.toggled.connect(self._emit)
            self.detail_check.toggled.connect(self._settle)
            column.addWidget(self.detail_check)

    def _on_frame1_toggled(self, checked: bool) -> None:
        """Reveal the slider, starting from the width already in force.

        Ticking the box must not move the frame -- it says "this one is
        mine now", not "make it different". So the slider adopts the shared
        border first, and only then becomes something you can drag.
        """
        if self.frame1_slider is None:
            return
        if checked:
            self.frame1_slider.setValue(self.border_slider.value())
        self.frame1_slider.setEnabled(checked)
        self._emit()
        self._settle()

    def _field(
        self,
        slider_label: str,
        slider_value: float,
        swatch_label: str,
        swatch_value: str,
    ) -> tuple[PercentSlider, Swatch, QWidget]:
        """One width-and-colour pair, laid out as a row.

        Built twice rather than described twice, so the border and the gap
        cannot drift apart in range, step or spacing.
        """
        holder = QWidget(self)
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(theme.S)

        slider = PercentSlider(slider_label, slider_value)
        slider.valueChanged.connect(self._emit)
        slider.settled.connect(self._settle)

        swatch = Swatch(swatch_value, swatch_label)
        swatch.colour_changed.connect(self._emit)
        swatch.colour_changed.connect(self._settle)

        row.addWidget(slider, 1)
        row.addWidget(swatch)
        return slider, swatch, holder

    def heightForWidth(self, width: int) -> int:
        """How tall this column really is once its help text has wrapped."""
        column = self.layout()
        if column is None:
            return int(super().heightForWidth(width))
        return int(column.heightForWidth(width))

    def resizeEvent(self, event: QResizeEvent) -> None:
        """A new width means a new minimum height, so say so."""
        super().resizeEvent(event)
        if event.oldSize().width() != event.size().width():
            self._pin_help_heights()
            self.updateGeometry()

    def _pin_help_heights(self) -> None:
        """Give each wrapped label a floor equal to the height it needs here.

        Reporting an honest `minimumSizeHint` from this widget is not on its
        own enough: the rail asks its children for a minimum once, while
        this one is still zero-width, and a later answer does not
        retroactively enlarge the space it was given. Pinning the labels
        themselves puts the floor somewhere the layout cannot round down --
        a label with a minimum height is a hard constraint, not a hint.
        """
        for label in self.findChildren(QLabel):
            if label.wordWrap() and label.text() and label.width() > 0:
                label.setMinimumHeight(label.heightForWidth(label.width()))

    def frame_style(self) -> pipeline.FrameStyle:
        """The style the fields currently describe.

        A field this rail does not show falls back to the default rather
        than to zero: hiding the gap control must not silently remove the
        gap from a composite.

        Not `style()`: `QWidget` already has that name for its `QStyle`,
        and shadowing it would mean returning a different type from an
        inherited method -- the sort of thing that is fine until the day
        something asks a widget for its QStyle and gets a border setting.
        """
        return pipeline.FrameStyle(
            border_percent=self.border_slider.value(),
            border_colour=self.border_swatch.colour,
            gutter_percent=(
                self.gutter_slider.value()
                if self.gutter_slider is not None
                else pipeline.DEFAULT_STYLE.gutter_percent
            ),
            gutter_colour=(
                self.gutter_swatch.colour
                if self.gutter_swatch is not None
                else pipeline.DEFAULT_STYLE.gutter_colour
            ),
            border_detail_frames=(
                self.detail_check.isChecked() if self.detail_check is not None else False
            ),
            # None, not the slider's number, while the box is unticked: the
            # slider goes on showing the shared width so that ticking the box
            # starts where you already were instead of moving the frame.
            padded_border_percent=(
                self.frame1_slider.value()
                if self.frame1_check is not None
                and self.frame1_slider is not None
                and self.frame1_check.isChecked()
                else None
            ),
        )

    def set_style(self, style: pipeline.FrameStyle) -> None:
        """Adopt a style without announcing it -- for restoring stored state.

        Restoring is not a user edit, and a caller that saves on
        `style_changed` would otherwise write back what it has just read.
        """
        self._quiet = True
        try:
            self.border_slider.setValue(style.border_percent)
            self.border_swatch.set_colour(style.border_colour)
            if self.gutter_slider is not None:
                self.gutter_slider.setValue(style.gutter_percent)
            if self.gutter_swatch is not None:
                self.gutter_swatch.set_colour(style.gutter_colour)
            if self.detail_check is not None:
                self.detail_check.setChecked(style.border_detail_frames)
            if self.frame1_check is not None and self.frame1_slider is not None:
                # `is not None`, never truthiness: 0 is full bleed, a real
                # choice, and it must not read back as "no choice made".
                wanted = style.padded_border_percent
                self.frame1_check.setChecked(wanted is not None)
                self.frame1_slider.setValue(style.border_percent if wanted is None else wanted)
                self.frame1_slider.setEnabled(wanted is not None)
        finally:
            self._quiet = False

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
        # The box already shows this name when a person picked it from the
        # popup, but saying so again costs nothing and leaves the row
        # honest when the choice arrived any other way.
        self.presets.set_current(name)

    def restore_style(self, style: pipeline.FrameStyle) -> None:
        """Adopt a stored style and name it if it is exactly a preset.

        The list has to be loaded first. Equality is the whole test --
        `FrameStyle` is frozen, so `==` compares every field, and naming a
        preset the settings merely resemble would be worse than naming
        none. Nothing matching leaves the box blank.
        """
        self.set_style(style)
        match = next((name for name, saved in self._presets.items() if saved == style), "")
        self.presets.set_current(match)

    def _on_preset_saved(self, name: str) -> None:
        # `delete_preset` swallows an unusable name itself; saving raises.
        # The row will not emit either for a name `clean_name` rejects, so
        # this is only ever reached by a caller emitting the signal by
        # hand -- but the two handlers should behave the same way.
        try:
            name = settings.clean_name(name)
        except ValueError:
            return
        settings.save_preset(self._scope, name, self.frame_style())
        self.reload_presets()
        self.presets.set_current(name)

    def _on_preset_deleted(self, name: str) -> None:
        settings.delete_preset(self._scope, name)
        self.reload_presets()
        self.presets.set_current("")

    def _emit(self, *_args: object) -> None:
        if self._quiet:
            return
        self.presets.mark_edited()
        self.style_changed.emit(self.frame_style())

    def _settle(self, *_args: object) -> None:
        if self._quiet:
            return
        self.style_settled.emit(self.frame_style())
