"""The skeleton both tabs are built on.

There is one product here, not two. Before this module the tabs shared four
concepts -- a ratio combobox, an output field, a run button, a preview --
and duplicated none of the layout: aspect ratio was row 3 on one tab and row
1 on the other, and switching tabs re-laid-out the whole window. Everything
in here exists so that stops being true.

Presentation only, like `theme`. Nothing here knows what a panorama is.
"""

import contextlib
import tkinter as tk
from tkinter import ttk
from typing import Protocol

from auto_border_pano.gui import theme


class BandSubject(Protocol):
    """What the shell needs from a tab in order to stencil the band.

    The band belongs to the shell rather than to either tab, so the tabs do
    not know about it or about each other -- they only state what they are
    working on and what they will make of it. Naming that contract here is
    what stops a tab quietly dropping one of the two variables: `app.run`
    is the only place that reads them and it ends in `mainloop`, so without
    this the failure would be a crash at launch with a green test suite.
    """

    @property
    def subject(self) -> tk.StringVar:
        """What is loaded: a filename, or how many sources."""

    @property
    def detail(self) -> tk.StringVar:
        """What this tab will make of it: `4:5 · 5 frames`."""


RAIL_WIDTH = 340
"""Points. The control rail is fixed; the light table takes what is left.

Fixed rather than proportional because the rail holds a fixed set of
controls at a fixed type size -- letting it grow with the window would just
stretch whitespace between a combobox and a button.
"""

BAND_HEIGHT = 44
"""Points. Tall enough for 12pt tracked caps with air above and below."""

_TRACKING = 2.4
"""Extra points between characters in the band. Film edge stencils are
tracked wide; this is the closest Tk gets, since Canvas is the only place
letter-spacing is possible at all."""


class TwoColumn:
    """A fixed control rail on the left, the light table on the right.

    The preview was previously whatever space was left at the bottom of the
    tab, which is why it could own 45% of the window and show nothing. Here
    it occupies the right column by design.
    """

    def __init__(self, parent: tk.Misc) -> None:
        self.frame = ttk.Frame(parent, padding=theme.SPACE_L)
        self.frame.columnconfigure(0, minsize=RAIL_WIDTH, weight=0)
        self.frame.columnconfigure(1, weight=1)
        self.frame.rowconfigure(0, weight=1)

        self.rail = ttk.Frame(self.frame)
        self.rail.grid(row=0, column=0, sticky=(tk.N, tk.S, tk.W, tk.E))
        self.rail.columnconfigure(0, weight=1)

        self.table = ttk.Frame(self.frame)
        self.table.grid(row=0, column=1, sticky=(tk.N, tk.S, tk.W, tk.E), padx=(theme.SPACE_L, 0))
        self.table.columnconfigure(0, weight=1)
        self.table.rowconfigure(0, weight=1)


def section(parent: tk.Misc, title: str, row: int) -> ttk.Label:
    """A rail section heading: `SOURCE`, `FORMAT`, `DESTINATION`.

    The rail is grouped by headings and whitespace rather than by rules --
    hairline rules everywhere is the broadsheet default, and this is a
    utility panel, not a newspaper.
    """
    label = ttk.Label(parent, text=title.upper(), style="Section.TLabel")
    label.grid(row=row, column=0, sticky=tk.W, pady=(theme.SPACE_L, theme.SPACE_S))
    return label


def show_tail(entry: ttk.Entry) -> None:
    """Keep the end of a path in view: the filename, not the volume.

    A path is longer than the 340pt rail and Tk shows a field from its
    start, so the rails displayed "/Users/albert/Pictures/coastline-hp" and
    clipped the only part of a path anybody recognises.

    Deferred to idle because a variable trace fires the instant the value is
    set, which on a first selection is before the field has been laid out --
    and a field one pixel wide has nothing to scroll. Callers also bind it
    to `<Configure>`, because Tk resets the view when a field is resized.

    Skipped while the field has focus: yanking the view to the end under
    someone who is typing, or who has put the caret mid-path, would be the
    interface fighting them.
    """
    if entry.focus_get() is entry:
        return

    def scroll() -> None:
        # The window can close between scheduling this and running it.
        with contextlib.suppress(tk.TclError):
            entry.xview_moveto(1.0)

    with contextlib.suppress(tk.TclError):
        entry.after_idle(scroll)


def path_entry(parent: tk.Misc, variable: tk.StringVar) -> ttk.Entry:
    """A rail's path field: mono, expanding, and riding at its tail."""
    entry = ttk.Entry(parent, textvariable=variable, style="TEntry")
    entry.grid(row=0, column=0, sticky=(tk.W, tk.E))
    entry.bind("<Configure>", lambda _event: show_tail(entry))
    variable.trace_add("write", lambda *_a: show_tail(entry))
    return entry


class RebateBand:
    """The black band a lab prints the frame's name onto.

    A static drawn header, deliberately not a Canvas tab bar. The plan
    considered making the tabs themselves frame numbers on this band and
    rejected it: `ttk.Notebook` gives keyboard tab navigation, focus rings
    and what accessibility Tk affords, and a hand-drawn Canvas tab bar would
    have bought a frame number and cost all three.
    """

    NOTHING_LOADED = "NO SOURCE LOADED"

    def __init__(self, parent: tk.Misc) -> None:
        self.canvas = tk.Canvas(
            parent,
            height=BAND_HEIGHT,
            background=theme.REBATE,
            highlightthickness=0,
            borderwidth=0,
        )
        self.subject = ""
        self.detail = ""
        self._font = theme.font(parent, "stencil")
        self.canvas.bind("<Configure>", lambda _event: self._draw())
        self._draw()

    def set_subject(self, text: str, *, strip_suffix: bool = False) -> None:
        """Name what is loaded. Caps because a lab stencils in caps."""
        if strip_suffix:
            text = text.rsplit(".", 1)[0]
        self.subject = text.upper()
        self._draw()

    def set_detail(self, text: str) -> None:
        """What the front tab will produce from it -- `4:5 · 5 FRAMES`."""
        self.detail = text.upper()
        self._draw()

    def _draw(self) -> None:
        # Every redraw clears first. The band redraws on each file selection
        # and each resize, so leaving items behind would pile up thousands.
        self.canvas.delete("all")
        # The subject leads, because the band exists to say what you are
        # working on. It used to open with the app's own name, which the
        # window's title bar is already saying two centimetres above -- the
        # band was spending its most prominent position on a duplicate.
        subject = self.subject or self.NOTHING_LOADED
        fill = theme.LIGHTBOX if self.subject else theme.SPROCKET
        self._tracked_text(theme.SPACE_L, subject, fill, "subject")
        if not self.detail:
            return
        width = self.canvas.winfo_width()
        # Right-aligned, so measure the run before placing the first glyph.
        run = self._tracked_width(self.detail)
        self._tracked_text(
            max(width - run - theme.SPACE_L, 0), self.detail, theme.SPROCKET, "detail"
        )

    def _tracked_width(self, text: str) -> float:
        return sum(self._font.measure(char) + _TRACKING for char in text)

    def _tracked_text(self, x: float, text: str, fill: str, tag: str) -> None:
        """Letter-spacing exists nowhere in Tk but here: one item per glyph
        at a measured offset. Only ever used for short static strings --
        never for anything that reflows."""
        for char in text:
            self.canvas.create_text(
                x,
                BAND_HEIGHT / 2,
                text=char,
                fill=fill,
                font=self._font,
                anchor="w",
                tags=(tag,),
            )
            x += self._font.measure(char) + _TRACKING
