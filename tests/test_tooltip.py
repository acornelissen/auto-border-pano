"""Tooltips: they appear after a dwell, they leave nothing behind."""

import tkinter as tk
from tkinter import ttk

import pytest

from auto_border_pano.gui import tooltip


def _tooltips(root: tk.Misc) -> list[tk.Toplevel]:
    """Every Toplevel anywhere under `root` -- a tooltip is a child of its button."""
    found: list[tk.Toplevel] = []
    for child in root.winfo_children():
        if isinstance(child, tk.Toplevel):
            found.append(child)
        found.extend(_tooltips(child))
    return found


def _texts(root: tk.Misc) -> list[str]:
    labels = []
    for window in _tooltips(root):
        for child in window.winfo_children():
            labels.append(str(child.cget("text")))
    return labels


def _button(root: tk.Misc) -> ttk.Button:
    button = ttk.Button(root, text="↑")
    button.pack()
    root.update_idletasks()
    return button


def _settle(root: tk.Tk) -> None:
    """Let every pending `after` fire."""
    root.after(tooltip.DELAY_MS * 2, root.quit)
    root.mainloop()


def test_hover_shows_after_the_delay(tk_root: tk.Tk) -> None:
    button = _button(tk_root)
    tooltip.attach(button, "Move earlier")

    button.event_generate("<Enter>")
    assert _tooltips(tk_root) == []

    _settle(tk_root)
    assert _texts(tk_root) == ["Move earlier"]


def test_leave_hides_the_tooltip(tk_root: tk.Tk) -> None:
    button = _button(tk_root)
    tooltip.attach(button, "Move later")

    button.event_generate("<Enter>")
    _settle(tk_root)
    assert len(_tooltips(tk_root)) == 1

    button.event_generate("<Leave>")
    assert _tooltips(tk_root) == []


def test_leaving_before_the_delay_cancels_it(tk_root: tk.Tk) -> None:
    button = _button(tk_root)
    tooltip.attach(button, "Remove")

    button.event_generate("<Enter>")
    button.event_generate("<Leave>")
    _settle(tk_root)

    assert _tooltips(tk_root) == []


def test_button_press_hides_the_tooltip(tk_root: tk.Tk) -> None:
    button = _button(tk_root)
    tooltip.attach(button, "Remove")

    button.event_generate("<Enter>")
    _settle(tk_root)
    assert len(_tooltips(tk_root)) == 1

    button.event_generate("<ButtonPress-1>")
    assert _tooltips(tk_root) == []


def test_repeated_hovers_leak_no_windows(tk_root: tk.Tk, monkeypatch: pytest.MonkeyPatch) -> None:
    # Fifty real dwells is fifty real waits -- this test alone cost 45s of
    # every run. The delay is not what is under test here; the reuse is.
    monkeypatch.setattr(tooltip, "DELAY_MS", 1)
    button = _button(tk_root)
    tooltip.attach(button, "Move earlier")

    for _ in range(50):
        button.event_generate("<Enter>")
        _settle(tk_root)
        assert len(_tooltips(tk_root)) == 1
        button.event_generate("<Leave>")
        assert _tooltips(tk_root) == []


def test_focus_shows_it_immediately_and_blur_hides_it(tk_root: tk.Tk) -> None:
    button = _button(tk_root)
    tooltip.attach(button, "Move earlier")

    button.event_generate("<FocusIn>")
    assert _texts(tk_root) == ["Move earlier"]

    button.event_generate("<FocusOut>")
    assert _tooltips(tk_root) == []


def test_destroying_the_widget_while_pending_does_not_raise(tk_root: tk.Tk) -> None:
    button = _button(tk_root)
    tooltip.attach(button, "Remove")

    button.event_generate("<Enter>")
    button.destroy()
    _settle(tk_root)

    assert _tooltips(tk_root) == []


def test_destroying_the_widget_while_shown_removes_the_tooltip(tk_root: tk.Tk) -> None:
    button = _button(tk_root)
    tooltip.attach(button, "Remove")

    button.event_generate("<Enter>")
    _settle(tk_root)
    assert len(_tooltips(tk_root)) == 1

    button.destroy()
    tk_root.update_idletasks()
    assert _tooltips(tk_root) == []
