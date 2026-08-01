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

import math
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

from maskingframe.gui import theme

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
"""Frames size from the space actually available, with no upper bound.

A constant maximum is why a working run once showed postage stamps in a
pane 540pt tall. There is no maximum now: the strip fills its half of the
window, because a preview you have to squint at is not doing its job.
"""

THUMBNAIL_PX = 900
"""What an image is bounded to on the way in.

Not a display bound -- the strip draws at whatever size the window allows.
This is the ceiling on what is held in memory per frame, so a 132MP scan is
resampled once on arrival and never again.
"""

APERTURE = 1
"""Hairline around a frame's image, drawn whether or not there is a
photograph in it yet -- an unexposed strip should still read as film."""

DEFAULT_FRAME_COUNT = 4
"""What an unexposed strip shows before anything is loaded.

Four is the commonest run -- one whole frame plus three details -- and the
count is only a drawing, so being wrong about it costs nothing.
"""

UNREADABLE_CAPTION = "UNREADABLE"


@dataclass(frozen=True)
class Rect:
    """A rectangle in normalised frame coordinates: 0..1 on both axes.

    Normalised so nothing here has to know the output's pixel size, and so
    the same description stays correct at every size the strip draws.
    """

    x: float
    y: float
    width: float
    height: float


@dataclass(frozen=True)
class BorderPreview:
    """What a border will look like, in terms the strip can draw.

    Plain data on purpose -- floats, strings and normalised rectangles. The
    strip is presentation only and must not learn what a `FrameStyle` is,
    so a tab translates its own settings into this and hands it over.

    `border` is a fraction of the frame's *short* side, matching how the
    setting is defined; the frame is the target ratio fitted inside the
    aperture, which is not the aperture itself. `first_frame_only` says the
    border applies to frame 1 alone -- what the Split tab does until the
    detail frames are bordered too. `gaps` are the separators between
    composite panels, empty when there are none to draw.

    `panels` is where a composite's pictures land, and supplying it changes
    how the whole thing is drawn. A composite's border is not the nominal
    band `border` describes: the solver fits the assembled block inside the
    frame's inset box and centres it, so on whichever axis the block is
    short there is leftover slack, and the render paints that slack in the
    border colour too. At 4:5 with a wide source and a square one that can
    more than double the border down one pair of edges. So when the panels
    are known the overlay is drawn the way the render composes -- the whole
    frame in the border colour, the gaps over it, and the panels knocked
    back out -- and the previewed border is then exactly the border. With
    no panels (the Split tab, or a composite whose shapes are not known
    yet) it stays a band around the edge, which is all that can be said.
    """

    aspect: float
    border: float
    colour: str
    first_frame_only: bool = False
    gaps: tuple[Rect, ...] = ()
    gap_colour: str = ""
    panels: tuple[Rect, ...] = ()


def frame_rect(left: int, top: int, size: int, aspect: float) -> QRect:
    """The output frame, at `aspect`, fitted inside a `size` square aperture.

    An aperture is square; an output frame almost never is. With a
    thumbnail loaded its own rectangle already *is* the frame, but an empty
    frame has no such rectangle, and dialling a border in before choosing a
    file is the main reason to want a live preview at all.
    """
    if aspect <= 0:
        return QRect(left, top, size, size)
    if aspect >= 1:
        width = size
        height = max(1, math.floor(size / aspect + 0.5))
    else:
        height = size
        width = max(1, math.floor(size * aspect + 0.5))
    return QRect(left + (size - width) // 2, top + (size - height) // 2, width, height)


def border_bands(rect: QRect, fraction: float) -> list[QRect]:
    """The four bands a border of `fraction` covers inside `rect`.

    Returns nothing at all for a zero border rather than a hairline: no
    border means no border. The bands are returned rather than painted so
    the arithmetic can be checked without a screen.
    """
    if fraction <= 0 or rect.width() <= 0 or rect.height() <= 0:
        return []
    short = min(rect.width(), rect.height())
    thickness = math.floor(fraction * short + 0.5)
    if thickness <= 0:
        return []
    if 2 * thickness >= rect.height() or 2 * thickness >= rect.width():
        return [QRect(rect)]
    left, top = rect.x(), rect.y()
    width, height = rect.width(), rect.height()
    inner = height - 2 * thickness
    return [
        QRect(left, top, width, thickness),
        QRect(left, top + height - thickness, width, thickness),
        QRect(left, top + thickness, thickness, inner),
        QRect(left + width - thickness, top + thickness, thickness, inner),
    ]


def scaled_rect(rect: QRect, normalised: Rect) -> QRect:
    """Place a normalised rectangle inside a frame's pixel rectangle."""
    return QRect(
        rect.x() + math.floor(normalised.x * rect.width() + 0.5),
        rect.y() + math.floor(normalised.y * rect.height() + 0.5),
        max(1, math.floor(normalised.width * rect.width() + 0.5)),
        max(1, math.floor(normalised.height * rect.height() + 0.5)),
    )


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
    copied.thumbnail((THUMBNAIL_PX, THUMBNAIL_PX), Image.Resampling.LANCZOS)
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
        self._border: BorderPreview | None = None
        self._frame_size = MIN_FRAME_PX
        self._columns = max(frames, 1)
        # Expanding in both directions: the frames grow to fill the space the
        # window gives them. The strip's own background is painted only
        # behind the film, so filling the cell does not leave a large pale
        # panel around it.
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
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
    def columns(self) -> int:
        """How many frames the sheet puts on a row at the current size."""
        self._sync()
        return self._columns

    @property
    def rows(self) -> int:
        # Syncs first, like every other derived reader here: the column
        # count follows the geometry, and geometry is set the moment a
        # widget is resized even though the event is deferred while hidden.
        self._sync()
        return math.ceil(len(self._frames) / max(self._columns, 1))

    @property
    def span(self) -> int:
        """How far the sheet's own background reaches across.

        As wide as the film in it, never the full column width: a pale tail
        beyond the last frame reads as an unfinished panel, not a sheet.
        """
        size = self.frame_size
        columns = min(self._columns, len(self._frames))
        return 2 * EDGE + columns * (size + GUTTER) - GUTTER

    @property
    def extent(self) -> int:
        """How far it reaches down."""
        self._sync()
        rows = self.rows
        return 2 * EDGE + rows * (self._frame_size + CHROME_PX) + GUTTER * (rows - 1)

    def set_border_preview(self, preview: BorderPreview | None) -> None:
        """Draw the border the rail currently describes, or nothing.

        `None` is the widget's original behaviour: no overlay at all. The
        border is drawn solid, in its own colour, because it is what will
        actually be printed -- a tint would be a diagram of the frame
        rather than the frame.
        """
        if preview == self._border:
            return
        self._border = preview
        self.update()

    @property
    def border_preview(self) -> BorderPreview | None:
        return self._border

    def frame_rect_at(self, index: int) -> QRect:
        """Where the output frame sits inside frame `index`'s aperture."""
        if not 0 <= index < len(self._frames):
            return QRect()
        return self._frame_rect(index)

    def border_rects(self, index: int) -> list[QRect]:
        """Where the border will land on frame `index`, in widget pixels.

        Exposed so the overlay's geometry can be checked without sampling a
        rendered image, and so a caller can prove which frames carry it.
        """
        if self._border is None or not 0 <= index < len(self._frames):
            return []
        if self._border.first_frame_only and index != 0:
            return []
        if self._frames[index].source is not None:
            # A frame holding a render already has its border in the pixels.
            # Overlaying another would lay a second band over the first.
            return []
        rect = self._frame_rect(index)
        if self._border.panels:
            # A composite's border is everything the panels and gaps do not
            # cover, which is not four bands: it is the whole frame, laid
            # down first and then knocked back out. Reported as the one
            # rectangle that is actually filled in the border colour.
            return [rect]
        return border_bands(rect, self._border.border)

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

    def clear_images(self) -> bool:
        """Drop every picture, keeping the frames themselves. Says whether
        there was anything to drop.

        For when a render on screen no longer matches the settings that made
        it: the border is rendered *into* a preview, so the moment the rail
        moves the picture is a lie. The strip goes back to empty apertures,
        where the live overlay draws the border the rail now describes.

        The run is untouched -- same count, same titles, same numbering --
        because only the pixels went stale, not the shape of the run. The
        return value is there so a caller can stay quiet when a frame
        silently vanishing would have been the only thing worth saying.
        """
        dropped = any(frame.source is not None or frame.unreadable for frame in self._frames)
        for frame in self._frames:
            frame.source = None
            frame.scaled = None
            frame.scaled_at = 0
            frame.unreadable = False
        self._errors = []
        self._remeasure()
        return dropped

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

    @staticmethod
    def _size_for(count: int, columns: int, width: int, height: int) -> int:
        """Frame size for a given number of columns, or 0 if it will not fit."""
        rows = math.ceil(count / columns)
        across = width - 2 * EDGE - GUTTER * (columns - 1)
        down = height - 2 * EDGE - rows * CHROME_PX - GUTTER * (rows - 1)
        if across <= 0 or down <= 0:
            return 0
        return min(across // columns, down // rows)

    def _measure(self) -> tuple[int, int]:
        """The frame size and column count the current space allows.

        A contact sheet wraps, and that is what lets the frames actually
        fill the space. In one fixed row the width alone decides how big a
        frame can be, so a tall window just left empty table underneath --
        the strip filled its cell while painting a thin band at the top of
        it. Trying every column count and keeping whichever makes the frames
        biggest uses both dimensions instead.
        """
        count = len(self._frames)
        if not self.testAttribute(Qt.WidgetAttribute.WA_Resized):
            # Nobody has given it a real cell yet, so its size is still Qt's
            # placeholder 100x30. Measuring against that would state an
            # appetite the layout would then grant.
            return MIN_FRAME_PX, count
        width, height = max(self.width(), 1), max(self.height(), 1)
        best_size, best_columns = 0, count
        for columns in range(1, count + 1):
            size = self._size_for(count, columns, width, height)
            # Ties go to fewer rows: at equal size a single row reads as a
            # strip, which is what the frames are.
            if size > best_size:
                best_size, best_columns = size, columns
        return max(MIN_FRAME_PX, int(best_size)), best_columns

    def _sync(self) -> int:
        """Bring the cached frame size up to date with the current geometry.

        Measured on read rather than only on `resizeEvent`: a widget's
        geometry is set the moment it is resized, but the event is deferred
        while it is hidden, and a strip that reported a stale size until it
        was shown would be reporting a lie.
        """
        self._frame_size, self._columns = self._measure()
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
        # Deliberately the minimum, not the measured size. The widget now
        # expands to fill its cell, so asking for the size it currently
        # happens to be would let the widget and its layout push each other
        # around on every repaint.
        return self.minimumSizeHint()

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

        self._sync()
        span = self.span
        band = self.extent

        # Panel, not rebate. A black slab this size reads as a hole in the
        # light table; the strip is a sleeve lying on it, and the frames are
        # what is dark. The hairline is doing real work -- panel on table is
        # a low-contrast edge -- and it replaces the shadow we are not using.
        painter.fillRect(QRect(0, 0, span, band), theme.rgb(theme.PANEL))
        painter.setPen(theme.rgb(theme.EDGE))
        painter.drawRect(QRect(0, 0, span - 1, band - 1))

        for index, frame in enumerate(self._frames):
            self._paint_frame(painter, index, frame)

        # No caption on an empty strip. The numbered, empty apertures
        # already say there is nothing on it, and captioning them said the
        # same thing twice -- in the largest element in the window.
        painter.end()

    def _aperture(self, index: int) -> tuple[int, int]:
        """The top-left corner of one frame's square image area."""
        size = self._frame_size
        column = index % max(self._columns, 1)
        row = index // max(self._columns, 1)
        # Every row carries its own number line and stencil line, so both
        # are offset from the row rather than from the widget.
        row_top = EDGE + row * (size + CHROME_PX + GUTTER)
        return EDGE + column * (size + GUTTER), row_top + TOP + NUMBER_ROW

    def _frame_rect(self, index: int) -> QRect:
        """The output frame inside one aperture, in widget pixels.

        A loaded thumbnail is already scaled to the output ratio and
        centred, so its own rectangle *is* the frame. With nothing loaded
        the frame has to be derived from the target ratio instead.
        """
        self._sync()
        size = self._frame_size
        left, top = self._aperture(index)
        thumbnail = self._frames[index].at(size)
        if thumbnail is not None:
            return QRect(
                left + (size - thumbnail.width()) // 2,
                top + (size - thumbnail.height()) // 2,
                thumbnail.width(),
                thumbnail.height(),
            )
        aspect = self._border.aspect if self._border is not None else 1.0
        return frame_rect(left, top, size, aspect)

    def _paint_frame(self, painter: QPainter, index: int, frame: _Frame) -> None:
        size = self._frame_size
        left, top = self._aperture(index)
        row_top = top - TOP - NUMBER_ROW

        painter.setPen(theme.rgb(theme.CHINAGRAPH))
        painter.drawText(
            QRect(left, row_top + TOP, size, NUMBER_ROW),
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

        self._paint_border(painter, index)

        if frame.title:
            painter.setPen(theme.rgb(theme.INK_DIM))
            painter.drawText(
                QRect(left, top + size, size, STENCIL_ROW),
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                self._elide(frame.title),
            )

    def _paint_border(self, painter: QPainter, index: int) -> None:
        """Lay the border, and any panel gaps, over one frame.

        Solid and in its own colour: this is the finished frame, not an
        annotation of it. The gaps go down in the gap colour for the same
        reason -- on a composite they are as much of the result as the
        outer border is.
        """
        preview = self._border
        if preview is None:
            return
        if preview.first_frame_only and index != 0:
            return
        # A rendered preview already has the border drawn into it, so
        # overlaying here would apply it twice -- and the two disagree,
        # because the render's border sits inside the image while the
        # overlay's sits on the frame. The render is the truth; leave it be.
        if self._frames[index].source is not None:
            return
        rect = self._frame_rect(index)
        colour = theme.rgb(preview.colour)
        if preview.panels:
            # In the render's own order: the canvas in the border colour,
            # the gaps over it, the panels on top. Here the panels hold no
            # picture yet, so they are knocked back to the empty aperture --
            # and what is left is the border, slack and all.
            painter.fillRect(rect, colour)
        else:
            for band in border_bands(rect, preview.border):
                painter.fillRect(band, colour)
        if preview.gaps and preview.gap_colour:
            gap_colour = theme.rgb(preview.gap_colour)
            for gap in preview.gaps:
                painter.fillRect(scaled_rect(rect, gap), gap_colour)
        aperture = theme.rgb(theme.PANEL)
        for panel in preview.panels:
            painter.fillRect(scaled_rect(rect, panel), aperture)

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
