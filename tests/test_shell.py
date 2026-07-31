"""Tests for the shared two-column skeleton and the rebate header band."""

import tkinter
from tkinter import ttk

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

    heading = shell.section(built.rail, "Negative", row=0)

    assert heading.cget("text") == "NEGATIVE"
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
