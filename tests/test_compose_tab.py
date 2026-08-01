"""Tests for the Qt Compose tab.

What these protect is everything the tab earned across the design stages and
which nothing in the toolkit enforces on its own:

* the rail carries the same sections, in the same order, as the Split tab;
* the interface makes its rules unbreakable rather than reporting them, so
  there is not a modal anywhere in the module;
* the arrangement shown is always one the solver returned, never a guess or
  a stale answer.

Headless: `QT_QPA_PLATFORM=offscreen`. `work.submit` runs jobs on a
`QThreadPool`, so anything that waits on a result uses `qtbot.waitUntil`,
and the token tests call the apply slot directly with hand-built data --
that is the only way to land two answers in a chosen order.
"""

from pathlib import Path
from typing import Any

import pytest
from PIL import Image
from pytestqt.qtbot import QtBot

from maskingframe import layout, pipeline
from maskingframe.gui import compose_tab, settings
from maskingframe.gui.compose_tab import ComposeTab

# Every test here builds a real ComposeTab, and the tab reads and writes the
# stored border style on construction and on every change. Without this the
# suite would read -- and overwrite -- the preferences of whoever runs it.
pytestmark = pytest.mark.usefixtures("isolated_settings")

FIXTURES = Path(__file__).parent / "fixtures"
WIDE = str(FIXTURES / "compose_wide.jpg")
TALL = str(FIXTURES / "compose_tall.jpg")
SQUARE = str(FIXTURES / "compose_square.jpg")


@pytest.fixture
def tab(qtbot: QtBot) -> ComposeTab:
    built = ComposeTab()
    qtbot.addWidget(built)
    return built


def _settled(qtbot: QtBot, built: ComposeTab) -> None:
    """Wait for the live solve to land."""
    qtbot.waitUntil(lambda: built.layout_name != "", timeout=5000)


# --- gating: the rules are unbreakable, not reported -------------------------


def test_the_buttons_are_correct_at_construction(tab: ComposeTab) -> None:
    assert tab.add_btn.isEnabled()
    assert not tab.save_btn.isEnabled()
    assert not tab.preview_btn.isEnabled()
    assert not tab.up_btn.isEnabled()
    assert not tab.down_btn.isEnabled()
    assert not tab.remove_btn.isEnabled()


def test_add_stops_at_three_sources(tab: ComposeTab) -> None:
    tab._accept([WIDE, TALL])
    assert tab.add_btn.isEnabled()

    tab._accept([SQUARE])
    assert not tab.add_btn.isEnabled()


def test_save_and_preview_need_at_least_two_sources(tab: ComposeTab) -> None:
    tab._accept([WIDE])
    assert not tab.save_btn.isEnabled()
    assert not tab.preview_btn.isEnabled()

    tab._accept([TALL])
    assert tab.save_btn.isEnabled()
    assert tab.preview_btn.isEnabled()


def test_the_reason_save_is_off_is_stated_in_the_status_line(tab: ComposeTab) -> None:
    assert tab.status == compose_tab.EMPTY_STATE
    tab._accept([WIDE])
    assert tab.status == compose_tab.ONE_MORE


def test_the_reorder_buttons_need_a_selection(tab: ComposeTab) -> None:
    tab._accept([WIDE, TALL, SQUARE])
    tab.listbox.select(None)
    assert not tab.up_btn.isEnabled()
    assert not tab.down_btn.isEnabled()
    assert not tab.remove_btn.isEnabled()


def test_up_is_off_at_the_top_and_down_at_the_bottom(tab: ComposeTab) -> None:
    tab._accept([WIDE, TALL, SQUARE])

    tab.listbox.select(0)
    assert not tab.up_btn.isEnabled()
    assert tab.down_btn.isEnabled()

    tab.listbox.select(2)
    assert tab.up_btn.isEnabled()
    assert not tab.down_btn.isEnabled()

    tab.listbox.select(1)
    assert tab.up_btn.isEnabled()
    assert tab.down_btn.isEnabled()


def test_save_names_what_it_will_write(tab: ComposeTab) -> None:
    assert tab.save_btn.text() == "Save composite"
    tab._accept([WIDE, TALL])
    assert tab.save_btn.text() == "Save diptych"
    tab._accept([SQUARE])
    assert tab.save_btn.text() == "Save triptych"


def test_the_glyph_buttons_carry_their_only_name_in_a_tooltip(tab: ComposeTab) -> None:
    assert tab.up_btn.toolTip() == "Move earlier"
    assert tab.down_btn.toolTip() == "Move later"
    assert tab.remove_btn.toolTip() == "Remove"


# --- adding several files at once --------------------------------------------


def test_add_takes_several_files_in_one_go(tab: ComposeTab) -> None:
    tab._accept([WIDE, TALL, SQUARE])

    assert tab.images == [WIDE, TALL, SQUARE]
    assert len(tab.listbox.items) == 3


def test_over_the_limit_takes_the_three_that_fit_and_names_the_rest(tab: ComposeTab) -> None:
    """Refusing the whole selection would be the modal this interface spent a
    stage removing; dropping them silently would be worse."""
    tab._accept([WIDE, TALL, SQUARE, WIDE, TALL])

    assert tab.images == [WIDE, TALL, SQUARE]
    assert "Left out" in tab.hint
    assert Path(WIDE).name in tab.hint


def test_a_full_list_leaves_a_further_pick_untouched(tab: ComposeTab) -> None:
    tab._accept([WIDE, TALL, SQUARE])
    tab._accept([TALL])

    assert tab.images == [WIDE, TALL, SQUARE]
    assert "Left out" in tab.hint


# --- reordering ---------------------------------------------------------------


def test_moving_a_source_keeps_it_selected(tab: ComposeTab) -> None:
    """So a second press moves the same one, not whatever landed under it."""
    tab._accept([WIDE, TALL, SQUARE])
    tab.listbox.select(2)

    tab.move_up()
    assert tab.images == [WIDE, SQUARE, TALL]
    assert tab.listbox.selected_index == 1

    tab.move_up()
    assert tab.images == [SQUARE, WIDE, TALL]
    assert tab.listbox.selected_index == 0


def test_move_down_walks_the_other_way(tab: ComposeTab) -> None:
    tab._accept([WIDE, TALL, SQUARE])
    tab.listbox.select(0)

    tab.move_down()

    assert tab.images == [TALL, WIDE, SQUARE]
    assert tab.listbox.selected_index == 1


def test_removing_takes_whatever_selection_the_list_settles_on(tab: ComposeTab) -> None:
    tab._accept([WIDE, TALL, SQUARE])
    tab.listbox.select(2)

    tab.remove()

    assert tab.images == [WIDE, TALL]
    assert tab._selection == tab.listbox.selected_index


# --- the live arrangement ------------------------------------------------------


def test_the_layout_name_matches_what_compose_preview_solves(qtbot: QtBot) -> None:
    """The rail and the finished composite can never disagree, because both
    come out of the same solver."""
    built = ComposeTab()
    qtbot.addWidget(built)
    built._accept([WIDE, TALL])
    _settled(qtbot, built)

    _image, solved = pipeline.compose_preview([WIDE, TALL], pipeline.DEFAULT_RATIO)

    assert built._solved == solved
    assert built.layout_name == compose_tab.present_layout(solved, 2)


def test_the_arrangement_reaches_the_status_line(qtbot: QtBot) -> None:
    built = ComposeTab()
    qtbot.addWidget(built)
    built._accept([WIDE, TALL])
    _settled(qtbot, built)

    assert built.status.startswith("Diptych, ")
    assert built.status.endswith(pipeline.DEFAULT_RATIO.name)


def test_the_name_clears_below_two_sources(qtbot: QtBot) -> None:
    built = ComposeTab()
    qtbot.addWidget(built)
    built._accept([WIDE, TALL])
    _settled(qtbot, built)

    built.listbox.select(1)
    built.remove()

    assert built.layout_name == ""
    assert built._solved == ""


def test_an_unreadable_file_shows_no_name_rather_than_a_guess(qtbot: QtBot, tmp_path: Path) -> None:
    broken = tmp_path / "broken.jpg"
    broken.write_bytes(b"not a jpeg")

    built = ComposeTab()
    qtbot.addWidget(built)
    built._accept([WIDE, str(broken)])
    qtbot.waitUntil(lambda: built.listbox.items[0].size is not None, timeout=5000)

    assert built.layout_name == ""
    assert built._solved == ""
    # The readable source still got its dimensions -- one bad file must not
    # cost the others theirs.
    assert built.listbox.items[0].size is not None


def test_changing_the_ratio_re_solves(qtbot: QtBot) -> None:
    built = ComposeTab()
    qtbot.addWidget(built)
    built._accept([WIDE, TALL])
    _settled(qtbot, built)
    first = built._solved

    landscape = pipeline.RATIOS["1.91:1"]
    built.ratio_combo.setCurrentText(landscape.display)
    qtbot.waitUntil(lambda: built._solved != "", timeout=5000)

    _image, expected = pipeline.compose_preview([WIDE, TALL], landscape)
    assert built._solved == expected
    assert built.status.endswith(landscape.name)
    assert first  # the first solve really did land, so this is a re-solve


def test_the_sizes_reach_the_rows(qtbot: QtBot) -> None:
    built = ComposeTab()
    qtbot.addWidget(built)
    built._accept([WIDE, TALL])
    _settled(qtbot, built)

    assert all(source.size is not None for source in built.listbox.items)


def test_a_stale_solve_does_not_overwrite_a_newer_one(tab: ComposeTab) -> None:
    """Add a third image while a two-image solve is in flight and the older
    reply must be dropped, not shown."""
    tab.images = [WIDE, TALL, SQUARE]
    tab._solve_token = 7

    stale = compose_tab._Solve(token=6, name="row", count=2, sizes={})
    tab._apply_layout_name(stale)
    assert tab.layout_name == ""
    assert tab._solved == ""

    fresh = compose_tab._Solve(token=7, name="column", count=3, sizes={})
    tab._apply_layout_name(fresh)
    assert tab._solved == "column"
    assert tab.layout_name == "Column of three"


def test_every_solver_arrangement_has_a_name(tab: ComposeTab) -> None:
    """Walks the solver's own candidate list, so a new arrangement cannot go
    unnamed: `present_layout` is derived, not a lookup table."""
    for count in (2, 3):
        for name, _node in layout.candidates(count):
            words = compose_tab.present_layout(name, count)
            assert words
            assert "-" not in words
            assert words[0].isupper()


def test_the_two_up_arrangements_get_their_everyday_names() -> None:
    assert compose_tab.present_layout("row", 2) == "Side by side"
    assert compose_tab.present_layout("column", 2) == "One above the other"
    assert compose_tab.present_layout("row", 3) == "Row of three"


def test_a_split_arrangement_says_which_side_each_group_is_on() -> None:
    assert compose_tab.present_layout("row-one-then-two", 3) == "One left, two stacked right"
    assert (
        compose_tab.present_layout("column-two-then-one", 3) == "Two side by side on top, one below"
    )


def test_an_unparsed_name_still_reads_as_words() -> None:
    assert compose_tab.present_layout("spiral-of-doom", 3) == "Spiral of doom"
    assert compose_tab.present_layout("", 3) == ""


# --- saving and previewing -----------------------------------------------------


def test_preview_writes_no_file(qtbot: QtBot, tmp_path: Path) -> None:
    built = ComposeTab()
    qtbot.addWidget(built)
    built._accept([WIDE, TALL])
    built.output_row.setText(str(tmp_path / "out"))

    built.preview()
    qtbot.waitUntil(lambda: built.save_btn.isEnabled(), timeout=20000)

    assert list(tmp_path.iterdir()) == []
    assert built.previews.exposed == 1
    assert built.status.startswith("Diptych, ")


def test_save_writes_the_composite_and_says_where(qtbot: QtBot, tmp_path: Path) -> None:
    built = ComposeTab()
    qtbot.addWidget(built)
    built._accept([WIDE, TALL])
    built.output_row.setText(str(tmp_path / "out"))

    built.save()
    qtbot.waitUntil(lambda: built.save_btn.isEnabled(), timeout=20000)

    written = tmp_path / "out_diptych.jpg"
    assert written.exists()
    assert built.status.startswith(f"Saved {written.name} — ")
    assert built.status.endswith(pipeline.DEFAULT_RATIO.name)


def test_a_missing_destination_is_said_inline_not_in_a_dialog(tab: ComposeTab) -> None:
    tab._accept([WIDE, TALL])
    tab.output_row.setText("")

    tab.save()

    assert tab.hint == compose_tab.NO_PREFIX
    assert tab.hint_label.objectName() == "Error"


def test_a_failure_is_reported_inline(tab: ComposeTab) -> None:
    tab._failed(OSError("cannot read source"))

    assert tab.status.startswith("Could not compose — ")
    assert tab.hint_label.objectName() == "Error"
    assert "cannot read source" in tab.hint


def test_a_later_success_clears_the_error_voice(qtbot: QtBot, tmp_path: Path) -> None:
    built = ComposeTab()
    qtbot.addWidget(built)
    built._accept([WIDE, TALL])
    built._failed(OSError("boom"))
    built.output_row.setText(str(tmp_path / "out"))

    built.save()
    qtbot.waitUntil(lambda: built.save_btn.isEnabled(), timeout=20000)

    assert built.hint == ""
    assert built.hint_label.objectName() == "Help"


def test_the_finished_frame_is_titled_with_the_arrangement(tab: ComposeTab) -> None:
    image = Image.new("RGB", (40, 50), "white")
    tab.images = [WIDE, TALL]

    tab._finish_preview(compose_tab._Previewed(image, "row", "4:5", 2))

    assert tab.previews.frame_count == 1
    assert tab.previews.caption_at(0).lower() == "row"


# --- the band -------------------------------------------------------------------


def test_the_band_counts_the_sources_and_names_the_composite(qtbot: QtBot) -> None:
    built = ComposeTab()
    qtbot.addWidget(built)
    seen: list[tuple[str, str]] = []
    built.band_changed.connect(lambda subject, detail: seen.append((subject, detail)))

    built._accept([WIDE, TALL])
    _settled(qtbot, built)

    assert built.subject == "2 sources"
    assert built.detail == f"{pipeline.DEFAULT_RATIO.name} · diptych"
    assert seen[-1] == (built.subject, built.detail)


def test_the_band_says_nothing_when_nothing_is_loaded(tab: ComposeTab) -> None:
    assert tab.subject == ""
    assert tab.detail == ""


# --- the rail matches the Split tab's -------------------------------------------


def _rail_texts(built: ComposeTab) -> list[str]:
    from PySide6.QtWidgets import QLabel

    return [
        child.text()
        for child in built.columns.rail.findChildren(QLabel)
        if child.objectName() == "Section"
    ]


def test_the_rail_reads_subject_then_format_then_destination(tab: ComposeTab) -> None:
    """Split's rail is subject, FORMAT, DESTINATION, primary. These two rails
    drifting apart is a bug that has been fixed twice."""
    assert _rail_texts(tab) == ["SOURCES", "FORMAT", "BORDER", "DESTINATION"]


def test_preview_sits_below_save_and_is_not_a_peer_of_it(tab: ComposeTab) -> None:
    rail = tab.columns.rail_layout
    order = []
    for index in range(rail.count()):
        item = rail.itemAt(index)
        order.append(None if item is None else item.widget())
    assert order.index(tab.preview_btn) > order.index(tab.save_btn)
    assert tab.save_btn.objectName() == "Primary"
    # An outlined button, not bare text: it still has to read as pressable.
    assert tab.preview_btn.objectName() == "Secondary"


def test_the_strip_is_at_the_top_of_the_table_at_its_natural_height(tab: ComposeTab) -> None:
    first = tab.columns.table_layout.itemAt(0)
    assert first is not None
    assert first.widget() is tab.previews
    assert tab.previews.frame_count == 1


# --- no modals, anywhere ---------------------------------------------------------


def test_no_modal_dialog_is_ever_constructed(
    tab: ComposeTab, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every `messagebox` call was deleted in the tkinter build and must not
    come back through Qt's door."""
    import PySide6.QtWidgets as widgets

    def forbidden(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("a modal was constructed")

    for name in ("information", "warning", "critical", "question", "about"):
        monkeypatch.setattr(widgets.QMessageBox, name, staticmethod(forbidden))
    monkeypatch.setattr(widgets.QMessageBox, "__init__", forbidden)

    tab._accept([WIDE, TALL, SQUARE, WIDE])
    tab.output_row.setText("")
    tab.save()
    tab._failed(OSError("boom"))
    tab.listbox.select(0)
    tab.move_down()
    tab.remove()


def test_the_module_never_imports_a_message_box() -> None:
    """Not even reachable: the name is not bound in the module at all."""
    assert not hasattr(compose_tab, "QMessageBox")
    source = Path(compose_tab.__file__).read_text(encoding="utf-8")
    assert "QMessageBox(" not in source
    assert "QMessageBox." not in source


# --- the border and the gap ------------------------------------------------------


def test_compose_tab_restores_the_stored_style(qtbot: QtBot) -> None:
    settings.save_style(settings.COMPOSE, pipeline.FrameStyle(gutter_percent=7.0))
    built = ComposeTab()
    qtbot.addWidget(built)
    assert built._style().gutter_percent == 7.0


def test_compose_tab_stores_a_changed_style(tab: ComposeTab) -> None:
    assert tab.border_controls.gutter_spin is not None
    tab.border_controls.gutter_spin.setValue(3.0)
    assert settings.load_style(settings.COMPOSE).gutter_percent == 3.0


def test_compose_tab_offers_gutter_controls_but_no_detail_toggle(tab: ComposeTab) -> None:
    assert tab.border_controls.gutter_spin is not None
    assert tab.border_controls.gutter_swatch is not None
    assert tab.border_controls.detail_check is None


def test_the_two_tabs_keep_separate_styles(qtbot: QtBot) -> None:
    settings.save_style(settings.SPLIT, pipeline.FrameStyle(border_percent=30.0))
    built = ComposeTab()
    qtbot.addWidget(built)
    assert built._style().border_percent == pipeline.DEFAULT_STYLE.border_percent


def test_the_border_section_sits_between_format_and_destination(tab: ComposeTab) -> None:
    """Both rails carry the same sections in the same order; switching tabs
    must not re-lay-out the window."""
    rail = tab.columns.rail_layout
    order = []
    for index in range(rail.count()):
        item = rail.itemAt(index)
        order.append(None if item is None else item.widget())
    assert order.index(tab.border_controls) > order.index(tab.ratio_combo)
    assert order.index(tab.border_controls) < order.index(tab.output_row)


def test_a_style_change_re_solves_the_arrangement(qtbot: QtBot, tab: ComposeTab) -> None:
    """The gap can change which arrangement wins, so the name in the rail
    must not go on describing the previous solution."""
    tab._accept([WIDE, TALL])
    _settled(qtbot, tab)
    before = tab._solve_token

    assert tab.border_controls.gutter_spin is not None
    tab.border_controls.gutter_spin.setValue(11.0)
    assert tab._solve_token > before
    _settled(qtbot, tab)


def test_the_solve_carries_the_style_it_was_asked_for(
    qtbot: QtBot, tab: ComposeTab, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`name_layout` runs off the GUI thread, so the style it uses must
    travel with the request rather than being re-read inside the job."""
    seen: list[Any] = []
    original = pipeline.name_layout

    def record(paths: Any, ratio: Any, style: Any = pipeline.DEFAULT_STYLE) -> str:
        seen.append(style)
        return original(paths, ratio, style)

    monkeypatch.setattr(pipeline, "name_layout", record)
    tab.border_controls.set_style(pipeline.FrameStyle(border_percent=13.0))
    tab._accept([WIDE, TALL])
    _settled(qtbot, tab)
    assert seen
    assert seen[-1].border_percent == 13.0


def test_a_stale_solve_still_loses_after_a_style_change(tab: ComposeTab) -> None:
    """A style change and a source change racing: the newer token wins,
    exactly as before."""
    tab.border_controls.set_style(pipeline.FrameStyle(gutter_percent=9.0))
    tab._on_style_changed(tab._style())
    stale = compose_tab._Solve(token=tab._solve_token - 1, name="row", count=2, sizes={})
    tab._apply_layout_name(stale)
    assert tab.layout_name == ""


def test_save_renders_with_the_chosen_style(qtbot: QtBot, tmp_path: Path) -> None:
    built = ComposeTab()
    qtbot.addWidget(built)
    built._accept([WIDE, TALL])
    built.border_controls.set_style(
        pipeline.FrameStyle(border_percent=10.0, border_colour="#000000")
    )
    built.output_row.setText(str(tmp_path / "out"))
    built.save()
    qtbot.waitUntil(lambda: built.status.startswith("Saved"), timeout=15000)
    written = next(iter(tmp_path.glob("*.jpg")))
    with Image.open(written) as composite:
        assert composite.convert("RGB").getpixel((0, 0)) == (0, 0, 0)


def test_preview_renders_with_the_chosen_style(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    built = ComposeTab()
    qtbot.addWidget(built)
    built._accept([WIDE, TALL])
    built.border_controls.set_style(
        pipeline.FrameStyle(border_percent=10.0, border_colour="#000000")
    )
    shown: list[Image.Image] = []
    monkeypatch.setattr(built.previews, "show_images", shown.extend)
    built.preview()
    qtbot.waitUntil(lambda: bool(shown), timeout=15000)
    assert shown[0].convert("RGB").getpixel((0, 0)) == (0, 0, 0)
