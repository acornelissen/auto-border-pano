"""The numbered sources list: the ordering control, drawn as frames.

This is the Qt port of the widget that replaced the Compose tab's
`tk.Listbox`. The Listbox was a raw Tk widget among ttk ones -- a black
rectangle with a hard sunken border, sized `height=4` for a list capped at
three, so one row was always dead space -- and it said nothing about the one
thing that matters here: the order of the rows is the left-to-right order of
the composite.

So each row carries a chinagraph frame number in the same visual language as
the contact strip's. The number is not decoration and it is not an index
label; it *is* the arrangement, and moving a row moves a numbered frame. The
two widgets speak one language on purpose.

Why a `QListWidget` and a delegate rather than a hand-drawn `paintEvent`:
under tkinter this control was a bare `Canvas`, so selection, focus, arrow
keys and hit testing were all hand-written, and macOS Tk still gave it no
accessibility at all. `QListWidget` brings selection, keyboard traversal, a
real focus state and native accessibility with it, and a `QStyledItemDelegate`
still gives the row exactly the marks the design asks for. The only thing
left to write is what a row looks like.

The list holds at most three rows, so there is no scrolling and no
virtualisation here and there should never be any. It draws its empty state
from construction, with no call needed.

Every colour and font comes from `theme`. No rounded corners, no shadows and
no animation: a light table and a film rebate are both hard-edged.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QModelIndex, QPersistentModelIndex, QRect, QSize, Qt, Signal
from PySide6.QtGui import QKeyEvent, QPainter, QPaintEvent
from PySide6.QtWidgets import (
    QListWidget,
    QListWidgetItem,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QWidget,
)

from auto_border_pano.gui import theme

BAR_WIDTH = 4
"""The chinagraph edge mark down the left of a row. Thin: it marks, it does
not fill."""

NUMBER_COLUMN = 26
"""Width reserved for the frame number, so the filenames line up."""

PAD_X = theme.S
PAD_Y = theme.S

NAME_ROW = 18
DIMENSION_ROW = 16
ROW_HEIGHT = PAD_Y + NAME_ROW + DIMENSION_ROW
"""Two lines per row: the filename, then what the machine measured about it.

The widget's height is derived from this, not fixed at four rows -- the
Listbox's dead fourth row is the specific thing being fixed.
"""

EMPTY_HEIGHT = 2 * ROW_HEIGHT
"""Enough for the empty caption to wrap onto two lines in the rail."""

EMPTY_CAPTION = "Add two sources for a diptych, three for a triptych."

BORDER = 1
"""One device pixel, which is a thing Qt can actually draw."""

PENDING_DIMENSIONS = "reading..."
"""Shown until the caller's header read lands. Dimensions come off the GUI
thread, so a row must render before it knows its own size."""


@dataclass(frozen=True)
class Source:
    """One row: a file, and its pixel size once somebody has read it.

    Frozen because a row is a fact about a file, not a mutable widget model.
    `size` is optional because the Compose tab reads image headers off the
    GUI thread and hands them over later.
    """

    path: str
    size: tuple[int, int] | None = None

    @property
    def name(self) -> str:
        return Path(self.path).name

    @property
    def dimensions(self) -> str:
        """The measured size, in the same `4000 x 1700` shape the rest of the
        app uses, or a placeholder while it is still being read."""
        if self.size is None:
            return PENDING_DIMENSIONS
        return f"{self.size[0]} × {self.size[1]}"  # noqa: RUF001


class _RowDelegate(QStyledItemDelegate):
    """How one numbered frame is drawn.

    The row is the only part of a `QListWidget` that had to be written by
    hand, and it is the only part that carries any design.
    """

    def sizeHint(
        self,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> QSize:
        return QSize(0, ROW_HEIGHT)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        source = index.data(Qt.ItemDataRole.UserRole)
        if not isinstance(source, Source):  # pragma: no cover - defensive
            super().paint(painter, option, index)
            return

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        rect = option.rect
        selected = bool(option.state & QStyle.StateFlag.State_Selected)

        painter.fillRect(rect, theme.rgb(theme.PANEL if selected else theme.WELL))

        # The edge mark. Chinagraph on the selected row, a hairline elsewhere
        # -- it is always there, so the row reads as a frame either way.
        painter.fillRect(
            QRect(rect.left() + PAD_X, rect.top() + 2, BAR_WIDTH, rect.height() - 4),
            theme.rgb(theme.CHINAGRAPH if selected else theme.EDGE),
        )

        left = rect.left() + PAD_X + BAR_WIDTH + PAD_X
        name_row = QRect(left, rect.top(), rect.width() - left, NAME_ROW + PAD_Y)
        painter.setFont(theme.stencil_font(11, tracking=1.4))
        painter.setPen(theme.rgb(theme.CHINAGRAPH))
        painter.drawText(
            name_row,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            str(index.row() + 1),
        )

        name_left = left + NUMBER_COLUMN
        available = rect.right() - name_left - PAD_X
        # Mono, because it is the file you chose rather than what we call it.
        painter.setFont(theme.data_font(12))
        painter.setPen(theme.rgb(theme.INK))
        # Elided from the front, because these filenames share a long prefix
        # and differ in their last few characters, and truncated rather than
        # wrapped, because a taller row would break the numbering's rhythm.
        painter.drawText(
            QRect(name_left, rect.top(), available, NAME_ROW + PAD_Y),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            painter.fontMetrics().elidedText(source.name, Qt.TextElideMode.ElideLeft, available),
        )

        painter.setFont(theme.data_font(11))
        painter.setPen(theme.rgb(theme.INK_DIM))
        painter.drawText(
            QRect(name_left, rect.top() + PAD_Y + NAME_ROW, available, DIMENSION_ROW),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            source.dimensions,
        )
        painter.restore()


class SourcesList(QListWidget):
    """A short list of numbered sources, in the order they will be placed.

    A `QListWidget` rather than a bare widget with a `paintEvent`: keyboard
    selection, the focus state and the accessibility tree all come with it,
    and the tkinter version had to hand-write the first two and never had the
    third at all.
    """

    selection_changed = Signal(object)
    """The selected row index, or None. Fires on programmatic moves too --
    the Compose tab drives its Up/Down/Remove states off this, and a row
    removed under the cursor changes what those buttons may do."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Sources")
        self.setItemDelegate(_RowDelegate(self))
        self.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.setUniformItemSizes(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        # Three rows, hard capped. There is nothing to scroll and nothing to
        # virtualise, and a scrollbar appearing would be a bug.
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QListWidget.Shape.NoFrame)
        self.setStyleSheet(
            f"""
            QListWidget#Sources {{
                background: {theme.WELL};
                border: {BORDER}px solid {theme.EDGE};
                outline: none;
            }}
            QListWidget#Sources:focus {{ border: {BORDER}px solid {theme.CHINAGRAPH}; }}
            """
        )

        self._items: list[Source] = []
        self._rebuilding = False
        self.currentRowChanged.connect(self._on_current_row_changed)
        # The empty state exists from construction. No call required.
        self._resize_to_rows()

    # --- public API ---------------------------------------------------------

    @property
    def count(self) -> int:  # type: ignore[override]
        """How many rows there are.

        This shadows `QListWidget.count()`, which is a method meaning the same
        thing. That is safe because `count()` is not virtual: Qt's own code
        calls the C++ slot directly and never looks the name up on the Python
        object. Nothing in this module calls `self.count()` either.
        """
        return len(self._items)

    @property
    def items(self) -> tuple[Source, ...]:  # type: ignore[override]
        """What the rows currently show. A tuple, so a caller reading the
        rendered state cannot quietly mutate it behind the widget."""
        return tuple(self._items)

    @property
    def selected_index(self) -> int | None:
        """The row the ordering buttons act on, or None if nothing is picked."""
        row = self.currentRow()
        return None if row < 0 else row

    def set_items(self, items: Sequence[Source]) -> None:
        """Replace every row, keeping the selection where that still means
        something.

        A reorder is a `set_items` with the same number of rows, so the
        selection is kept as-is there: the user picked position 2, and after
        Down they should still be on the row they moved. A shorter list clamps
        to the last row; an empty one clears.
        """
        previous = self.selected_index
        self._items = list(items)

        wanted = previous
        if not self._items:
            wanted = None
        elif previous is not None and previous >= len(self._items):
            wanted = len(self._items) - 1

        # Rebuilding drives `currentRowChanged` through -1 and back on its
        # own. Silence it and announce once, against the value the caller
        # last saw, so a reorder that lands on the same row says nothing.
        self._rebuilding = True
        try:
            self.clear()
            for position, source in enumerate(self._items):
                self.addItem(self._build_row(position, source))
            self.setCurrentRow(-1 if wanted is None else wanted)
        finally:
            self._rebuilding = False

        self._resize_to_rows()
        self._announce(previous)

    def select(self, index: int | None) -> None:
        """Move the selection programmatically. Out of range clears it."""
        if index is None or not 0 <= index < len(self._items):
            self.setCurrentRow(-1)
        else:
            self.setCurrentRow(index)

    # --- internals ----------------------------------------------------------

    def _build_row(self, position: int, source: Source) -> QListWidgetItem:
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, source)
        # The delegate draws everything, so the accessible name is the only
        # text the row has. Say the number out loud: the order is the point.
        item.setData(
            Qt.ItemDataRole.AccessibleTextRole,
            f"{position + 1}. {source.name}, {source.dimensions}",
        )
        item.setSizeHint(QSize(0, ROW_HEIGHT))
        return item

    def _resize_to_rows(self) -> None:
        """Height follows the rows. The Listbox's dead fourth row is the
        specific thing being fixed, so nothing here is fixed at four."""
        rows = ROW_HEIGHT * len(self._items) if self._items else EMPTY_HEIGHT
        self.setFixedHeight(rows + 2 * BORDER)
        self.setAccessibleDescription(EMPTY_CAPTION if not self._items else "")

    def _on_current_row_changed(self, _row: int) -> None:
        if not self._rebuilding:
            self.selection_changed.emit(self.selected_index)

    def _announce(self, previous: int | None) -> None:
        if previous != self.selected_index:
            self.selection_changed.emit(self.selected_index)

    # --- behaviour ----------------------------------------------------------

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Arrow keys, clamped rather than wrapped.

        Qt clamps at both ends already. The one case it gets wrong for this
        widget is the first press with nothing selected: Qt lands on row 0
        whichever way you pressed, where Up should land on the near end.
        Wrapping is deliberately not offered -- in a list whose order is its
        meaning it is disorienting, and three rows have obvious ends.
        """
        if event.key() == Qt.Key.Key_Up and self.selected_index is None and self._items:
            self.setCurrentRow(len(self._items) - 1)
            event.accept()
            return
        super().keyPressEvent(event)

    def paintEvent(self, event: QPaintEvent) -> None:
        """The rows, and the empty state when there are none.

        Drawn in the widget rather than left as a blank box: an empty list is
        the moment the user most needs telling what to do.
        """
        super().paintEvent(event)
        if self._items:
            return
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.setFont(theme.data_font(11))
        painter.setPen(theme.rgb(theme.INK_DIM))
        painter.drawText(
            self.viewport().rect().adjusted(PAD_X, PAD_Y, -PAD_X, -PAD_Y),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap),
            EMPTY_CAPTION,
        )
