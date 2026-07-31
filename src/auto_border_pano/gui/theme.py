"""The light-table theme: five colours, three type roles, one spacing scale.

The app is not a darkroom. It never asks you to judge tone -- tone is fixed
the moment the scan is made -- it asks you to judge layout. So the chrome is
a light table rather than the dark grey every other photo tool inherits, and
the white border in the output reads as the paper margin it is instead of as
glare.

Everything here is presentation only. No widget in this module knows what a
panorama is, and nothing outside `gui/` imports it.

`apply()` switches ttk to `clam`. That is not cosmetic: under macOS's native
`aqua` theme ttk ignores `background`, `fieldbackground` and `bordercolor`
outright, so none of the palette below would take effect. Losing the native
look is the deliberate trade.
"""

import tkinter as tk
from collections.abc import Sequence
from tkinter import font as tkfont
from tkinter import ttk
from typing import Literal

# --- Colour -----------------------------------------------------------------
# Five tokens, no more. `chinagraph` earns its salience by being the only
# saturated colour in the app; a second accent would cost the primary action
# its primacy.

LIGHTBOX = "#F1F4F6"
"""The table surface. Cool white, ~5200K. Window and panel background."""

SLEEVE = "#DCE1E4"
"""Polypropylene negative sleeve. Recessed areas and input wells."""

REBATE = "#1B1D1F"
"""Film base. The strip, the header band, primary text. 15.4:1 on lightbox."""

SPROCKET = "#8B9298"
"""Sprocket-hole grey. Rules, disabled states, large-text-only utility copy."""

CHINAGRAPH = "#D5372C"
"""The grease pencil an editor marks selects with. Primary action and errors."""

INK_SECONDARY = "#5A5F63"
"""Secondary body text: `rebate` at 70% over `lightbox`, 7.1:1.

`sprocket` is 3.3:1 on `lightbox`, which clears WCAG AA only at the 3:1
large-text threshold. Anything smaller than 12pt semibold uses this instead.
"""

# --- Spacing ----------------------------------------------------------------
# One scale, three steps. Every padx/pady in the GUI is one of these, so
# things that belong together look like it.

SPACE_S = 6
SPACE_M = 12
SPACE_L = 24

# --- Type -------------------------------------------------------------------
# Three roles. Anything the machine measured -- paths, pixel dimensions,
# ratios, counts -- is set in `data`, which is what separates "the file you
# chose" from "what we call it" at a glance.

EMULSION_STACK = (
    "Avenir Next Condensed",
    "Helvetica Neue Condensed Bold",
    "Oswald",
    "Helvetica Neue",
    "Helvetica",
)
BODY_STACK = ("Avenir Next", "Inter", "Helvetica Neue", "Helvetica")
DATA_STACK = ("SF Mono", "Menlo", "Courier New", "Courier")

_ROLES: dict[str, tuple[Sequence[str], int, Literal["normal", "bold"]]] = {
    # role         stack           size  weight
    "band": (EMULSION_STACK, 26, "bold"),
    "heading": (BODY_STACK, 19, "bold"),
    "action": (BODY_STACK, 15, "normal"),
    "body": (BODY_STACK, 13, "normal"),
    "stencil": (EMULSION_STACK, 12, "bold"),
    "data": (DATA_STACK, 11, "normal"),
    "help": (BODY_STACK, 11, "normal"),
}

STYLE_NAMES = (
    "TFrame",
    "TLabel",
    "TEntry",
    "TButton",
    "TCombobox",
    "TRadiobutton",
    "TNotebook",
    "TNotebook.Tab",
    "Horizontal.TProgressbar",
    "Section.TLabel",
    "Stencil.TLabel",
    "Data.TLabel",
    "Help.TLabel",
    "Error.TLabel",
    "Heading.TLabel",
    "Primary.TButton",
    "Link.TButton",
)

# Tk owns named fonts per interpreter, and a fresh `tkfont.Font` leaks a new
# one on every call. The previews rebuild on every run, so cache per root.
_font_cache: dict[tuple[int, str], tkfont.Font] = {}
_family_cache: dict[tuple[int, tuple[str, ...]], str] = {}


def resolve_family(root: tk.Misc, stack: Sequence[str]) -> str:
    """First installed family in `stack`, or Tk's own default if none is."""
    key = (id(root.tk), tuple(stack))
    cached = _family_cache.get(key)
    if cached is not None:
        return cached

    installed = {name.lower(): name for name in tkfont.families(root)}
    for candidate in stack:
        found = installed.get(candidate.lower())
        if found is not None:
            _family_cache[key] = found
            return found

    fallback = tkfont.nametofont("TkDefaultFont", root).cget("family")
    _family_cache[key] = fallback
    return fallback


def font(root: tk.Misc, role: str) -> tkfont.Font:
    """The font for a type role, resolved against what is actually installed."""
    stack, size, weight = _ROLES[role]
    key = (id(root.tk), role)
    cached = _font_cache.get(key)
    if cached is not None:
        return cached

    resolved = tkfont.Font(root=root, family=resolve_family(root, stack), size=size, weight=weight)
    _font_cache[key] = resolved
    return resolved


def apply(root: tk.Misc) -> None:
    """Put the whole app on the light table. Safe to call more than once."""
    style = ttk.Style(root)
    style.theme_use("clam")

    body = font(root, "body")

    style.configure(
        ".",
        background=LIGHTBOX,
        foreground=REBATE,
        fieldbackground=SLEEVE,
        bordercolor=SPROCKET,
        lightcolor=LIGHTBOX,
        darkcolor=LIGHTBOX,
        troughcolor=SLEEVE,
        focuscolor=CHINAGRAPH,
        font=body,
    )

    style.configure("TFrame", background=LIGHTBOX)
    style.configure("TLabel", background=LIGHTBOX, foreground=REBATE, font=body)

    style.configure(
        "TEntry",
        fieldbackground=SLEEVE,
        foreground=REBATE,
        insertcolor=REBATE,
        borderwidth=0,
        relief="flat",
        padding=(SPACE_S, SPACE_S),
        font=font(root, "data"),
    )
    style.map(
        "TEntry",
        fieldbackground=[("disabled", LIGHTBOX)],
        foreground=[("disabled", SPROCKET)],
    )

    style.configure(
        "TButton",
        background=SLEEVE,
        foreground=REBATE,
        bordercolor=SPROCKET,
        borderwidth=1,
        relief="flat",
        padding=(SPACE_M, SPACE_S),
        font=body,
    )
    style.map(
        "TButton",
        background=[("pressed", SPROCKET), ("active", "#CDD3D7"), ("disabled", LIGHTBOX)],
        foreground=[("disabled", SPROCKET)],
        # A disabled button keeps its edge. Filled with the panel colour and
        # borderless it stops reading as a button at all -- grey text floating
        # on the rail looks like a rendering fault rather than "not yet".
        bordercolor=[("disabled", "#C3C9CD")],
    )

    style.configure(
        "Primary.TButton",
        background=CHINAGRAPH,
        foreground=LIGHTBOX,
        bordercolor=CHINAGRAPH,
        padding=(SPACE_M, SPACE_S + 2),
        font=font(root, "action"),
    )
    style.map(
        "Primary.TButton",
        background=[("pressed", "#A82A21"), ("active", "#C13129"), ("disabled", SLEEVE)],
        foreground=[("disabled", SPROCKET)],
        bordercolor=[("disabled", SLEEVE)],
    )

    # "Preview" is free and reversible; it must not read as a peer of the
    # action that writes to disk.
    style.configure(
        "Link.TButton",
        background=LIGHTBOX,
        foreground=INK_SECONDARY,
        borderwidth=0,
        relief="flat",
        padding=(0, SPACE_S),
        font=body,
    )
    style.map(
        "Link.TButton",
        background=[("active", LIGHTBOX), ("pressed", LIGHTBOX)],
        foreground=[("active", REBATE), ("disabled", SPROCKET)],
    )

    style.configure(
        "TCombobox",
        fieldbackground=SLEEVE,
        background=SLEEVE,
        foreground=REBATE,
        arrowcolor=REBATE,
        bordercolor=SPROCKET,
        borderwidth=0,
        padding=(SPACE_S, SPACE_S),
        font=body,
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", SLEEVE)],
        selectbackground=[("readonly", SLEEVE)],
        selectforeground=[("readonly", REBATE)],
    )
    # The dropdown list is a raw Tk widget the style engine cannot reach.
    root.option_add("*TCombobox*Listbox.background", LIGHTBOX)
    root.option_add("*TCombobox*Listbox.foreground", REBATE)
    root.option_add("*TCombobox*Listbox.selectBackground", CHINAGRAPH)
    root.option_add("*TCombobox*Listbox.selectForeground", LIGHTBOX)

    style.configure(
        "TRadiobutton",
        background=LIGHTBOX,
        foreground=REBATE,
        indicatorcolor=LIGHTBOX,
        font=body,
    )
    style.map(
        "TRadiobutton",
        indicatorcolor=[("selected", CHINAGRAPH)],
        background=[("active", LIGHTBOX)],
    )

    # The tabs start at the same gutter as the control rail below them.
    # Flush against the window edge they read as a rendering fault, and
    # nothing else in the app touches the edge.
    style.configure("TNotebook", background=LIGHTBOX, borderwidth=0, tabmargins=(SPACE_L, 0, 0, 0))
    style.configure(
        "TNotebook.Tab",
        background=SLEEVE,
        foreground=INK_SECONDARY,
        bordercolor=SLEEVE,
        padding=(SPACE_L, SPACE_S + 2),
        font=font(root, "action"),
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", LIGHTBOX)],
        foreground=[("selected", REBATE)],
        # clam grows the selected tab by default, so the two tabs render at
        # different sizes and the active one sits lower than its neighbour.
        # Pin the expansion to nothing; colour alone says which is selected.
        expand=[("selected", [0, 0, 0, 0])],
    )

    style.configure(
        "Horizontal.TProgressbar",
        # Not chinagraph. The accent is reserved for the primary action; a
        # progress bar that competes with it costs the button its primacy.
        background=REBATE,
        troughcolor=SLEEVE,
        bordercolor=SLEEVE,
        borderwidth=0,
        lightcolor=REBATE,
        darkcolor=REBATE,
    )

    # Caps are applied in the string, not by the style -- ttk has no
    # text-transform. `sprocket` is legible here because these are 12pt bold.
    style.configure("Section.TLabel", foreground=SPROCKET, font=font(root, "stencil"))
    style.configure("Stencil.TLabel", foreground=SPROCKET, font=font(root, "stencil"))
    style.configure("Heading.TLabel", foreground=REBATE, font=font(root, "heading"))
    style.configure("Data.TLabel", foreground=INK_SECONDARY, font=font(root, "data"))
    style.configure("Help.TLabel", foreground=INK_SECONDARY, font=font(root, "help"))
    style.configure("Error.TLabel", foreground=CHINAGRAPH, font=font(root, "help"))
