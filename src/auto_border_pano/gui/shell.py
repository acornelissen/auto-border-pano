"""The skeleton both tabs are built on.

There is one product here, not two. Before this module the tabs shared four
concepts -- a ratio combobox, an output field, a run button, a preview --
and duplicated none of the layout: aspect ratio was row 3 on one tab and row
1 on the other, and switching tabs re-laid-out the whole window. Everything
in here exists so that stops being true.

Presentation only, like `theme`. Nothing here knows what a panorama is.
"""

import tkinter as tk
from tkinter import ttk

from auto_border_pano.gui import theme

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


class RebateBand:
    """The black band a lab prints the frame's name onto.

    A static drawn header, deliberately not a Canvas tab bar. The plan
    considered making the tabs themselves frame numbers on this band and
    rejected it: `ttk.Notebook` gives keyboard tab navigation, focus rings
    and what accessibility Tk affords, and a hand-drawn Canvas tab bar would
    have bought a frame number and cost all three.
    """

    def __init__(self, parent: tk.Misc) -> None:
        self.canvas = tk.Canvas(
            parent,
            height=BAND_HEIGHT,
            background=theme.REBATE,
            highlightthickness=0,
            borderwidth=0,
        )
        self.subject = ""
        self._font = theme.font(parent, "stencil")
        self.canvas.bind("<Configure>", lambda _event: self._draw())

    def set_subject(self, text: str, *, strip_suffix: bool = False) -> None:
        """Name what is loaded. Caps because a lab stencils in caps."""
        if strip_suffix:
            text = text.rsplit(".", 1)[0]
        self.subject = text.upper()
        self._draw()

    def _draw(self) -> None:
        # Every redraw clears first. The band redraws on each file selection
        # and each resize, so leaving items behind would pile up thousands.
        self.canvas.delete("all")
        self._tracked_text(theme.SPACE_M, "AUTO BORDER PANO", theme.SPROCKET, "identity")
        if not self.subject:
            return
        width = self.canvas.winfo_width()
        # Right-aligned, so measure the run before placing the first glyph.
        run = self._tracked_width(self.subject)
        self._tracked_text(
            max(width - run - theme.SPACE_M, 0), self.subject, theme.LIGHTBOX, "subject"
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
