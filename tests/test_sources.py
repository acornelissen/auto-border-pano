"""Tests for the numbered sources list.

The list replaces a `tk.Listbox`, so what these tests protect is everything
the Listbox gave for free and this widget has to hand-write: selection,
keyboard operability, and not leaking canvas items on rebuild. Plus the two
promises the design plan makes about it -- that the rows are numbered
frames, and that an empty list says what to do rather than showing a box.
"""

import tkinter

from auto_border_pano.gui import sources, theme


def _texts(built: sources.SourcesList, tag: str) -> list[str]:
    return [
        built.canvas.itemcget(item, "text")  # type: ignore[no-untyped-call]
        for item in built.canvas.find_withtag(tag)
    ]


def _items(count: int) -> list[sources.Source]:
    return [sources.Source(f"/tmp/source{index}.jpg", (4000, 1700)) for index in range(count)]


def test_the_empty_state_is_drawn_at_construction_with_no_call(tk_root: tkinter.Tk) -> None:
    """The Listbox's empty state was a bare black box that told you nothing."""
    built = sources.SourcesList(tk_root)

    assert _texts(built, "empty") == [sources.EMPTY_CAPTION]
    assert built.count == 0
    assert built.selected_index is None


def test_a_row_carries_its_number_its_name_and_its_dimensions(tk_root: tkinter.Tk) -> None:
    built = sources.SourcesList(tk_root)

    built.set_items([sources.Source("/photos/horizons3-hp5-4.jpg", (4000, 1700))])

    assert _texts(built, "number") == ["1"]
    assert _texts(built, "name") == ["horizons3-hp5-4.jpg"]
    assert _texts(built, "dimensions") == ["4000 × 1700"]  # noqa: RUF001
    assert built.canvas.find_withtag("empty") == ()


def test_the_number_is_chinagraph_like_the_contact_strip(tk_root: tkinter.Tk) -> None:
    """The ordering control and the result speak one language: the number
    is the arrangement, so it is marked the way the strip marks a frame."""
    built = sources.SourcesList(tk_root)
    built.set_items(_items(2))

    numbers = built.canvas.find_withtag("number")

    assert [built.canvas.itemcget(item, "fill") for item in numbers] == [  # type: ignore[no-untyped-call]
        theme.CHINAGRAPH,
        theme.CHINAGRAPH,
    ]


def test_the_numbers_renumber_when_the_order_changes(tk_root: tkinter.Tk) -> None:
    built = sources.SourcesList(tk_root)
    first = sources.Source("/photos/a.jpg", (10, 10))
    second = sources.Source("/photos/b.jpg", (10, 10))
    built.set_items([first, second])

    built.set_items([second, first])

    assert _texts(built, "number") == ["1", "2"]
    assert _texts(built, "name") == ["b.jpg", "a.jpg"]


def test_a_row_renders_before_its_dimensions_have_been_read(tk_root: tkinter.Tk) -> None:
    """Headers are read off the main thread, so a row exists before it knows
    its own size."""
    built = sources.SourcesList(tk_root)

    built.set_items([sources.Source("/photos/horizons3-hp5-4.jpg")])

    assert _texts(built, "name") == ["horizons3-hp5-4.jpg"]
    assert _texts(built, "dimensions") == [sources.PENDING_DIMENSIONS]


def test_the_height_follows_the_rows_rather_than_a_fixed_four(tk_root: tkinter.Tk) -> None:
    """The Listbox was `height=4` for a list capped at 3, so one row was
    always dead space."""
    built = sources.SourcesList(tk_root)
    built.set_items(_items(2))
    two = int(built.canvas.cget("height"))

    built.set_items(_items(3))

    assert int(built.canvas.cget("height")) > two
    assert int(built.canvas.cget("height")) == sources.PAD_Y + 3 * sources.ROW_HEIGHT


def test_clicking_a_row_selects_it_and_fires_the_callback(tk_root: tkinter.Tk) -> None:
    seen: list[int | None] = []
    built = sources.SourcesList(tk_root, on_select=seen.append)
    built.set_items(_items(3))

    built.select_at(sources.PAD_Y + sources.ROW_HEIGHT + 2)

    assert built.selected_index == 1
    assert seen == [1]


def test_clicking_past_the_last_row_does_not_select(tk_root: tkinter.Tk) -> None:
    built = sources.SourcesList(tk_root)
    built.set_items(_items(2))

    built.select_at(sources.PAD_Y + 9 * sources.ROW_HEIGHT)

    assert built.selected_index is None


def test_the_selected_row_is_marked_in_chinagraph(tk_root: tkinter.Tk) -> None:
    built = sources.SourcesList(tk_root)
    built.set_items(_items(2))

    built.select(1)

    bars = built.canvas.find_withtag("bar")
    fills = [built.canvas.itemcget(item, "fill") for item in bars]  # type: ignore[no-untyped-call]
    assert fills == [theme.SPROCKET, theme.CHINAGRAPH]
    assert len(built.canvas.find_withtag("selection")) == 1


def test_the_arrow_keys_move_the_selection(tk_root: tkinter.Tk) -> None:
    """Hand-written control, no accessibility story on macOS Tk: keyboard
    operability is the mitigation, not a nicety."""
    seen: list[int | None] = []
    built = sources.SourcesList(tk_root, on_select=seen.append)
    built.set_items(_items(3))

    built.move_selection(1)
    assert built.selected_index == 0
    built.move_selection(1)
    built.move_selection(1)
    assert built.selected_index == 2
    built.move_selection(-1)

    assert built.selected_index == 1
    assert seen == [0, 1, 2, 1]


def test_the_arrow_keys_stop_at_the_ends(tk_root: tkinter.Tk) -> None:
    built = sources.SourcesList(tk_root)
    built.set_items(_items(2))
    built.select(0)

    for _ in range(3):
        built.move_selection(-1)
    assert built.selected_index == 0

    for _ in range(5):
        built.move_selection(1)
    assert built.selected_index == 1


def test_the_arrows_do_nothing_on_an_empty_list(tk_root: tkinter.Tk) -> None:
    built = sources.SourcesList(tk_root)

    built.move_selection(1)

    assert built.selected_index is None


def test_the_widget_takes_focus_and_shows_it(tk_root: tkinter.Tk) -> None:
    built = sources.SourcesList(tk_root)
    built.set_items(_items(2))
    assert built.canvas.find_withtag("focus") == ()

    built.set_focused(True)

    assert built.canvas.cget("takefocus") in ("1", 1, True)
    focus = built.canvas.find_withtag("focus")
    assert len(focus) == 1
    assert built.canvas.itemcget(focus[0], "outline") == theme.CHINAGRAPH  # type: ignore[no-untyped-call]

    built.set_focused(False)
    assert built.canvas.find_withtag("focus") == ()


def test_the_keyboard_and_click_bindings_are_on_the_widget_not_globally(
    tk_root: tkinter.Tk,
) -> None:
    """`bind_all` would steal the arrow keys from every other control."""
    built = sources.SourcesList(tk_root)

    for sequence in ("<Button-1>", "<Up>", "<Down>", "<FocusIn>", "<FocusOut>"):
        assert built.canvas.bind(sequence), sequence
        assert sequence not in tk_root.bind_all()


def test_the_arrow_handler_breaks_so_focus_does_not_walk_off(tk_root: tkinter.Tk) -> None:
    """Without "break" Tk also runs its own focus traversal on the same key."""
    built = sources.SourcesList(tk_root)
    built.set_items(_items(2))

    assert built.move_selection(1) == "break"


def test_the_selection_survives_a_reorder(tk_root: tkinter.Tk) -> None:
    """A move is a `set_items` at the same length: the user stays on the row
    they just moved."""
    seen: list[int | None] = []
    built = sources.SourcesList(tk_root, on_select=seen.append)
    first = sources.Source("/photos/a.jpg", (10, 10))
    second = sources.Source("/photos/b.jpg", (10, 10))
    built.set_items([first, second])
    built.select(1)
    seen.clear()

    built.set_items([second, first])

    assert built.selected_index == 1
    assert seen == []


def test_the_selection_is_clamped_when_the_last_row_goes(tk_root: tkinter.Tk) -> None:
    seen: list[int | None] = []
    built = sources.SourcesList(tk_root, on_select=seen.append)
    built.set_items(_items(3))
    built.select(2)
    seen.clear()

    built.set_items(_items(2))

    assert built.selected_index == 1
    assert seen == [1]


def test_the_selection_clears_when_the_list_empties(tk_root: tkinter.Tk) -> None:
    seen: list[int | None] = []
    built = sources.SourcesList(tk_root, on_select=seen.append)
    built.set_items(_items(2))
    built.select(1)
    seen.clear()

    built.set_items([])

    assert built.selected_index is None
    assert seen == [None]
    assert _texts(built, "empty") == [sources.EMPTY_CAPTION]


def test_selecting_out_of_range_clears_rather_than_raising(tk_root: tkinter.Tk) -> None:
    built = sources.SourcesList(tk_root)
    built.set_items(_items(2))
    built.select(1)

    built.select(9)

    assert built.selected_index is None


def test_reselecting_the_same_row_does_not_fire_again(tk_root: tkinter.Tk) -> None:
    seen: list[int | None] = []
    built = sources.SourcesList(tk_root, on_select=seen.append)
    built.set_items(_items(2))

    built.select(1)
    built.select(1)

    assert seen == [1]


def test_rebuilding_the_list_does_not_accumulate_canvas_items(tk_root: tkinter.Tk) -> None:
    """This redraws on every add, move, removal and focus change."""
    built = sources.SourcesList(tk_root)
    built.set_items(_items(3))
    built.set_items(_items(2))
    after_first = len(built.canvas.find_all())

    for _ in range(5):
        built.set_items(_items(2))

    assert len(built.canvas.find_all()) == after_first
    assert len(built.canvas.find_withtag("number")) == 2


def test_a_long_filename_is_truncated_to_the_widget(tk_root: tkinter.Tk) -> None:
    built = sources.SourcesList(tk_root)

    built.set_items([sources.Source("/photos/" + "horizons-" * 12 + ".jpg", (10, 10))])

    drawn = _texts(built, "name")[0]
    assert drawn.startswith(sources.ELLIPSIS)
    assert drawn.endswith(".jpg")
