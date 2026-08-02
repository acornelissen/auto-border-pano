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
from PySide6.QtWidgets import QLabel
from pytestqt.qtbot import QtBot

from maskingframe import layout, pipeline
from maskingframe.gui import compose_tab, settings, shell
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


def test_add_stops_at_six_sources(tab: ComposeTab) -> None:
    tab._accept([WIDE, TALL, SQUARE, WIDE, TALL])
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


def test_over_the_limit_takes_the_six_that_fit_and_names_the_rest(tab: ComposeTab) -> None:
    """Refusing the whole selection would be the modal this interface spent a
    stage removing; dropping them silently would be worse."""
    tab._accept([WIDE, TALL, SQUARE, WIDE, TALL, SQUARE, WIDE, TALL])

    assert tab.images == [WIDE, TALL, SQUARE, WIDE, TALL, SQUARE]
    assert "Left out" in tab.hint
    assert Path(WIDE).name in tab.hint


def test_a_full_list_leaves_a_further_pick_untouched(tab: ComposeTab) -> None:
    tab._accept([WIDE, TALL, SQUARE, WIDE, TALL, SQUARE])
    tab._accept([TALL])

    assert tab.images == [WIDE, TALL, SQUARE, WIDE, TALL, SQUARE]
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

    stale = compose_tab._Solve(token=6, name="R(1,2)", count=2, sizes={})
    tab._apply_layout_name(stale)
    assert tab.layout_name == ""
    assert tab._solved == ""

    fresh = compose_tab._Solve(token=7, name="C(1,2,3)", count=3, sizes={})
    tab._apply_layout_name(fresh)
    assert tab._solved == "C(1,2,3)"
    assert tab.layout_name == "Column of three"


def test_present_layout_reads_the_solver_name_as_a_sentence() -> None:
    """Walks the solver's own list, so an arrangement it cannot read fails
    the suite rather than reaching the rail as a formula.

    `words != name` alone would pass a partial leak -- "Row of three: 1, 2,
    C(3,4)" is not the name and is not English either -- so the notation's
    own characters are barred outright. That is what the version of this
    test before the rename got wrong: it asked for no hyphen and a capital,
    both of which raw notation satisfies, and so waved the breakage through.
    """
    seen: dict[int, set[str]] = {}
    for count in range(pipeline.MIN_IMAGES, pipeline.MAX_IMAGES + 1):
        for name, _ in layout.candidates(count):
            words = compose_tab.present_layout(name, count)
            assert words
            assert words != name, f"{name} was not read"
            assert words[0].isupper()
            assert "(" not in words and ")" not in words, f"{name} leaked notation: {words}"
            assert not any(char.isdigit() for char in words), f"{name} leaked a numeral: {words}"
            # Two arrangements reading the same sentence would put a wrong
            # description on one of them, which no other assertion here
            # would notice.
            assert words not in seen.setdefault(count, set()), f"{name} reads as an earlier one"
            seen[count].add(words)


@pytest.mark.parametrize(
    ("name", "count", "expected"),
    [
        # Rule 1: a pair is not "a row of two".
        ("R(1,2)", 2, "Side by side"),
        ("C(1,2)", 2, "One above the other"),
        # Rule 2: no grouping.
        ("R(1,2,3)", 3, "Row of three"),
        ("C(1,2,3,4,5,6)", 6, "Column of six"),
        # Rule 3: even grouping.
        ("C(R(1,2,3),R(4,5,6))", 6, "Two rows of three"),
        ("R(C(1,2),C(3,4),C(5,6))", 6, "Three columns of two"),
        # Rule 4: two uneven parts keep today's positional wording.
        ("R(1,C(2,3))", 3, "One left, two stacked right"),
        ("R(C(1,2),3)", 3, "Two stacked left, one right"),
        ("C(1,R(2,3))", 3, "One on top, two side by side below"),
        ("C(R(1,2),3)", 3, "Two side by side on top, one below"),
        # Rule 5: three or more uneven parts are listed in order.
        ("C(1,R(2,3),R(4,5,6))", 6, "Column of three: one, two side by side, three side by side"),
        ("R(1,C(2,3),4)", 4, "Row of three: one, two stacked, one"),
    ],
)
def test_present_layout_reads_a_notation_name(name: str, count: int, expected: str) -> None:
    assert compose_tab.present_layout(name, count) == expected


def test_an_unreadable_name_is_shown_rather_than_swallowed() -> None:
    assert compose_tab.present_layout("nonsense", 3) == "nonsense"
    assert compose_tab.present_layout("", 3) == ""


def test_the_save_button_names_every_composable_count() -> None:
    labels = {count: compose_tab._save_label(count) for count in range(2, 7)}
    assert labels == {
        2: "Save diptych",
        3: "Save triptych",
        4: "Save tetraptych",
        5: "Save pentaptych",
        6: "Save hexaptych",
    }


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
    assert _rail_texts(tab) == ["SOURCES", "FORMAT", "ARRANGEMENT", "BORDER", "DESTINATION"]


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
    assert tab.border_controls.gutter_slider is not None
    tab.border_controls.gutter_slider.setValue(3.0)
    assert settings.load_style(settings.COMPOSE).gutter_percent == 3.0


def test_the_rail_shows_every_line_of_its_help_text(qtbot: QtBot, tab: ComposeTab) -> None:
    """This rail carries the most help text of the two, so it is the one
    that clipped first."""
    # The worst case a real window can actually be put in: Qt derives a
    # window's minimum size from its children and refuses to go below it, so
    # the tab is shown at exactly that minimum. Settling it takes a couple of
    # passes, because the wrapped labels only learn their width once they
    # have been laid out at it.
    tab.show()
    qtbot.waitExposed(tab)
    for _ in range(3):
        tab.resize(1100, tab.minimumSizeHint().height())
        qtbot.wait(1)
    clipped = [
        label.text()
        for label in tab.findChildren(QLabel)
        if label.wordWrap()
        and label.text()
        and label.height() < label.heightForWidth(label.width())
    ]
    assert clipped == []


def test_compose_tab_offers_gutter_controls_but_no_detail_toggle(tab: ComposeTab) -> None:
    assert tab.border_controls.gutter_slider is not None
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

    assert tab.border_controls.gutter_slider is not None
    tab.border_controls.gutter_slider.setValue(11.0)
    assert tab._solve_token > before
    _settled(qtbot, tab)


def test_the_solve_carries_the_style_it_was_asked_for(
    qtbot: QtBot, tab: ComposeTab, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`name_layout` runs off the GUI thread, so the style it uses must
    travel with the request rather than being re-read inside the job."""
    seen: list[Any] = []
    original = pipeline.name_layout

    def record(
        paths: Any, ratio: Any, arrangement: str = "", style: Any = pipeline.DEFAULT_STYLE
    ) -> str:
        seen.append(style)
        return original(paths, ratio, arrangement, style=style)

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


def _wait_for_sizes(qtbot: QtBot, tab: ComposeTab) -> None:
    qtbot.waitUntil(lambda: all(path in tab._sizes for path in tab.images), timeout=5000)


def test_the_border_is_previewed_with_nothing_loaded(qtbot: QtBot) -> None:
    """The strip's single empty aperture still gets the border, at the
    target ratio, and no gaps -- there is no arrangement to solve."""
    tab = ComposeTab()
    qtbot.addWidget(tab)
    tab.previews.resize(600, 500)
    tab.border_controls.border_slider.setValue(10.0)

    preview = tab.previews.border_preview
    assert preview is not None
    assert preview.border == pytest.approx(0.1)
    assert preview.gaps == ()
    assert tab.previews.border_rects(0)


def test_the_gaps_between_panels_are_previewed_too(qtbot: QtBot) -> None:
    """Solved from the cached source shapes, so it matches what will be
    rendered rather than being a decoration."""
    tab = ComposeTab()
    qtbot.addWidget(tab)
    tab.previews.resize(600, 500)
    tab._accept([WIDE, TALL])
    _wait_for_sizes(qtbot, tab)
    tab.border_controls.gutter_slider.setValue(6.0)  # type: ignore[union-attr]

    style = tab.border_controls.frame_style()
    ratio = pipeline.RATIOS[tab._ratio_name()]
    aspects = [tab._sizes[path][0] / tab._sizes[path][1] for path in tab.images]
    expected = pipeline.composite_rects(aspects, ratio, style).gaps

    preview = tab.previews.border_preview
    assert preview is not None
    assert expected, "a nonzero gap must solve to at least one separator"
    assert tuple((g.x, g.y, g.width, g.height) for g in preview.gaps) == expected
    assert preview.gap_colour == style.gutter_colour


def test_the_panels_are_handed_over_so_the_border_includes_its_slack(qtbot: QtBot) -> None:
    """Where the pictures land decides where the border is.

    The solver centres the assembled block inside the frame's inset box, so
    the axis it does not fill leaves slack that the render paints in the
    border colour. Only the panels say where that is, so the tab hands them
    to the strip and the previewed border is the whole of the border.
    """
    tab = ComposeTab()
    qtbot.addWidget(tab)
    tab.previews.resize(600, 500)
    tab._accept([WIDE, TALL])
    _wait_for_sizes(qtbot, tab)

    style = tab.border_controls.frame_style()
    ratio = pipeline.RATIOS[tab._ratio_name()]
    aspects = [tab._sizes[path][0] / tab._sizes[path][1] for path in tab.images]
    expected = pipeline.composite_rects(aspects, ratio, style).panels

    preview = tab.previews.border_preview
    assert preview is not None
    assert len(expected) == 2
    assert tuple((p.x, p.y, p.width, p.height) for p in preview.panels) == expected


def test_one_source_gets_the_outer_border_and_no_gaps(qtbot: QtBot) -> None:
    """With fewer than two sources there is no layout to solve."""
    tab = ComposeTab()
    qtbot.addWidget(tab)
    tab.previews.resize(600, 500)
    tab._accept([WIDE])
    _wait_for_sizes(qtbot, tab)

    preview = tab.previews.border_preview
    assert preview is not None
    assert preview.gaps == ()
    assert preview.panels == ()
    assert tab.previews.border_rects(0)


# --- a render must never outlive the settings it was made under --------------


def _previewed(qtbot: QtBot, tab: ComposeTab) -> None:
    tab.previews.resize(600, 500)
    tab._accept([WIDE, TALL])
    _wait_for_sizes(qtbot, tab)
    tab.preview()
    qtbot.waitUntil(lambda: tab.previews.exposed > 0, timeout=15000)


def test_a_rendered_composite_carries_no_overlay(qtbot: QtBot, tab: ComposeTab) -> None:
    """The render already has the border and the gaps in it."""
    _previewed(qtbot, tab)

    assert tab.previews.border_rects(0) == []


def _captured_renders(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Any, Any, Any, Any]]:
    """Hold every submitted job instead of running it, so two answers can
    be landed in a chosen order."""
    captured: list[tuple[Any, Any, Any, Any]] = []
    monkeypatch.setattr(
        compose_tab,
        "submit",
        lambda job, done, failed=None, owner=None: captured.append((job, done, failed, owner)),
    )
    return captured


def test_every_job_names_the_widget_its_callbacks_touch(
    qtbot: QtBot, tab: ComposeTab, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Qt drops a queued signal only for a destroyed *bound method*, and
    `submit` connects closures, so a callback with no `owner` reaches a
    widget whose C++ half has gone and raises on the GUI thread."""
    captured = _captured_renders(monkeypatch)
    tab._accept([WIDE, TALL])
    tab.preview()
    tab.output_row.setText(str(tmp_path / "out"))
    tab.save()

    assert captured, "no job was submitted, so nothing was checked"
    assert [owner for *_rest, owner in captured] == [tab] * len(captured)


def test_changing_the_border_composes_the_frame_again(qtbot: QtBot, tab: ComposeTab) -> None:
    _previewed(qtbot, tab)

    tab.border_controls.border_slider.setValue(20.0)

    # No blanking: the old composite is up while the new one is made.
    assert tab.previews.exposed == 1
    assert tab.status == shell.UPDATING_PREVIEW
    qtbot.waitUntil(lambda: tab.status != shell.UPDATING_PREVIEW, timeout=15000)
    assert tab.previews.exposed == 1
    # A render carries its border in its pixels, so it takes no overlay.
    assert tab.previews.border_rects(0) == []


def test_dragging_the_gap_slider_does_not_compose(
    qtbot: QtBot, tab: ComposeTab, monkeypatch: pytest.MonkeyPatch
) -> None:
    _previewed(qtbot, tab)
    captured = _captured_renders(monkeypatch)
    slider = tab.border_controls.gutter_slider
    assert slider is not None

    slider.slider.setSliderDown(True)
    slider.setValue(9.0)
    # The live solve still runs on every move; a compose does not.
    assert all(call[1] != tab._finish_preview for call in captured)
    before = len(captured)

    slider.slider.setSliderDown(False)
    assert len(captured) > before
    assert tab.status == shell.UPDATING_PREVIEW


def test_changing_the_ratio_composes_the_frame_again(qtbot: QtBot, tab: ComposeTab) -> None:
    _previewed(qtbot, tab)

    tab.ratio_combo.setCurrentText(pipeline.RATIOS["1:1"].display)

    assert tab.previews.exposed == 1
    qtbot.waitUntil(lambda: "1:1" in tab.status, timeout=15000)
    assert tab.previews.exposed == 1


def test_nothing_is_composed_when_the_table_is_empty(
    qtbot: QtBot, tab: ComposeTab, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An empty frame is already showing the live overlay, which is exactly
    what the rail says."""
    tab._accept([WIDE, TALL])
    _wait_for_sizes(qtbot, tab)
    captured = _captured_renders(monkeypatch)

    tab.border_controls.border_slider.setValue(20.0)

    assert tab.previews.exposed == 0
    assert all(call[1] != tab._finish_preview for call in captured)


def test_removing_a_source_drops_the_composite(qtbot: QtBot, tab: ComposeTab) -> None:
    """A composite of a set nobody is composing any more is not worth
    remaking, and one source cannot be composed at all."""
    _previewed(qtbot, tab)
    tab.listbox.select(0)
    tab._on_select(0)

    tab.remove()

    assert tab.previews.exposed == 0


def test_a_stale_composite_does_not_overwrite_a_newer_one(
    qtbot: QtBot, tab: ComposeTab, monkeypatch: pytest.MonkeyPatch
) -> None:
    _previewed(qtbot, tab)
    captured = _captured_renders(monkeypatch)

    tab.border_controls.border_slider.setValue(12.0)
    tab.border_controls.border_slider.setValue(20.0)
    renders = [call for call in captured if call[1].__name__ == "done"]
    assert len(renders) == 2

    newest = renders[1][0]()
    renders[1][1](newest)
    settled = tab.status

    # The older job returns last, and is dropped.
    older = renders[0][0]()
    renders[0][1](older)

    assert tab.status == settled
    assert tab.previews.exposed == 1


def test_a_solve_landing_does_not_pull_a_preview_off_the_table(
    qtbot: QtBot, tab: ComposeTab
) -> None:
    """A background solve returning is new information about the settings
    in force, not a change to them. Only a change discards a render."""
    _previewed(qtbot, tab)

    tab._refresh_border_preview()

    assert tab.previews.exposed == 1


def test_compose_sees_only_its_own_presets(qtbot: QtBot, isolated_settings: Path) -> None:
    # A split border and a composite border are different decisions, so the
    # two lists never mix.
    settings.save_preset(settings.SPLIT, "Split only", pipeline.DEFAULT_STYLE)
    settings.save_preset(settings.COMPOSE, "Compose only", pipeline.DEFAULT_STYLE)
    tab = ComposeTab()
    qtbot.addWidget(tab)
    tab.border_controls.reload_presets()

    names = [
        tab.border_controls.presets.box.itemText(i)
        for i in range(tab.border_controls.presets.box.count())
    ]
    assert "Compose only" in names
    assert "Split only" not in names


def test_choosing_a_compose_preset_applies_the_gap(qtbot: QtBot, isolated_settings: Path) -> None:
    settings.save_preset(
        settings.COMPOSE,
        "Wide gap",
        pipeline.FrameStyle(gutter_percent=9.0, gutter_colour="#102030"),
    )
    tab = ComposeTab()
    qtbot.addWidget(tab)
    tab.border_controls.reload_presets()

    tab.border_controls.presets.chosen.emit("Wide gap")

    style = tab.border_controls.frame_style()
    assert style.gutter_percent == 9.0
    assert style.gutter_colour == "#102030"


def test_a_restored_compose_style_that_is_a_preset_is_named(
    qtbot: QtBot, isolated_settings: Path
) -> None:
    """Compose restores and names in its own right, not by resembling Split."""
    style = pipeline.FrameStyle(gutter_percent=9.0, gutter_colour="#102030")
    settings.save_preset(settings.COMPOSE, "Wide gap", style)
    settings.save_style(settings.COMPOSE, style)

    tab = ComposeTab()
    qtbot.addWidget(tab)

    assert tab.border_controls.frame_style() == style
    assert tab.border_controls.presets.box.currentText() == "Wide gap"


def test_a_chosen_compose_preset_survives_a_relaunch(qtbot: QtBot, isolated_settings: Path) -> None:
    """The Compose wiring is a copy of Split's, so it needs its own proof."""
    style = pipeline.FrameStyle(gutter_percent=9.0, gutter_colour="#102030")
    settings.save_preset(settings.COMPOSE, "Wide gap", style)
    tab = ComposeTab()
    qtbot.addWidget(tab)
    tab.border_controls.reload_presets()

    tab.border_controls.presets.chosen.emit("Wide gap")

    relaunched = ComposeTab()
    qtbot.addWidget(relaunched)
    assert relaunched.border_controls.frame_style() == style
    assert relaunched.border_controls.presets.box.currentText() == "Wide gap"


# --- the arrangement combo ---------------------------------------------------


def _ratio(built: ComposeTab) -> pipeline.AspectRatio:
    return pipeline.RATIOS[built._ratio_name()]


def _with_sources(qtbot: QtBot, built: ComposeTab, paths: list[str]) -> None:
    built._accept(paths)
    _settled(qtbot, built)


def test_the_arrangement_list_opens_on_automatic(qtbot: QtBot, tab: ComposeTab) -> None:
    _with_sources(qtbot, tab, [WIDE, TALL, SQUARE])

    assert tab.chosen_arrangement() == ""
    assert tab.arrangement_combo.currentIndex() == 0
    assert tab.arrangement_combo.itemText(0).startswith(compose_tab.AUTOMATIC)


def test_the_list_names_the_automatic_pick_in_its_first_entry(
    qtbot: QtBot, tab: ComposeTab
) -> None:
    """Choosing nothing still has to say what you are getting."""
    _with_sources(qtbot, tab, [WIDE, TALL, SQUARE])

    words = compose_tab.present_layout(tab.layout_name, 3)

    assert words.lower() in tab.arrangement_combo.itemText(0).lower()


def test_every_arrangement_is_offered_once(qtbot: QtBot, tab: ComposeTab) -> None:
    _with_sources(qtbot, tab, [WIDE, TALL, SQUARE, SQUARE])
    offered = [tab.arrangement_combo.itemText(i) for i in range(1, tab.arrangement_combo.count())]

    assert len(offered) == len(set(offered))
    assert len(offered) == len(pipeline.arrangements([WIDE, TALL, SQUARE, SQUARE], _ratio(tab)))


def test_choosing_an_arrangement_is_remembered_and_used(qtbot: QtBot, tab: ComposeTab) -> None:
    _with_sources(qtbot, tab, [WIDE, TALL, SQUARE])
    tab.arrangement_combo.setCurrentIndex(2)

    chosen = tab.chosen_arrangement()

    assert chosen
    assert chosen != ""
    assert pipeline.name_layout([WIDE, TALL, SQUARE], _ratio(tab), chosen) == chosen


def test_adding_a_source_drops_the_chosen_arrangement(qtbot: QtBot, tab: ComposeTab) -> None:
    """An arrangement names a shape for exactly N panels. With a different
    N it means nothing, so it goes back to automatic rather than being
    quietly ignored."""
    _with_sources(qtbot, tab, [WIDE, TALL, SQUARE])
    tab.arrangement_combo.setCurrentIndex(2)
    assert tab.chosen_arrangement()

    _with_sources(qtbot, tab, [SQUARE])

    assert tab.chosen_arrangement() == ""
    assert tab.arrangement_combo.currentIndex() == 0


def test_a_ratio_change_keeps_the_chosen_arrangement(qtbot: QtBot, tab: ComposeTab) -> None:
    """The arrangement is still valid, and dropping a deliberate choice for
    a reason the user did not ask about is what makes a control feel
    unreliable."""
    _with_sources(qtbot, tab, [WIDE, TALL, SQUARE])
    tab.arrangement_combo.setCurrentIndex(2)
    chosen = tab.chosen_arrangement()

    tab.ratio_combo.setCurrentText(pipeline.RATIOS["1.91:1"].display)
    _settled(qtbot, tab)

    assert tab.chosen_arrangement() == chosen


def test_a_border_change_keeps_the_chosen_arrangement(qtbot: QtBot, tab: ComposeTab) -> None:
    _with_sources(qtbot, tab, [WIDE, TALL, SQUARE])
    tab.arrangement_combo.setCurrentIndex(2)
    chosen = tab.chosen_arrangement()

    wider = pipeline.FrameStyle(border_percent=20.0)
    tab.border_controls.set_style(wider)
    tab._on_style_settled(wider)
    _settled(qtbot, tab)

    assert tab.chosen_arrangement() == chosen


def test_reordering_keeps_the_chosen_arrangement(qtbot: QtBot, tab: ComposeTab) -> None:
    _with_sources(qtbot, tab, [WIDE, TALL, SQUARE])
    tab.arrangement_combo.setCurrentIndex(2)
    chosen = tab.chosen_arrangement()

    tab.listbox.select(0)
    tab.move_down()
    _settled(qtbot, tab)

    assert tab.chosen_arrangement() == chosen
