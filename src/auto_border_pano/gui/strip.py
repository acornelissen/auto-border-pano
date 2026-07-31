"""The contact strip: one widget holding every frame of a run.

This is the Qt port of `gui/strip.py`, and it is the stage's signature
element. It replaces four disconnected sunken boxes with a single object --
frames butted together on one continuous strip, each carrying its frame
number in chinagraph above and its role stencilled beneath. The numbering
is earned rather than decorative: frame 1 is the whole panorama and 2..N
are its details, in order.

Three things carry over from the tkinter build because they were design
decisions, not toolkit workarounds:

* The strip is pale, not black. A black slab this size reads as a hole cut
  in the light table. What should be dark is the photograph, so each frame
  sits in an aperture with a one-pixel film-base hairline and nothing
  heavier.
* No drop shadows, no rounded corners, no animation. The direction is a
  light table and film rebate, both hard-edged. Qt makes all three trivial;
  a toolkit removing a constraint is not a reason to spend it.
* The empty state is drawn from construction, with no call needed. That is
  the point of the widget: the old preview pane built its container and
  never populated it, so the largest element in the window was a void with
  nothing in it, not even a caption.

Two things are genuinely different under Qt:

* The strip is the widget. There is no `.canvas` wrapper and no
  `set_available_width`; a Qt widget learns its size from `resizeEvent` and
  states its appetite through `sizeHint`, so nobody has to tell it.
* Captions are elided with `QFontMetrics.elidedText` rather than measured
  character by character. In the tkinter build the hand-rolled version was
  only applied sometimes, which is how "FRAME 1 . WHOLE PANORAMA" came to
  run straight through frame 2's caption.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import (
    QFont,
    QFontMetrics,
    QImage,
    QPainter,
    QPaintEvent,
    QPixmap,
    QResizeEvent,
)
from PySide6.QtWidgets import QSizePolicy, QWidget

from auto_border_pano.gui import theme

EDGE = theme.M
"""Margin to the left and right of the outermost frames."""

GUTTER = theme.S
"""Gap between two butted frames. Small: they read as one strip."""

NUMBER_ROW = 20
STENCIL_ROW = 20
TOP = theme.S
BOTTOM = theme.S

CHROME_PX = TOP + NUMBER_ROW + STENCIL_ROW + BOTTOM
"""Everything in a frame's column that is not the photograph."""

MIN_FRAME_PX = 72
MAX_FRAME_PX = 260
"""Frames size from the space actually available, between these bounds.

A constant maximum is why a working run once showed postage stamps in a
pane 540pt tall. The opposite failure is just as bad: sizing a single frame
from a wide column made one frame the size of the column. A frame is a
thumbnail of a run, not the run.
"""

APERTURE = 1
"""Hairline around a frame's image, drawn whether or not there is a
photograph in it yet -- an unexposed strip should still read as film."""

DEFAULT_FRAME_COUNT = 4
"""What an unexposed strip shows before anything is loaded.

Four is the commonest run -- one whole frame plus three details -- and the
count is only a drawing, so being wrong about it costs nothing.
"""

EMPTY_CAPTION = "NOTHING ON THE STRIP YET"
UNREADABLE_CAPTION = "UNREADABLE"


def pil_to_pixmap(image: Image.Image) -> QPixmap:
    """A `QPixmap` of `image`, converted through raw RGB888 bytes.

    Deliberately not `PIL.ImageQt`: that module picks its Qt binding by
    probing what happens to be importable, so it silently changes behaviour
    depending on the environment, and it is an optional part of Pillow.
    Three lines of explicit conversion have no such ambiguity. The `.copy()`
    matters -- a `QImage` built over a Python bytes object does not own its
    pixels, and dropping the buffer would leave the pixmap reading freed
    memory.
    """
    rgb = image if image.mode == "RGB" else image.convert("RGB")
    width, height = rgb.size
    frame = QImage(
        rgb.tobytes("raw", "RGB"),
        width,
        height,
        3 * width,
        QImage.Format.Format_RGB888,
    ).copy()
    return QPixmap.fromImage(frame)


def _bounded(image: Image.Image) -> Image.Image:
    """A copy no larger than the biggest frame the strip will ever draw.

    Bounded once, on the way in. A source can be 132MP, and a resize must
    never send the original back through the resampler.
    """
    copied = image.copy()
    copied.thumbnail((MAX_FRAME_PX, MAX_FRAME_PX), Image.Resampling.LANCZOS)
    return copied


@dataclass
class _Frame:
    """One cell of the strip. `source` is the only state that matters."""

    title: str = ""
    source: QPixmap | None = None
    unreadable: bool = False
    scaled: QPixmap | None = None
    scaled_at: int = 0

    def at(self, size: int) -> QPixmap | None:
        """The thumbnail at `size`, rescaled from the bounded copy only when
        the size has actually changed."""
        if self.source is None or size <= 0:
            return None
        if self.scaled is None or self.scaled_at != size:
            self.scaled = self.source.scaled(
                size,
                size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.scaled_at = size
        return self.scaled


class ContactStrip(QWidget):
    """A row of numbered frames on one continuous strip."""

    def __init__(self, parent: QWidget | None = None, frames: int = DEFAULT_FRAME_COUNT) -> None:
        super().__init__(parent)
        self._font: QFont = theme.stencil_font(10, tracking=1.6)
        self._metrics = QFontMetrics(self._font)
        self._frames: list[_Frame] = [_Frame() for _ in range(max(frames, 1))]
        self._errors: list[str] = []
        self._frame_size = MAX_FRAME_PX
        # Vertically Maximum, never Expanding. The strip is an object lying
        # on the light table, not a panel filling it: painted over a whole
        # column it becomes a large pale box with a thin row of pictures
        # floating in the middle, which is the same "big box mostly
        # containing nothing" the strip exists to replace.
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
        self._remeasure()

    # --- public API ---------------------------------------------------------

    @property
    def frame_count(self) -> int:
        return len(self._frames)

    @property
    def errors(self) -> list[str]:
        return self._errors

    @property
    def frame_size(self) -> int:
        """Side of a frame's image area, in points. Derived, never constant."""
        return self._sync()

    @property
    def span(self) -> int:
        """How far the strip's own background reaches.

        As long as the film in it, never the full column width: a pale tail
        beyond the last frame reads as an unfinished panel, not a strip.
        """
        count = len(self._frames)
        return 2 * EDGE + count * (self.frame_size + GUTTER) - GUTTER

    def set_frames(self, titles: Sequence[str]) -> None:
        """Lay out one frame per title, discarding everything from the last
        run. The count varies with the ratio and the panorama, so this is
        called on every run and must leave nothing stale behind."""
        self._frames = [_Frame(title=title.upper()) for title in titles] or [_Frame()]
        self._errors = []
        self._remeasure()

    def show_paths(self, paths: Sequence[Path]) -> None:
        """Load a thumbnail per frame from disk."""
        self._errors = []
        for index, path in enumerate(paths):
            if index >= len(self._frames):
                break
            self._load(index, path)
        self._remeasure()

    def show_images(self, images: Sequence[Image.Image]) -> None:
        """Show already-loaded images, one per frame."""
        self._errors = []
        for frame, image in zip(self._frames, images, strict=True):
            frame.source = pil_to_pixmap(_bounded(image))
            frame.scaled = None
            frame.unreadable = False
        self._remeasure()

    def mark_written(self, index: int, path: Path) -> None:
        """Expose one frame. Progress is the strip filling in, not a bar."""
        self._load(index, path)
        self._remeasure()

    def mark_unreadable(self, index: int, reason: str) -> None:
        """Mark a frame whose file will not decode, keeping the reason.

        A missing file counts as unreadable. Drawing it as an empty frame
        would report a failure as an absence.
        """
        if not 0 <= index < len(self._frames):
            return
        frame = self._frames[index]
        frame.source = None
        frame.scaled = None
        frame.unreadable = True
        self._errors.append(reason)
        self._remeasure()

    # --- introspection, for tests and status lines --------------------------

    def pixmap_at(self, index: int) -> QPixmap | None:
        if not 0 <= index < len(self._frames):
            return None
        return self._frames[index].at(self.frame_size)

    def caption_at(self, index: int) -> str:
        """The stencil as it will actually be painted, elided to its frame."""
        if not 0 <= index < len(self._frames):
            return ""
        return self._elide(self._frames[index].title)

    def is_unreadable(self, index: int) -> bool:
        return 0 <= index < len(self._frames) and self._frames[index].unreadable

    @property
    def exposed(self) -> int:
        return sum(1 for frame in self._frames if frame.source is not None)

    # --- loading ------------------------------------------------------------

    def _load(self, index: int, path: Path) -> None:
        if not 0 <= index < len(self._frames):
            return
        try:
            with Image.open(path) as opened:
                opened.load()
                image = opened.convert("RGB")
        except Exception as error:
            self.mark_unreadable(index, f"{path.name}: {error}")
            return
        frame = self._frames[index]
        frame.source = pil_to_pixmap(_bounded(image))
        frame.scaled = None
        frame.unreadable = False

    # --- geometry -----------------------------------------------------------

    def _measure(self) -> int:
        """The frame size the current space allows.

        Bounded by width and height both. Width alone is not enough: in a
        tall narrow column a single frame sized from the width became a
        square the size of the column.
        """
        count = len(self._frames)
        size = MAX_FRAME_PX
        if not self.testAttribute(Qt.WidgetAttribute.WA_Resized):
            # Nobody has given it a real cell yet, so its size is still Qt's
            # placeholder 100x30. Measuring against that would state a
            # minimum-size appetite and the layout would grant it.
            return size
        if self.width() > 1:
            usable = self.width() - 2 * EDGE - GUTTER * (count - 1)
            size = MIN_FRAME_PX if usable <= 0 else usable // count
        if self.height() > 1:
            size = min(size, self.height() - CHROME_PX)
        return max(MIN_FRAME_PX, min(MAX_FRAME_PX, int(size)))

    def _sync(self) -> int:
        """Bring the cached frame size up to date with the current geometry.

        Measured on read rather than only on `resizeEvent`: a widget's
        geometry is set the moment it is resized, but the event is deferred
        while it is hidden, and a strip that reported a stale size until it
        was shown would be reporting a lie.
        """
        self._frame_size = self._measure()
        return self._frame_size

    def _remeasure(self) -> None:
        before = self._frame_size
        if self._sync() != before:
            # The height we ask for follows the frame size, so only tell the
            # layout when it actually moved. Asking on every repaint is how
            # a widget and its layout walk each other down to the minimum.
            self.updateGeometry()
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(self.span, self.frame_size + CHROME_PX)

    def minimumSizeHint(self) -> QSize:
        count = len(self._frames)
        return QSize(
            2 * EDGE + count * (MIN_FRAME_PX + GUTTER) - GUTTER,
            MIN_FRAME_PX + CHROME_PX,
        )

    def resizeEvent(self, event: QResizeEvent) -> None:
        self._remeasure()

    # --- drawing ------------------------------------------------------------

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.setFont(self._font)

        size = self._sync()
        span = self.span
        band = size + CHROME_PX

        # Panel, not rebate. A black slab this size reads as a hole in the
        # light table; the strip is a sleeve lying on it, and the frames are
        # what is dark. The hairline is doing real work -- panel on table is
        # a low-contrast edge -- and it replaces the shadow we are not using.
        painter.fillRect(QRect(0, 0, span, band), theme.rgb(theme.PANEL))
        painter.setPen(theme.rgb(theme.EDGE))
        painter.drawRect(QRect(0, 0, span - 1, band - 1))

        for index, frame in enumerate(self._frames):
            self._paint_frame(painter, index, frame)

        if self.exposed == 0:
            # Once, across the whole strip. Once per frame would turn an
            # unexposed strip into a wall of repeated text.
            painter.setPen(theme.rgb(theme.INK_DIM))
            painter.drawText(
                QRect(0, TOP + NUMBER_ROW, span, size),
                int(Qt.AlignmentFlag.AlignCenter),
                EMPTY_CAPTION,
            )
        painter.end()

    def _paint_frame(self, painter: QPainter, index: int, frame: _Frame) -> None:
        size = self._frame_size
        left = EDGE + index * (size + GUTTER)
        top = TOP + NUMBER_ROW

        painter.setPen(theme.rgb(theme.CHINAGRAPH))
        painter.drawText(
            QRect(left, TOP, size, NUMBER_ROW),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            str(index + 1),
        )

        # The aperture. An empty frame is still a frame.
        painter.setPen(theme.rgb(theme.REBATE))
        painter.drawRect(
            QRect(left - APERTURE, top - APERTURE, size + 2 * APERTURE - 1, size + 2 * APERTURE - 1)
        )

        thumbnail = frame.at(size)
        if thumbnail is not None:
            painter.drawPixmap(
                left + (size - thumbnail.width()) // 2,
                top + (size - thumbnail.height()) // 2,
                thumbnail,
            )
        elif frame.unreadable:
            painter.setPen(theme.rgb(theme.CHINAGRAPH))
            painter.drawText(
                QRect(left, top, size, size),
                int(Qt.AlignmentFlag.AlignCenter),
                UNREADABLE_CAPTION,
            )

        if frame.title:
            painter.setPen(theme.rgb(theme.INK_DIM))
            painter.drawText(
                QRect(left, top + size, size, STENCIL_ROW),
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                self._elide(frame.title),
            )

    def _elide(self, text: str) -> str:
        """`text`, shortened from the end until it fits one frame.

        From the end, unlike the file list: these read "FRAME 3 . DETAIL",
        so the front is what identifies the frame. Unelided, frame 1's
        caption ran straight through frame 2's.
        """
        size = self.frame_size
        if not text or size <= 0:
            return ""
        return self._metrics.elidedText(text, Qt.TextElideMode.ElideRight, size)
