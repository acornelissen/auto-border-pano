"""Tests for the shared two-column skeleton and the rebate header band."""

import tkinter
from tkinter import ttk

import pytest

from auto_border_pano.gui import shell, theme


def test_the_rail_is_a_fixed_column_and_the_table_takes_the_rest(tk_root: tkinter.Tk) -> None:
    """The preview stops being whatever is left at the bottom and becomes the
    subject of the window. That is the whole point of the stage."""
    built = shell.TwoColumn(tk_root)

    rail = built.frame.grid_columnconfigure(0)
    table = built.frame.grid_columnconfigure(1)

    assert int(rail["minsize"]) == shell.RAIL_WIDTH
    assert int(rail["weight"]) == 0
    assert int(table["weight"]) == 1


def test_the_rail_and_the_table_are_both_real_frames(tk_root: tkinter.Tk) -> None:
    built = shell.TwoColumn(tk_root)

    assert isinstance(built.rail, ttk.Frame)
    assert isinstance(built.table, ttk.Frame)
    assert built.rail.winfo_parent() == built.table.winfo_parent()


def test_both_tabs_get_the_same_skeleton(tk_root: tkinter.Tk) -> None:
    """There is one product, not two. If the rails ever disagree, the tabs
    have drifted apart again."""
    first = shell.TwoColumn(tk_root)
    second = shell.TwoColumn(tk_root)

    assert (
        first.frame.grid_columnconfigure(0)["minsize"]
        == second.frame.grid_columnconfigure(0)["minsize"]
    )


def test_a_section_heading_is_capitalised_in_the_string(tk_root: tkinter.Tk) -> None:
    """ttk has no text-transform, so caps have to be in the text itself."""
    built = shell.TwoColumn(tk_root)

    heading = shell.section(built.rail, "Source", row=0)

    assert heading.cget("text") == "SOURCE"
    assert heading.cget("style") == "Section.TLabel"


def test_the_rebate_band_is_film_base_black(tk_root: tkinter.Tk) -> None:
    band = shell.RebateBand(tk_root)

    assert band.canvas.cget("background") == theme.REBATE


def test_the_rebate_band_shows_the_loaded_file_in_emulsion_caps(tk_root: tkinter.Tk) -> None:
    band = shell.RebateBand(tk_root)

    band.set_subject("horizons3-hp5-4.jpg")

    assert band.subject == "HORIZONS3-HP5-4.JPG"


def test_the_rebate_band_strips_the_suffix_the_way_a_lab_would(tk_root: tkinter.Tk) -> None:
    """A lab prints the frame's name on the rebate, not its file extension."""
    band = shell.RebateBand(tk_root)

    band.set_subject("horizons3-hp5-4.jpg", strip_suffix=True)

    assert band.subject == "HORIZONS3-HP5-4"


def test_the_rebate_band_says_nothing_when_nothing_is_loaded(tk_root: tkinter.Tk) -> None:
    band = shell.RebateBand(tk_root)

    assert band.subject == ""
    assert band.detail == ""


def test_the_empty_band_states_that_rather_than_going_blank(tk_root: tkinter.Tk) -> None:
    """A blank black bar reads as a rendering fault. It says what is missing."""
    band = shell.RebateBand(tk_root)

    drawn = "".join(
        band.canvas.itemcget(item, "text")  # type: ignore[no-untyped-call]
        for item in band.canvas.find_withtag("subject")
    )

    assert drawn == shell.RebateBand.NOTHING_LOADED


def test_the_band_does_not_repeat_the_window_title(tk_root: tkinter.Tk) -> None:
    """The title bar sits directly above the band already saying the app's
    name; the band's most prominent position must not spend itself on a
    duplicate of it."""
    band = shell.RebateBand(tk_root)
    band.set_subject("coastline-hp5-3.jpg", strip_suffix=True)
    band.set_detail("4:5 · 5 frames")

    drawn = "".join(
        band.canvas.itemcget(item, "text")  # type: ignore[no-untyped-call]
        for item in band.canvas.find_all()
    )

    assert "AUTO BORDER PANO" not in drawn
    assert "COASTLINE-HP5-3" in drawn


def test_the_band_carries_what_the_front_tab_will_produce(tk_root: tkinter.Tk) -> None:
    band = shell.RebateBand(tk_root)

    band.set_detail("4:5 · 5 frames")

    drawn = "".join(
        band.canvas.itemcget(item, "text")  # type: ignore[no-untyped-call]
        for item in band.canvas.find_withtag("detail")
    )

    assert drawn == "4:5 · 5 FRAMES"


def test_tracked_text_draws_one_canvas_item_per_character(tk_root: tkinter.Tk) -> None:
    """Letter-spacing is Canvas-only, one create_text per character at a
    computed offset. If this ever collapses to a single item the tracking
    has silently stopped working."""
    band = shell.RebateBand(tk_root)

    band.set_subject("ABC")

    glyphs = band.canvas.find_withtag("subject")

    drawn = [
        band.canvas.itemcget(item, "text")  # type: ignore[no-untyped-call]
        for item in glyphs
    ]

    assert drawn == ["A", "B", "C"]


def test_redrawing_the_band_does_not_accumulate_stale_items(tk_root: tkinter.Tk) -> None:
    """The band redraws on every file selection and on every resize; leaking
    an item per redraw would pile thousands of them onto the canvas."""
    band = shell.RebateBand(tk_root)

    band.set_subject("ABC")
    after_first = len(band.canvas.find_all())
    for _ in range(5):
        band.set_subject("ABC")

    assert len(band.canvas.find_all()) == after_first


def test_the_real_app_wiring_builds_and_feeds_the_band(tk_root: tkinter.Tk) -> None:
    """`app.run` is the one path no test exercised, because it ends in
    `mainloop`. It reaches into both tabs for the vars that drive the band,
    so a tab that grows or loses one crashes at launch while every other
    test stays green. This builds exactly what `run` builds, minus the loop.
    """
    from auto_border_pano.gui.compose_tab import ComposeTab
    from auto_border_pano.gui.split_tab import PanoramaSplitterGUI

    band = shell.RebateBand(tk_root)
    band.canvas.grid(row=0, column=0, sticky=(tkinter.W, tkinter.E))

    notebook = ttk.Notebook(tk_root)
    notebook.grid(row=1, column=0, sticky=(tkinter.W, tkinter.E, tkinter.N, tkinter.S))
    page = ttk.Frame(notebook)
    page.columnconfigure(0, weight=1)
    page.rowconfigure(0, weight=1)
    split = PanoramaSplitterGUI(page)
    notebook.add(page, text="Split")
    compose = ComposeTab(notebook)
    notebook.add(compose.frame, text="Compose")

    tabs: list[shell.BandSubject] = [split, compose]

    def show_current(*_args: object) -> None:
        current = tabs[int(notebook.index("current"))]  # type: ignore[no-untyped-call]
        band.set_subject(current.subject.get(), strip_suffix=True)
        band.set_detail(current.detail.get())

    for tab in tabs:
        tab.subject.trace_add("write", show_current)
        tab.detail.trace_add("write", show_current)
    notebook.bind("<<NotebookTabChanged>>", show_current)
    show_current()

    # Both tabs must carry both vars, or the band cannot be fed from either.
    for tab in tabs:
        assert isinstance(tab.subject, tkinter.StringVar)
        assert isinstance(tab.detail, tkinter.StringVar)

    split.subject.set("coastline-hp5-3.jpg")
    split.detail.set("4:5 · 5 frames")

    assert band.subject == "COASTLINE-HP5-3"
    assert band.detail == "4:5 · 5 FRAMES"


def test_a_path_field_rides_at_its_tail_on_both_rails(tk_root: tkinter.Tk) -> None:
    """The filename is the only part of a path anybody recognises, and it is
    the part Tk clips. `shell.path_entry` is what stops the two rails
    solving that differently, or one of them not solving it at all."""
    tk_root.geometry("600x200")
    frame = ttk.Frame(tk_root)
    frame.grid(row=0, column=0, sticky="ew")
    frame.columnconfigure(0, weight=1)
    tk_root.columnconfigure(0, weight=1)

    variable = tkinter.StringVar()
    entry = shell.path_entry(frame, variable)
    tk_root.update()

    variable.set("/Users/albert/Pictures/a-long-directory-name/coastline-hp5-3.jpg")
    tk_root.update()

    assert entry.index("@0") > 0, "the field is still showing the head of the path"


def test_a_path_field_leaves_the_view_alone_while_it_has_focus(
    tk_root: tkinter.Tk, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Yanking the view to the end under someone typing, or with the caret
    mid-path, would be the interface fighting them.

    A withdrawn window cannot hold keyboard focus -- `focus_get()` is always
    None here -- so the guard is driven directly rather than through a real
    focus that this environment will not grant.
    """
    tk_root.geometry("600x200")
    frame = ttk.Frame(tk_root)
    frame.grid(row=0, column=0, sticky="ew")
    frame.columnconfigure(0, weight=1)
    tk_root.columnconfigure(0, weight=1)

    variable = tkinter.StringVar()
    entry = shell.path_entry(frame, variable)
    tk_root.update()

    variable.set("/Users/albert/Pictures/a-long-directory-name/coastline-hp5-3.jpg")
    tk_root.update()
    assert entry.index("@0") > 0, "precondition: an unfocused field rides at its tail"

    monkeypatch.setattr(type(entry), "focus_get", lambda self: entry)
    entry.xview_moveto(0.0)
    shell.show_tail(entry)
    tk_root.update()

    assert entry.index("@0") == 0, "the view was moved under a focused field"
