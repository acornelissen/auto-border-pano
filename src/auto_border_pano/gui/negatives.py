"""The numbered negatives list: the ordering control, drawn as frames.

This replaces the `tk.Listbox` on the Compose tab. The Listbox was a raw Tk
widget among ttk ones -- a pure black rectangle with a hard sunken border,
nothing else in the app looking remotely like it -- sized `height=4` for a
list hard-capped at three, so one row was always dead space. Worse, it said
nothing about the one thing that matters here: the order of the rows is the
left-to-right order of the composite.

So each row carries a chinagraph frame number in the same visual language
as the contact strip's. The number is not decoration and it is not an
index label; it *is* the arrangement, and moving a row moves a numbered
frame. The two widgets speak one language on purpose.

The same three constraints from the design plan's feasibility table bind
here as they do on the strip, and for the same reasons: no drop shadows
(Canvas has no alpha to blend one against), no pre-rendered bitmap chrome
(it goes soft at 2x), no animation and no rounded corners. Every mark below
is a native Canvas primitive, and every colour and font comes from `theme`.

The list holds at most three rows, so there is no scrolling and no
virtualisation here and there should never be any. It draws its empty state
from construction, with no call needed.

Accessibility note: this is a hand-written control, and macOS Tk offers it
no accessibility story at all. Keyboard operability is the mitigation the
plan asks for, which is why the canvas takes focus, shows that it has focus,
and moves the selection on Up/Down. Those bindings are on the widget, never
`bind_all` -- a global binding would steal the arrow keys from the whole app.
"""

import tkinter as tk
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from auto_border_pano.gui import theme

BAR_WIDTH = 4
"""The chinagraph edge mark down the left of a row. Thin: it marks, it does
not fill."""

NUMBER_COLUMN = 26
"""Width reserved for the frame number, so the filenames line up."""

PAD_X = theme.SPACE_S
PAD_Y = theme.SPACE_S

NAME_ROW = 17
DIMENSION_ROW = 15
ROW_HEIGHT = PAD_Y + NAME_ROW + DIMENSION_ROW
"""Two lines per row: the filename, then what the machine measured about it.

The height is derived from this, not fixed at four rows -- the Listbox's
dead fourth row is the specific thing being fixed.
"""

EMPTY_HEIGHT = 2 * ROW_HEIGHT
"""Enough for the empty caption to wrap onto two lines in the rail."""

EMPTY_CAPTION = "Add two negatives for a diptych, three for a triptych."

FALLBACK_WIDTH = 340
"""Stand-in width for the first draw, before the geometry manager reports a
real one. It matches the rail the list lives in; the next draw corrects it."""

ELLIPSIS = "..."

PENDING_DIMENSIONS = "reading..."
"""Shown until the caller's header read lands. Dimensions come off the main
thread, so a row must render before it knows its own size."""


@dataclass(frozen=True)
class Negative:
    """One row: a file, and its pixel size once somebody has read it.

    Frozen because a row is a fact about a file, not a mutable widget model.
    `size` is optional because the Compose tab reads image headers off the
    main thread and hands them over later.
    """

    path: str
    size: tuple[int, int] | None = None

    @property
    def name(self) -> str:
        return Path(self.path).name

    @property
    def dimensions(self) -> str:
        """The measured size, in the same `4000 x 1700` shape the rest of
        the app uses, or a placeholder while it is still being read."""
        if self.size is None:
            return PENDING_DIMENSIONS
        return f"{self.size[0]} × {self.size[1]}"  # noqa: RUF001


class NegativesList:
    """A short list of numbered negatives, in the order they will be placed."""

    def __init__(
        self,
        parent: tk.Misc,
        on_select: Callable[[int | None], None] | None = None,
    ) -> None:
        self.canvas = tk.Canvas(
            parent,
            background=theme.LIGHTBOX,
            highlightthickness=0,
            borderwidth=0,
            # Focusable, because keyboard operability is the whole
            # accessibility story this widget has.
            takefocus=True,
        )
        self._number_font = theme.font(parent, "stencil")
        self._data_font = theme.font(parent, "data")
        self._body_font = theme.font(parent, "help")
        self._items: list[Negative] = []
        self._selected: int | None = None
        self._on_select = on_select
        self._focused = False

        # Bound on the widget, never `bind_all`: a global binding would take
        # the arrow keys away from every other control in the app. Each
        # binding is a one-line adapter over a public method, so the
        # behaviour is reachable without synthesising Tk events -- which a
        # withdrawn, unmapped test window cannot deliver anyway.
        self.canvas.bind("<Button-1>", lambda event: self.select_at(int(event.y)))
        self.canvas.bind("<Up>", lambda _event: self.move_selection(-1))
        self.canvas.bind("<Down>", lambda _event: self.move_selection(1))
        self.canvas.bind("<FocusIn>", lambda _event: self.set_focused(True))
        self.canvas.bind("<FocusOut>", lambda _event: self.set_focused(False))

        # The empty state exists from construction. No call required.
        self._redraw()

    # --- public API ---------------------------------------------------------

    @property
    def count(self) -> int:
        return len(self._items)

    @property
    def items(self) -> tuple[Negative, ...]:
        """What the rows currently show. A tuple, so a caller reading the
        rendered state cannot quietly mutate it behind the redraw."""
        return tuple(self._items)

    @property
    def selected_index(self) -> int | None:
        """The row the ordering buttons act on, or None if nothing is picked."""
        return self._selected

    def set_items(self, items: Sequence[Negative]) -> None:
        """Replace every row, keeping the selection where that still means
        something.

        A reorder is a `set_items` with the same number of rows, so the
        selection is kept as-is there: the user picked position 2, and after
        Down they should still be on the row they moved. A shorter list
        clamps to the last row; an empty one clears.
        """
        previous = self._selected
        self._items = list(items)
        if not self._items:
            self._selected = None
        elif previous is not None and previous >= len(self._items):
            self._selected = len(self._items) - 1
        self._redraw()
        self._announce(previous)

    def select(self, index: int | None) -> None:
        """Move the selection programmatically. Out-of-range clears it."""
        previous = self._selected
        if index is None or not 0 <= index < len(self._items):
            self._selected = None
        else:
            self._selected = index
        self._redraw()
        self._announce(previous)

    def select_at(self, y: int) -> None:
        """Select whichever row contains `y`. A click below the last does
        nothing, rather than selecting the nearest row the user did not hit."""
        # Clicking a list is a request to use it, so take focus with it;
        # otherwise the arrow keys would do nothing until the user tabbed in.
        self.canvas.focus_set()
        if not self._items:
            return
        index = (y - PAD_Y) // ROW_HEIGHT
        if 0 <= index < len(self._items):
            self.select(index)

    def move_selection(self, delta: int) -> str:
        """Step the selection by `delta` rows, clamped at both ends.

        Returns Tk's `"break"` because it is the arrow-key handler: without
        it Tk also runs its own focus traversal on the same key, so the
        selection would move while the focus walked off the widget.
        """
        if self._items:
            if self._selected is None:
                # A first press lands on the near end rather than doing nothing.
                self.select(0 if delta > 0 else len(self._items) - 1)
            else:
                # Clamped, not wrapped. Wrapping in a list whose order is its
                # meaning is disorienting, and three rows have obvious ends.
                self.select(max(0, min(len(self._items) - 1, self._selected + delta)))
        return "break"

    def set_focused(self, focused: bool) -> None:
        """Draw, or stop drawing, the focus mark. Driven by Tk's focus events."""
        if focused == self._focused:
            return
        self._focused = focused
        self._redraw()

    def focus_set(self) -> None:
        """Give the canvas keyboard focus, as a real widget would."""
        self.canvas.focus_set()

    # --- internals ----------------------------------------------------------

    def _announce(self, previous: int | None) -> None:
        """Tell the caller only when the selection actually moved.

        The Compose tab drives its Up/Down/Remove states off this, and it
        needs the programmatic moves as much as the clicks -- a row removed
        under the cursor changes what those buttons may do.
        """
        if self._on_select is not None and previous != self._selected:
            self._on_select(self._selected)

    # --- drawing ------------------------------------------------------------

    def _redraw(self) -> None:
        # Every redraw clears first. This redraws on every add, every move,
        # every removal and every focus change; leaking items would pile
        # them up for the life of the window.
        self.canvas.delete("all")

        height = PAD_Y + (ROW_HEIGHT * len(self._items) if self._items else EMPTY_HEIGHT)
        self.canvas.configure(height=height)
        width = self.canvas.winfo_width()
        if width <= 1:
            # Before the geometry manager has a real width to report. The
            # rail is a fixed width, so this is a safe stand-in and the next
            # real draw corrects it.
            width = FALLBACK_WIDTH

        if self._items:
            for index, item in enumerate(self._items):
                self._draw_row(index, item, width)
        else:
            self.canvas.create_text(
                PAD_X,
                PAD_Y,
                text=EMPTY_CAPTION,
                fill=theme.INK_SECONDARY,
                font=self._body_font,
                anchor="nw",
                width=width - 2 * PAD_X,
                tags=("empty",),
            )

        # Focus is shown as a chinagraph rule round the widget: the one
        # saturated colour in the app, and the same mark an editor uses to
        # pick a frame. Inset by one pixel so the outline is not clipped.
        self.canvas.create_rectangle(
            0,
            0,
            width - 1,
            height - 1,
            outline=theme.CHINAGRAPH if self._focused else theme.SLEEVE,
            fill="",
            tags=("focus" if self._focused else "border",),
        )

    def _fit(self, text: str, available: int) -> str:
        """`text`, shortened from the front until it fits `available` points.

        From the front, because these filenames share a long prefix and
        differ in their last few characters -- `horizons3-hp5-4` against
        `horizons3-hp5-6` -- so the tail is the part worth keeping.
        """
        if available <= 0 or self._data_font.measure(text) <= available:
            return text
        for start in range(1, len(text)):
            candidate = ELLIPSIS + text[start:]
            if self._data_font.measure(candidate) <= available:
                return candidate
        return ELLIPSIS

    def _draw_row(self, index: int, item: Negative, width: int) -> None:
        top = PAD_Y + index * ROW_HEIGHT
        selected = index == self._selected
        tags = (f"row{index}",)

        if selected:
            self.canvas.create_rectangle(
                0,
                top,
                width,
                top + ROW_HEIGHT,
                fill=theme.SLEEVE,
                outline="",
                tags=("selection", *tags),
            )
        # The edge mark. Chinagraph on the selected row, sleeve elsewhere --
        # it is always there, so the row reads as a frame either way.
        self.canvas.create_rectangle(
            PAD_X,
            top + 2,
            PAD_X + BAR_WIDTH,
            top + ROW_HEIGHT - 2,
            fill=theme.CHINAGRAPH if selected else theme.SPROCKET,
            outline="",
            tags=("bar", *tags),
        )

        text_left = PAD_X + BAR_WIDTH + PAD_X
        self.canvas.create_text(
            text_left,
            top + NAME_ROW / 2,
            text=str(index + 1),
            fill=theme.CHINAGRAPH,
            font=self._number_font,
            anchor="w",
            tags=("number", *tags),
        )

        name_left = text_left + NUMBER_COLUMN
        # Mono, because it is the file you chose rather than what we call it.
        self.canvas.create_text(
            name_left,
            top + NAME_ROW / 2,
            # Truncated rather than wrapped: wrapping would make one row
            # taller than its neighbours and break the numbering's rhythm.
            text=self._fit(item.name, width - name_left - PAD_X),
            fill=theme.REBATE,
            font=self._data_font,
            anchor="w",
            tags=("name", *tags),
        )
        self.canvas.create_text(
            name_left,
            top + NAME_ROW + DIMENSION_ROW / 2,
            text=item.dimensions,
            fill=theme.INK_SECONDARY,
            font=self._data_font,
            anchor="w",
            tags=("dimensions", *tags),
        )
