"""Hover and focus tooltips for the glyph buttons.

The Compose tab's reorder controls are bare up, down and remove glyphs: small,
sitting in a row, and deliberately unlabelled. A tooltip is the only thing giving them a name,
so it has to appear on keyboard focus as well as on hover -- otherwise the
controls have no accessible name at all for anyone not using a mouse.

One `attach(widget, text)` call per button. Nothing else here is public.
"""

import contextlib
import tkinter as tk

from auto_border_pano.gui import theme

DELAY_MS = 450
"""Hover dwell before the tooltip shows.

Long enough that crossing a button on the way to another one shows nothing,
short enough that a deliberate hover does not feel broken. Focus skips it:
tabbing to a control is already deliberate.
"""

_OFFSET_X = 0
_OFFSET_Y = 6


class _Tooltip:
    """One tooltip bound to one widget. Owns at most one Toplevel at a time."""

    def __init__(self, widget: tk.Misc, text: str) -> None:
        self.widget = widget
        self.text = text
        self.pending: str | None = None
        self.window: tk.Toplevel | None = None

        widget.bind("<Enter>", self.schedule, add="+")
        widget.bind("<FocusIn>", self.show, add="+")
        widget.bind("<Leave>", self.hide, add="+")
        widget.bind("<FocusOut>", self.hide, add="+")
        widget.bind("<ButtonPress>", self.hide, add="+")
        widget.bind("<Destroy>", self.hide, add="+")

    def schedule(self, _event: "tk.Event[tk.Misc] | None" = None) -> None:
        self.cancel()
        self.pending = self.widget.after(DELAY_MS, self.show)

    def cancel(self) -> None:
        if self.pending is not None:
            # The widget may already be destroyed, taking its `after` with it.
            with contextlib.suppress(tk.TclError):
                self.widget.after_cancel(self.pending)
            self.pending = None

    def show(self, _event: "tk.Event[tk.Misc] | None" = None) -> None:
        self.pending = None
        if self.window is not None:
            return
        try:
            if not self.widget.winfo_exists():
                return
            window = tk.Toplevel(self.widget)
            window.wm_overrideredirect(True)
            tk.Label(
                window,
                text=self.text,
                background=theme.REBATE,
                foreground=theme.LIGHTBOX,
                font=theme.font(self.widget, "help"),
                padx=theme.SPACE_S,
                pady=theme.SPACE_S // 2,
                borderwidth=0,
            ).pack()
            window.wm_geometry(
                f"+{self.widget.winfo_rootx() + _OFFSET_X}"
                f"+{self.widget.winfo_rooty() + self.widget.winfo_height() + _OFFSET_Y}"
            )
        except tk.TclError:  # widget died between the check and the draw
            return
        self.window = window

    def hide(self, _event: "tk.Event[tk.Misc] | None" = None) -> None:
        self.cancel()
        window, self.window = self.window, None
        if window is not None:
            with contextlib.suppress(tk.TclError):
                window.destroy()


def attach(widget: tk.Misc, text: str) -> None:
    """Give `widget` a tooltip reading `text`, on hover and on keyboard focus."""
    _Tooltip(widget, text)
