"""The contact strip: one Canvas holding every frame of a run.

This replaces the four disconnected sunken boxes of `PreviewPanes` with a
single object -- frames butted together on a shared sleeve, each carrying
its frame number in chinagraph above and its role stencilled beneath.

The sleeve is pale, not black. A black slab the size of this widget reads
as a hole cut in the light table; what should be dark is the photograph,
so each frame sits in an aperture with a one-pixel film-base hairline and
nothing heavier.

Three rules from the design plan's feasibility table are load-bearing here
and are not preferences:

* No drop shadows. Tk Canvas has no alpha blending against the canvas
  background, so a faked shadow is brittle. The strip sits on the table
  with a one-pixel rule instead.
* No pre-rendered bitmap ornament. Any `ImageTk` bitmap blits at image
  pixels equal points and goes soft on a 2x display, so every piece of
  chrome here is a native Canvas primitive. Images are used only for the
  user's own photographs, where softness is invisible at thumbnail size.
* No animation and no rounded corners. The one motion in the app is frames
  appearing as they are written, which is discrete.

The strip draws its empty state from construction, with no call needed.
That is the point of the widget: the old preview pane built its container
and never populated it, so the largest element in the window was a void
with nothing in it, not even a caption.
"""

import tkinter as tk
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageTk

from auto_border_pano.gui import theme

EDGE = theme.SPACE_M
"""Rebate to the left and right of the outermost frames."""

GUTTER = theme.SPACE_S
"""Rebate between two butted frames. Small: they read as one strip."""

NUMBER_ROW = 20
STENCIL_ROW = 20
TOP = theme.SPACE_S
BOTTOM = theme.SPACE_S

CHROME_PX = TOP + NUMBER_ROW + STENCIL_ROW + BOTTOM
"""Everything in a frame's column that is not the photograph."""

MIN_FRAME_PX = 72
MAX_FRAME_PX = 260
"""Frames size from the space actually available, between these bounds.

The old `PREVIEW_MAX_PX = 150` was a constant, which is why a working run
showed postage stamps floating in a pane 540pt tall. The opposite failure
is just as bad: sizing a single frame from a wide column made one frame
the size of the column. A frame is a thumbnail of a run, not the run.
"""

APERTURE = 1
"""Hairline around a frame's image. The photograph needs separating from
the sleeve, and one pixel of film base does it without a heavy border."""

DEFAULT_FRAME_COUNT = 4
"""What an unexposed strip shows before anything is loaded.

Four is the commonest run -- one whole frame plus three details -- and the
count is only a drawing, so being wrong about it costs nothing.
"""

RESIZE_DELAY_MS = 80
"""Debounce. A window drag fires `<Configure>` per pixel; rebuilding
thumbnails that often would make the drag crawl."""

EMPTY_CAPTION = "NOTHING ON THE STRIP YET"
UNREADABLE_CAPTION = "UNREADABLE"

ELLIPSIS = "…"


@dataclass
class _Frame:
    """One cell of the strip. `image` is the only state that matters."""

    title: str = ""
    image: Image.Image | None = None
    unreadable: bool = False


@dataclass
class _Metrics:
    """Where everything sits, once the available space is known."""

    frame_size: int = MIN_FRAME_PX
    height: int = 0
    origin: int = EDGE
    step: int = field(default=0)
    band: int = 0
    """Height of the sleeve the strip is drawn on. At least `height`; more
    when the geometry manager has stretched the canvas past its content, so
    the strip fills its cell instead of leaving a slab of bare table."""
    top: int = 0
    """Where the content starts inside the band, so it sits centred."""


class ContactStrip:
    """A row of numbered frames on one continuous rebate."""

    def __init__(self, parent: tk.Misc, frames: int = DEFAULT_FRAME_COUNT) -> None:
        self.canvas = tk.Canvas(
            parent,
            background=theme.LIGHTBOX,
            highlightthickness=0,
            borderwidth=0,
        )
        self._font = theme.font(parent, "stencil")
        self._frames: list[_Frame] = [_Frame() for _ in range(max(frames, 1))]
        # PhotoImage references. Tk drops an image the instant its
        # PhotoImage is collected and renders a blank in its place, so this
        # list is not a cache -- it is the only thing keeping the pixels on
        # screen. A Canvas needs it exactly as much as a Label does.
        self._photos: list[ImageTk.PhotoImage] = []
        # Reasons for any UNREADABLE frame, for a caller's status line.
        self.errors: list[str] = []
        self._width = 0
        self._height = 0
        self._metrics = _Metrics()
        self._resize_job: str | None = None

        self.canvas.bind("<Configure>", self._on_configure)
        # The empty state exists from construction. No call required.
        self._redraw()

    # --- public API ---------------------------------------------------------

    @property
    def frame_count(self) -> int:
        return len(self._frames)

    @property
    def frame_size(self) -> int:
        """Side of a frame's image area, in points. Derived, never constant."""
        return self._metrics.frame_size

    def set_frames(self, titles: Sequence[str]) -> None:
        """Lay out one frame per title, discarding everything from the last run.

        Called on every run, and the count varies with the ratio and the
        panorama, so this must not leave stale canvas items or stale image
        references behind.
        """
        self._frames = [_Frame(title=title.upper()) for title in titles] or [_Frame()]
        self._photos = []
        self.errors = []
        self._redraw()

    def show_paths(self, paths: Sequence[Path]) -> None:
        """Load a thumbnail per frame from disk."""
        self.errors = []
        for index, path in enumerate(paths):
            if index >= len(self._frames):
                break
            self._load(index, path)
        self._redraw()

    def show_images(self, images: Sequence[Image.Image]) -> None:
        """Show already-loaded images, one per frame."""
        self.errors = []
        for frame, image in zip(self._frames, images, strict=True):
            frame.image = _bounded(image)
            frame.unreadable = False
        self._redraw()

    def mark_written(self, index: int, path: Path) -> None:
        """Expose one frame. Progress is the strip filling in, not a bar."""
        self._load(index, path)
        self._redraw()

    def mark_unreadable(self, index: int, reason: str) -> None:
        """Mark a frame whose file will not decode, keeping the reason."""
        if not 0 <= index < len(self._frames):
            return
        self._frames[index].image = None
        self._frames[index].unreadable = True
        self.errors.append(reason)
        self._redraw()

    def set_available_width(self, width: int) -> None:
        """Resize to a known width. Frames size from this, not a constant."""
        self.set_available_space(width, self._height)

    def set_available_space(self, width: int, height: int) -> None:
        """Resize to a known cell. Frames are bounded by both dimensions.

        Width alone is not enough: in a tall column a single frame sized
        from the width alone becomes a square the size of the column.
        """
        if width <= 1:
            # `<Configure>` fires once before the geometry manager has any
            # real size to report. Laying out against that would divide the
            # strip into slivers and then thrash back.
            return
        self._width = width
        self._height = max(height, 0)
        self._redraw()

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
        # Bounded on the way in, so a redraw never re-scales a 132MP scan
        # and the strip never holds more than a few hundred KB per frame.
        self._frames[index].image = _bounded(image)
        self._frames[index].unreadable = False

    # --- geometry -----------------------------------------------------------

    def _on_configure(self, event: "tk.Event[tk.Canvas]") -> None:
        """Only the width comes from the widget itself.

        The canvas asks for its own height (`configure(height=...)`), so the
        height it is then given back is the height it just requested. Feeding
        that into the size calculation is a loop: each redraw bounds the
        frames by the height the previous redraw asked for, and the strip
        walks itself down to the minimum frame size over a few resizes. The
        height bound only means anything when a caller states a real cell
        height through `set_available_space`.
        """
        if self._resize_job is not None:
            self.canvas.after_cancel(self._resize_job)
        width = int(event.width)
        self._resize_job = self.canvas.after(
            RESIZE_DELAY_MS, lambda: self.set_available_width(width)
        )

    def _measure(self) -> _Metrics:
        count = len(self._frames)
        width = self._width or self.canvas.winfo_width()
        usable = width - 2 * EDGE - GUTTER * (count - 1)
        size = MIN_FRAME_PX if usable <= 0 else usable // count
        if self._height > 1:
            # The other bound. Without it the strip only knows how wide it
            # may be, which is how one frame in a tall column became one
            # enormous square.
            size = min(size, self._height - CHROME_PX)
        size = max(MIN_FRAME_PX, min(MAX_FRAME_PX, int(size)))
        height = size + CHROME_PX
        # The band is the strip's own height, never the whole cell. Painting
        # the full cell turned a five-frame strip into a large pale panel
        # with a thin row of pictures floating in the middle of it -- the
        # same "big box mostly containing nothing" the strip exists to fix.
        # Everything below the strip is light table, and should look like it.
        return _Metrics(
            frame_size=size,
            height=height,
            origin=EDGE,
            step=size + GUTTER,
            band=height,
            top=0,
        )

    # --- drawing ------------------------------------------------------------

    def _redraw(self) -> None:
        # Every redraw clears first. The strip redraws on every run, every
        # written frame and every resize; leaking items would pile up
        # thousands of them.
        self.canvas.delete("all")
        self._photos = []
        self._metrics = self._measure()
        metrics = self._metrics

        # The sleeve is as long as the film in it. Running it to the full
        # width of the column left a wide pale tail beyond the last frame,
        # which reads as an unfinished panel rather than as a strip.
        span = 2 * EDGE + metrics.step * len(self._frames) - GUTTER
        self.canvas.configure(height=metrics.height)
        # The sleeve, not the film base. A black slab this size reads as a
        # hole in the light table; the strip is a negative sleeve lying on
        # it, and the frames are what is dark.
        self.canvas.create_rectangle(
            0, 0, span, metrics.band, fill=theme.SLEEVE, outline="", tags=("rebate",)
        )
        # The strip sits on the table with a rule, not a shadow: Tk Canvas
        # has no alpha to blend one against. Sleeve on lightbox is a
        # low-contrast edge, so the rule is doing real work here.
        self.canvas.create_line(
            0, metrics.band - 1, span, metrics.band - 1, fill=theme.SPROCKET, tags=("rule",)
        )

        for index, frame in enumerate(self._frames):
            self._draw_frame(index, frame, metrics)

        if not any(frame.image is not None for frame in self._frames):
            # Once, across the whole strip. Once per frame would turn an
            # unexposed strip into a wall of repeated text.
            self.canvas.create_text(
                span / 2,
                metrics.top + TOP + NUMBER_ROW + metrics.frame_size / 2,
                text=EMPTY_CAPTION,
                # Not sprocket: sprocket is specified against the lightbox
                # and is borderline even there. On the paler sleeve it fails.
                fill=theme.INK_SECONDARY,
                font=self._font,
                anchor="center",
                tags=("caption",),
            )

    def _draw_frame(self, index: int, frame: _Frame, metrics: _Metrics) -> None:
        left = metrics.origin + index * metrics.step
        top = metrics.top + TOP + NUMBER_ROW
        size = metrics.frame_size

        self.canvas.create_text(
            left,
            metrics.top + TOP + NUMBER_ROW / 2,
            text=str(index + 1),
            fill=theme.CHINAGRAPH,
            font=self._font,
            anchor="w",
            tags=("number",),
        )

        # The aperture. An empty frame is still a frame, so this is drawn
        # whether or not there is a photograph in it yet.
        self.canvas.create_rectangle(
            left - APERTURE,
            top - APERTURE,
            left + size + APERTURE - 1,
            top + size + APERTURE - 1,
            fill="",
            outline=theme.REBATE,
            width=APERTURE,
            tags=("aperture", f"aperture{index}"),
        )

        if frame.image is not None:
            thumbnail = frame.image.copy()
            thumbnail.thumbnail((size, size), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(thumbnail)
            self._photos.append(photo)
            self.canvas.create_image(
                left + size / 2,
                top + size / 2,
                image=photo,
                anchor="center",
                tags=("frame", f"frame{index}"),
            )
        elif frame.unreadable:
            self.canvas.create_text(
                left + size / 2,
                top + size / 2,
                text=UNREADABLE_CAPTION,
                fill=theme.CHINAGRAPH,
                font=self._font,
                anchor="center",
                tags=("unreadable", f"frame{index}"),
            )

        if frame.title:
            self.canvas.create_text(
                left,
                top + size + STENCIL_ROW / 2,
                # Clipped to its own frame. Unclipped, "FRAME 1 · WHOLE
                # PANORAMA" ran straight through frame 2's caption.
                text=self._fit(frame.title, size),
                fill=theme.INK_SECONDARY,
                font=self._font,
                anchor="w",
                tags=("stencil",),
            )

    def _fit(self, text: str, available: int) -> str:
        """`text`, shortened from the end until it fits `available` points.

        From the end, unlike the file list: these read "FRAME 3 · DETAIL",
        so the front is what identifies the frame.
        """
        if available <= 0:
            return ""
        if self._font.measure(text) <= available:
            return text
        for end in range(len(text) - 1, 0, -1):
            candidate = text[:end] + ELLIPSIS
            if self._font.measure(candidate) <= available:
                return candidate
        return ELLIPSIS if self._font.measure(ELLIPSIS) <= available else ""


def _bounded(image: Image.Image) -> Image.Image:
    """A copy no larger than the biggest frame the strip will ever draw."""
    copied = image.copy()
    copied.thumbnail((MAX_FRAME_PX, MAX_FRAME_PX), Image.Resampling.LANCZOS)
    return copied
