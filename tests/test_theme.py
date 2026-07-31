"""Tests for the light-table theme.

These need a real Tk root -- a ttk.Style has no meaning without one -- but
the root stays withdrawn, so they run the same way the other real-Tk GUI
tests in this suite do.
"""

import tkinter
from collections.abc import Iterator
from tkinter import font as tkfont
from tkinter import ttk
from typing import Any

import pytest

from auto_border_pano.gui import theme


@pytest.fixture
def root() -> Iterator[tkinter.Tk]:
    window = tkinter.Tk()
    window.withdraw()
    yield window
    window.destroy()


def options(style: ttk.Style, name: str) -> dict[str, Any]:
    """`Style.configure` is typed as returning `dict | None`; a style that was
    never configured is the None case, which is itself worth failing on."""
    configured = style.configure(name)
    assert configured is not None, f"{name} was never configured"
    return dict(configured)


def test_palette_is_the_five_documented_tokens() -> None:
    assert theme.LIGHTBOX == "#F1F4F6"
    assert theme.SLEEVE == "#DCE1E4"
    assert theme.REBATE == "#1B1D1F"
    assert theme.SPROCKET == "#8B9298"
    assert theme.CHINAGRAPH == "#D5372C"


def test_secondary_text_is_the_aa_passing_composite_not_sprocket() -> None:
    """`sprocket` on `lightbox` is 3.3:1 and fails AA for body text; the plan
    pins secondary body text to the 7.1:1 composite instead."""
    assert theme.INK_SECONDARY == "#5A5F63"
    assert theme.INK_SECONDARY != theme.SPROCKET


def test_spacing_is_a_scale_with_no_stray_values() -> None:
    assert (theme.SPACE_S, theme.SPACE_M, theme.SPACE_L) == (6, 12, 24)


def test_apply_switches_to_clam(root: tkinter.Tk) -> None:
    theme.apply(root)

    assert ttk.Style(root).theme_use() == "clam"


def test_apply_is_idempotent(root: tkinter.Tk) -> None:
    theme.apply(root)
    theme.apply(root)

    assert ttk.Style(root).theme_use() == "clam"


def test_every_font_role_resolves_to_an_installed_family(root: tkinter.Tk) -> None:
    """The fallback chains must bottom out in something Tk actually has, or
    a role silently renders in Tk's default and the type system is a lie."""
    installed = {name.lower() for name in tkfont.families(root)}

    for stack in (theme.EMULSION_STACK, theme.BODY_STACK, theme.DATA_STACK):
        resolved = theme.resolve_family(root, stack)
        assert resolved.lower() in installed, f"{resolved} not installed for {stack}"


def test_resolve_family_prefers_the_first_installed_candidate(root: tkinter.Tk) -> None:
    installed = next(iter(tkfont.families(root)))

    assert theme.resolve_family(root, ("No Such Family At All", installed)) == installed


def test_resolve_family_falls_back_to_tk_default_when_nothing_matches(root: tkinter.Tk) -> None:
    """Tk's own default may be a private family (`.AppleSystemUIFont` on
    macOS) that `families()` does not list, so assert it is usable rather
    than that it is listed."""
    fallback = theme.resolve_family(root, ("No Such Family At All",))

    assert fallback
    assert tkfont.Font(root=root, family=fallback, size=13).measure("x") > 0


def test_apply_registers_every_named_style_the_tabs_use(root: tkinter.Tk) -> None:
    theme.apply(root)
    style = ttk.Style(root)

    for name in theme.STYLE_NAMES:
        assert options(style, name) is not None


def test_primary_button_is_the_only_chinagraph_background(root: tkinter.Tk) -> None:
    theme.apply(root)
    style = ttk.Style(root)

    chinagraph_backed = [
        name
        for name in theme.STYLE_NAMES
        if options(style, name).get("background") == theme.CHINAGRAPH
    ]

    assert chinagraph_backed == ["Primary.TButton"]


def test_body_surfaces_sit_on_the_lightbox(root: tkinter.Tk) -> None:
    theme.apply(root)
    style = ttk.Style(root)

    assert options(style, "TFrame")["background"] == theme.LIGHTBOX
    assert options(style, "TLabel")["background"] == theme.LIGHTBOX


def test_entries_are_set_in_the_data_font_over_the_sleeve(root: tkinter.Tk) -> None:
    theme.apply(root)
    style = ttk.Style(root)

    assert options(style, "TEntry")["fieldbackground"] == theme.SLEEVE
    # ttk hands back the Tk font *name*, not the Font object.
    assert options(style, "TEntry")["font"] == str(theme.font(root, "data"))


def test_font_returns_the_same_object_for_a_repeated_role(root: tkinter.Tk) -> None:
    """Tk leaks a named font per call otherwise, and rebuilt previews call
    into this on every run."""
    assert theme.font(root, "body") is theme.font(root, "body")


def test_font_rejects_an_unknown_role(root: tkinter.Tk) -> None:
    with pytest.raises(KeyError):
        theme.font(root, "no-such-role")


def test_both_tabs_build_on_a_themed_root(root: tkinter.Tk) -> None:
    """`theme.apply` runs before any widget exists in `app.run`; prove the
    real tab constructors survive it, since a bad style name only fails at
    widget-construction time, never at `apply` time."""
    from auto_border_pano.gui.compose_tab import ComposeTab
    from auto_border_pano.gui.split_tab import PanoramaSplitterGUI

    theme.apply(root)
    root.configure(background=theme.LIGHTBOX)

    notebook = ttk.Notebook(root)
    page = ttk.Frame(notebook)
    PanoramaSplitterGUI(page)
    notebook.add(page, text="Split")
    compose = ComposeTab(notebook)
    notebook.add(compose.frame, text="Diptych / Triptych")

    assert ttk.Style(root).theme_use() == "clam"


def test_focus_ring_is_chinagraph(root: tkinter.Tk) -> None:
    theme.apply(root)

    assert options(ttk.Style(root), ".")["focuscolor"] == theme.CHINAGRAPH
