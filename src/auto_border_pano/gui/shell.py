"""The skeleton both tabs are built on.

There is one product here, not two. Both rails carry the same sections in
the same order -- subject, then FORMAT, then DESTINATION, then the primary
action -- so switching tabs does not re-lay-out the window.

Presentation only, like `theme`. Nothing here knows what a panorama is.
"""

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from auto_border_pano.gui import theme


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
