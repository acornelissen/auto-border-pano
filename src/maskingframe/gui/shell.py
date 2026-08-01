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
    QSizePolicy,
    QSlider,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from maskingframe import pipeline
from maskingframe.gui import theme

STALE_PREVIEW = "Settings changed. Press Preview to render them."
"""What both tabs say when a render is dropped for no longer matching.

A preview vanishing as you drag a slider reads as a glitch unless
something accounts for it. It is a plain statement, in the help voice, not
an error -- nothing has gone wrong and there is nothing to fix.
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

        self.rail = QWidget(self)
        self.rail.setObjectName("Rail")
        self.rail.setFixedWidth(theme.RAIL_WIDTH)
        self.rail_layout = QVBoxLayout(self.rail)
        self.rail_layout.setContentsMargins(theme.L, theme.L, theme.L, theme.L)
        self.rail_layout.setSpacing(0)

        self.table = QWidget(self)
        self.table.setObjectName("Table")
        self.table_layout = QVBoxLayout(self.table)
        self.table_layout.setContentsMargins(theme.L, theme.L, theme.L, theme.L)
        self.table_layout.setSpacing(0)

        row.addWidget(self.rail)
        row.addWidget(self.table, 1)


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
        widest = f"{pipeline.MAX_PERCENT:.1f} %"
        self.readout.setFixedWidth(QFontMetrics(theme.data_font()).horizontalAdvance(widest) + 4)

        row.addWidget(self.slider, 1)
        row.addWidget(self.readout)

        # The label names the control; the value belongs to the slider too,
        # because the readout beside it is decoration a screen reader has no
        # reason to associate with anything.
        self.setAccessibleName(label)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFocusProxy(self.slider)

        self.slider.valueChanged.connect(self._changed)
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

    def _describe(self) -> None:
        reading = f"{self.value():.1f} %"
        self.readout.setText(reading)
        self.slider.setAccessibleDescription(reading)
        self.setToolTip(f"{self.accessibleName()}: {reading}")


class BorderControls(QWidget):
    """The border section of a rail.

    Both tabs need it, and both must present it identically -- switching
    tabs should not re-lay-out the window. Compose additionally sets the gap
    between panels; split additionally chooses whether the detail frames
    carry the border too. Everything is emitted as one whole `FrameStyle`,
    so a consumer never has to reassemble the fields itself.
    """

    style_changed = Signal(object)

    def __init__(
        self,
        show_gutter: bool,
        show_detail_toggle: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._quiet = False
        self.gutter_slider: PercentSlider | None = None
        self.gutter_swatch: Swatch | None = None
        self.detail_check: QCheckBox | None = None

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
        self.border_slider, self.border_swatch, border_row = self._field(
            "Border width",
            pipeline.DEFAULT_STYLE.border_percent,
            "Border colour",
            pipeline.DEFAULT_STYLE.border_colour,
        )
        column.addWidget(border_row)
        column.addSpacing(theme.S)
        column.addWidget(
            help_label("Percent of the frame's short side, so it reads the same at every ratio.")
        )

        if show_gutter:
            column.addSpacing(theme.M)
            self.gutter_slider, self.gutter_swatch, gutter_row = self._field(
                "Gap width",
                pipeline.DEFAULT_STYLE.gutter_percent,
                "Gap colour",
                pipeline.DEFAULT_STYLE.gutter_colour,
            )
            column.addWidget(gutter_row)
            column.addSpacing(theme.S)
            column.addWidget(help_label("The gap between the panels."))

        if show_detail_toggle:
            column.addSpacing(theme.M)
            self.detail_check = QCheckBox("Border the detail frames too")
            self.detail_check.setAccessibleName("Border the detail frames too")
            self.detail_check.toggled.connect(self._emit)
            column.addWidget(self.detail_check)

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

        swatch = Swatch(swatch_value, swatch_label)
        swatch.colour_changed.connect(self._emit)

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
        finally:
            self._quiet = False

    def _emit(self, *_args: object) -> None:
        if self._quiet:
            return
        self.style_changed.emit(self.frame_style())
