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
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPaintEvent, QPixmap
from PySide6.QtWidgets import QSizePolicy, QWidget

from maskingframe.gui import theme
from maskingframe.gui.strip import pil_to_pixmap

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

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pixmap: QPixmap | None = None
        self._aspect = 1.0
        self._positions: tuple[float, ...] = ()
        self._window = 0.0
        self._dragging: int | None = None
        self._grab_offset = 0.0
        self._font: QFont = theme.stencil_font(10, tracking=1.4)
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
        self.update()

    def positions(self) -> tuple[float, ...]:
        return self._positions

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
        painter.setPen(QColor(theme.EDGE))
        painter.drawRect(self.surface_rect().adjusted(0, 0, -1, -1))
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
            painter.setPen(QColor(theme.INK))
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
