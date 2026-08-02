"""The ribbon: the whole panorama once, with a window per detail frame.

The contact strip shows what each frame *is*; the ribbon shows where each
one *came from*, which is the thing you cannot see by looking at the frames
alone -- how close two crops are, and what the panorama has left over.

Fixed height with the picture fitted inside it, never cropped. A height
that followed the picture would be 275px for a 2.3:1 panorama and a 49px
sliver for a 13:1 one, and the whole tab would jump every time a different
file was loaded.

Presentation only, like `strip.py`. It knows a picture, how wide one window
is as a fraction of the panorama, and where the windows are. It has never
heard of a FrameStyle, an AspectRatio or a file.
"""

import math
from collections.abc import Sequence

from PIL import Image
from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFocusEvent,
    QFont,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPixmap,
)
from PySide6.QtWidgets import QSizePolicy, QWidget

from maskingframe.gui import theme
from maskingframe.gui.strip import FOCUS_EDGE, draw_edge, pil_to_pixmap

RIBBON_HEIGHT = 240
"""Tall enough to judge a crop by, short enough to leave the strip the room.

Set from the shape this project actually scans. At 2.4:1 the height binds,
so the picture comes out 2.4 * (240 - 2 * MARGIN) = 518px wide -- well over
half a ribbon in a 1280-wide window, which is enough to see where two crops
overlap. At 96 the same panorama was 202px, a thumbnail. The strip below
loses what the ribbon takes: at this height it still gets ~200px frames in
two rows, against a 72px floor.
"""

MARGIN = theme.M
"""Surround between the picture and the edge of the ribbon's own surface.

`theme.M` rather than `theme.S` so the ribbon's picture and the contact
strip's film start at the same distance from the left.
"""

DIM = QColor(theme.INK)
"""The wash over everything no frame covers. Alpha is set where it is used."""

DIM_ALPHA = 110

HANDLE = 2
"""The window's edge. A hairline, like every other edge in this interface."""


class FrameRibbon(QWidget):
    """The panorama with a draggable window per detail frame."""

    frame_moved = Signal(int, float)
    """(frame index, wanted left edge as a fraction of the width) on every
    movement of a drag. Cheap work only -- this drives the overlay, not a
    re-render.

    What the hand asked for, not what the plan becomes. Keeping the frames
    in order needs the source's size and the target ratio, and the ribbon
    knows neither; the tab owns that rule so the contact strip's drag can go
    through the very same one. Whatever comes back arrives via `set_plan`.
    """

    frame_settled = Signal(int)
    """Once, when the hand stops. This is what a re-render hangs off, and it
    is the same split `PercentSlider` makes for the border controls."""

    frame_nudged = Signal(int, int)
    """(frame index, step count). A count, not a distance: how far a step
    moves is policy, and the tab is the only thing that knows what a percent
    of this panorama is. Shift is ten steps; Home and End are a hundred,
    which spans the whole width and lets the tab's clamp do the rest."""

    selection_changed = Signal(int)
    """(frame index) when the keys move the selection. The tab owns which
    frame is selected -- the strip marks the same one -- so this asks rather
    than decides."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pixmap: QPixmap | None = None
        self._aspect = 1.0
        self._positions: tuple[float, ...] = ()
        self._window = 0.0
        self._dragging: int | None = None
        self._grab_offset = 0.0
        self._font: QFont = theme.stencil_font(10, tracking=1.4)
        self._selected: int | None = None
        # Its own plain identity, and nothing more. What is selected, and
        # where along the panorama it sits, is the rail's sentence, and the
        # tab pushes that verbatim into `setAccessibleDescription` -- so the
        # two views and the screen reader say one thing, and the ribbon does
        # not have to know what a percent of a panorama is.
        self.setAccessibleName("Panorama overview")
        # Kept rather than read back from `hasFocus()`, for the reason
        # `ContactStrip` gives: Qt only reports focus on a widget whose
        # window is active, and the mark is checked by painting into an image.
        self._focused = False
        # Reachable by Tab and by click. A window is a control, and a control
        # you can only reach with a pointer is not reachable at all.
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFixedHeight(RIBBON_HEIGHT)
        # Only the surface behind the picture is painted, so whatever the
        # widget stands on has to show through the rest of the cell.
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    # --- what it is showing -------------------------------------------------

    def set_source(self, image: Image.Image | None) -> None:
        """The panorama to draw, or nothing."""
        if image is None:
            self._pixmap = None
            self._aspect = 1.0
        else:
            self._pixmap = pil_to_pixmap(image)
            self._aspect = image.width / max(1, image.height)
        self.update()

    def set_plan(self, positions: Sequence[float], window_fraction: float) -> None:
        """Where the frames are and how wide one is. Emits nothing.

        Silent on purpose: a tab that saves on `frame_moved` would
        otherwise write back what it has just read.
        """
        self._positions = tuple(positions)
        self._window = max(0.0, min(1.0, window_fraction))
        # A selection that outlives the plan it points into is the actual
        # defect: every reader (paint, marked_rect, the key handler) trusts
        # `_selected` to index `_positions`, so the plan changing is the one
        # place to drop a selection the new plan can no longer support.
        if self._selected is not None and self._selected >= len(self._positions):
            self._selected = None
        self.update()

    def positions(self) -> tuple[float, ...]:
        return self._positions

    def set_selected(self, index: int | None) -> None:
        """Mark one frame, or none. Emits nothing.

        Silent for the same reason `set_plan` is: the tab holds the one
        copy, and a widget that announced what it had just been told would
        write it straight back.
        """
        self._selected = index
        self.update()

    def selected(self) -> int | None:
        return self._selected

    def marked_rect(self) -> QRect:
        """Where the selection is drawn, or a null rect. Exposed so the
        marking can be checked without sampling pixels."""
        if self._selected is None or not 0 <= self._selected < len(self._positions):
            return QRect()
        return self.window_rects()[self._selected]

    def edge_colour(self, index: int) -> str:
        """The colour window `index`'s edge is drawn in.

        The decision itself, exposed: `marked_rect` says only where the mark
        goes, and a test comparing it with `window_rects` cannot tell whether
        anything was drawn in chinagraph at all.
        """
        return theme.CHINAGRAPH if index == self._selected else theme.INK

    # --- geometry, exposed so it can be checked without sampling pixels -----

    def picture_rect(self) -> QRect:
        """Where the panorama lands, fitted inside the ribbon.

        Pinned to the top left rather than centred: the ribbon's surface
        reaches only as far as the picture, so there is nothing to centre it
        in, and a left edge shared with the strip below reads as one stack.
        """
        if self._pixmap is None:
            return QRect()
        available_width = max(1, self.width() - 2 * MARGIN)
        available_height = max(1, self.height() - 2 * MARGIN)
        width = available_width
        height = max(1, math.floor(width / self._aspect + 0.5))
        if height > available_height:
            height = available_height
            width = max(1, math.floor(height * self._aspect + 0.5))
        return QRect(MARGIN, MARGIN, width, height)

    def surface_rect(self) -> QRect:
        """The ribbon's own background: the picture plus its surround.

        Never the whole widget. A pale slab running out past the picture
        reads as an empty panel, which is the same reason `ContactStrip.span`
        stops at the film.
        """
        picture = self.picture_rect()
        if picture.isNull():
            return QRect()
        return picture.adjusted(-MARGIN, -MARGIN, MARGIN, MARGIN)

    def window_rects(self) -> list[QRect]:
        """One rectangle per frame, in widget pixels."""
        picture = self.picture_rect()
        if picture.isNull() or not self._positions:
            return []
        span = picture.width()
        width = max(1, math.floor(self._window * span + 0.5))
        return [
            QRect(
                picture.left() + math.floor(position * span + 0.5),
                picture.top(),
                width,
                picture.height(),
            )
            for position in self._positions
        ]

    # --- dragging -----------------------------------------------------------

    def _window_at(self, point: QPoint) -> int | None:
        """Which window the cursor is in, latest first.

        Latest first so that when two frames overlap the one drawn on top is
        the one you grab -- anything else would feel like the interface
        picking a different frame from the one under the cursor.
        """
        for index in reversed(range(len(self.window_rects()))):
            if self.window_rects()[index].contains(point):
                return index
        return None

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        point = event.position().toPoint()
        index = self._window_at(point)
        if index is None:
            return
        picture = self.picture_rect()
        grabbed = (point.x() - picture.left()) / max(1, picture.width())
        self._dragging = index
        self._grab_offset = grabbed - self._positions[index]

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._dragging is None:
            return
        picture = self.picture_rect()
        point = event.position().toPoint()
        wanted = (point.x() - picture.left()) / max(1, picture.width()) - self._grab_offset
        self.frame_moved.emit(self._dragging, wanted)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._dragging is None:
            return
        index = self._dragging
        self._dragging = None
        self.frame_settled.emit(index)

    def edge_pen(self) -> tuple[str, int]:
        """The colour and weight of the ribbon's own edge.

        INK when it holds focus, as every field in the app already does, and
        as the contact strip below does. Chinagraph is left to say which
        window is picked -- focus and selection are different states and can
        be present at once.
        """
        if self._focused:
            return theme.INK, FOCUS_EDGE
        return theme.EDGE, 1

    def focusInEvent(self, event: QFocusEvent) -> None:
        self._focused = True
        # Nothing is marked until the user asks for it; asking for it is
        # exactly what taking focus is.
        announce = self._selected is None and bool(self._positions)
        if announce:
            self._selected = 0
        super().focusInEvent(event)
        self.update()
        # Announced, not kept to itself: a frame marked here and nowhere
        # else would be a selection carried by colour alone until the user
        # happened to press a key. `set_selected` is silent, so the tab
        # adopting this and echoing it back cannot loop.
        if announce:
            self.selection_changed.emit(0)

    def focusOutEvent(self, event: QFocusEvent) -> None:
        self._focused = False
        super().focusOutEvent(event)
        self.update()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if not self._positions:
            super().keyPressEvent(event)
            return
        if self._selected is None:
            # Same as taking focus, and announced for the same reason: this
            # is reachable when the plan arrives after the focus did.
            self._selected = 0
            self.selection_changed.emit(0)
        key = event.key()
        coarse = event.modifiers() & Qt.KeyboardModifier.ShiftModifier
        steps: dict[int, int] = {
            Qt.Key.Key_Left: -10 if coarse else -1,
            Qt.Key.Key_Right: 10 if coarse else 1,
            Qt.Key.Key_Home: -100,
            Qt.Key.Key_End: 100,
        }
        step = steps.get(key)
        if step is not None:
            self.frame_nudged.emit(self._selected, step)
            return
        if key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            wanted = self._selected + (1 if key == Qt.Key.Key_Down else -1)
            # Stops rather than wraps: a selection that jumped from the last
            # frame back to the first would lose your place on a picture you
            # are reading left to right.
            if 0 <= wanted < len(self._positions):
                self._selected = wanted
                self.update()
                self.selection_changed.emit(wanted)
            return
        super().keyPressEvent(event)

    # --- drawing ------------------------------------------------------------

    def sizeHint(self) -> QSize:
        return QSize(480, RIBBON_HEIGHT)

    def paintEvent(self, _event: QPaintEvent) -> None:
        painter = QPainter(self)
        if self._pixmap is None:
            # Nothing loaded is nothing to show. An empty band the width of
            # the tab would be a panel with no content in it.
            return
        picture = self.picture_rect()
        # Panel and hairline, exactly as the contact strip draws its sheet:
        # the two are the same kind of object lying on the same table.
        painter.fillRect(self.surface_rect(), QColor(theme.PANEL))
        colour, width = self.edge_pen()
        draw_edge(painter, self.surface_rect(), colour, width)
        painter.drawPixmap(picture, self._pixmap)

        # Everything no frame covers goes under a wash, so the windows read
        # as the part of the picture that will actually be printed.
        wash = QColor(DIM)
        wash.setAlpha(DIM_ALPHA)
        windows = self.window_rects()
        for band in _uncovered(picture, windows):
            painter.fillRect(band, wash)

        painter.setFont(self._font)
        for index, window in enumerate(windows):
            painter.setPen(QColor(self.edge_colour(index)))
            for offset in range(HANDLE):
                painter.drawRect(window.adjusted(offset, offset, -offset - 1, -offset - 1))
            painter.setPen(QColor(theme.CHINAGRAPH))
            painter.drawText(
                window.adjusted(theme.S // 2, 1, 0, 0),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                str(index + 2),
            )
        painter.end()


def _uncovered(picture: QRect, windows: Sequence[QRect]) -> list[QRect]:
    """The parts of the picture no window covers.

    Merged first, because windows may overlap and washing an overlap twice
    would make it darker than the rest of the dimmed area.
    """
    if not windows:
        return [picture] if not picture.isNull() else []
    merged: list[list[int]] = []
    for window in sorted(windows, key=lambda w: w.left()):
        if merged and window.left() <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], window.right())
        else:
            merged.append([window.left(), window.right()])

    bands: list[QRect] = []
    edge = picture.left()
    for start, end in merged:
        if start > edge:
            bands.append(QRect(edge, picture.top(), start - edge, picture.height()))
        edge = max(edge, end + 1)
    if edge <= picture.right():
        bands.append(QRect(edge, picture.top(), picture.right() - edge + 1, picture.height()))
    return bands
