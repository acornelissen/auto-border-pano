"""Tests for the Diptych / Triptych tab: `ComposeTab`, its workers and buttons."""

import threading
import tkinter
from pathlib import Path
from typing import Any

import pytest

from auto_border_pano import pipeline
from tests.conftest import StubButton, StubVar


class _StubLabel:
    """Records the style a ttk.Label would have been given."""

    def __init__(self) -> None:
        self.style: str | None = None

    def configure(self, style: str) -> None:
        self.style = style


def test_compose_tab_requires_two_or_three_images() -> None:
    from auto_border_pano.gui import compose_tab

    tab = compose_tab.ComposeTab.__new__(compose_tab.ComposeTab)
    tab.images = ["a.jpg"]
    assert not tab.can_compose()
    tab.images = ["a.jpg", "b.jpg"]
    assert tab.can_compose()
    tab.images = ["a.jpg", "b.jpg", "c.jpg"]
    assert tab.can_compose()
    tab.images = ["a.jpg", "b.jpg", "c.jpg", "d.jpg"]
    assert not tab.can_compose()


def test_compose_tab_reordering_changes_the_order() -> None:
    from auto_border_pano.gui import compose_tab

    tab = compose_tab.ComposeTab.__new__(compose_tab.ComposeTab)
    tab.images = ["a.jpg", "b.jpg", "c.jpg"]
    tab._selection = 2
    tab._swap(2, 1)
    assert tab.images == ["a.jpg", "c.jpg", "b.jpg"]


def test_compose_worker_reports_the_layout_name(tmp_path: Path) -> None:
    # The worker runs off the main thread and must hand everything back
    # through root.after -- the same discipline as the splitter's workers.
    from auto_border_pano.gui import compose_tab

    fixtures = Path(__file__).parent / "fixtures"
    sources = [str(fixtures / "compose_wide.jpg"), str(fixtures / "compose_square.jpg")]

    calls: list[tuple[Any, ...]] = []

    class StubRoot:
        def after(self, _delay: int, func: Any, *args: Any) -> None:
            calls.append(args)
            func(*args)

    tab = compose_tab.ComposeTab.__new__(compose_tab.ComposeTab)
    tab.root = StubRoot()  # type: ignore[assignment]
    tab._finish = lambda *args: calls.append(args)  # type: ignore[method-assign]

    tab._run_compose(sources, str(tmp_path / "out"), "4:5")

    assert calls, "worker never reported back through root.after"
    message, path, error, layout_name = calls[-1]
    assert error is None
    assert path is not None
    assert layout_name, "worker reported no layout name"
    assert message == f"Saved out_diptych.jpg — {layout_name}, 4:5"
    assert (tmp_path / "out_diptych.jpg").exists()


def test_compose_worker_reports_failure_without_dying(tmp_path: Path) -> None:
    from auto_border_pano.gui import compose_tab

    calls: list[tuple[Any, ...]] = []

    class StubRoot:
        def after(self, _delay: int, func: Any, *args: Any) -> None:
            calls.append(args)
            func(*args)

    tab = compose_tab.ComposeTab.__new__(compose_tab.ComposeTab)
    tab.root = StubRoot()  # type: ignore[assignment]
    tab._finish = lambda *args: calls.append(args)  # type: ignore[method-assign]

    tab._run_compose(["/does/not/exist.jpg", "/nor/this.jpg"], str(tmp_path / "out"), "4:5")

    assert calls, "worker died silently instead of reporting the error"
    message, path, error = calls[-1]
    assert message.startswith("Could not compose — ")
    assert error is not None, "worker reported success for images that do not exist"
    assert path is None


def test_compose_worker_preview_does_not_write_a_file(tmp_path: Path) -> None:
    # Preview must reach pipeline.compose_preview with the same discipline
    # as Save's worker (plain data in, root.after out) but never touch disk.
    from auto_border_pano.gui import compose_tab

    fixtures = Path(__file__).parent / "fixtures"
    sources = [str(fixtures / "compose_wide.jpg"), str(fixtures / "compose_square.jpg")]

    calls: list[tuple[Any, ...]] = []

    class StubRoot:
        def after(self, _delay: int, func: Any, *args: Any) -> None:
            calls.append(args)
            func(*args)

    tab = compose_tab.ComposeTab.__new__(compose_tab.ComposeTab)
    tab.root = StubRoot()  # type: ignore[assignment]
    tab._finish_preview = lambda *args: calls.append(args)  # type: ignore[method-assign]

    before = set(tmp_path.iterdir())
    tab._run_preview(sources, "4:5")

    assert calls, "preview worker never reported back through root.after"
    message, image, error, layout_name = calls[-1]
    assert error is None
    assert image is not None
    # The status line rests on what the user has configured; the solved
    # arrangement travels separately, for the stencil under the frame.
    assert message == f"Diptych, {compose_tab.present_layout(layout_name, 2).lower()}, 4:5"
    assert layout_name, "expected the solved layout name alongside the image"
    assert set(tmp_path.iterdir()) == before, "preview must not write any file"


def test_compose_worker_preview_reports_failure_without_dying(tmp_path: Path) -> None:
    from auto_border_pano.gui import compose_tab

    calls: list[tuple[Any, ...]] = []

    class StubRoot:
        def after(self, _delay: int, func: Any, *args: Any) -> None:
            calls.append(args)
            func(*args)

    tab = compose_tab.ComposeTab.__new__(compose_tab.ComposeTab)
    tab.root = StubRoot()  # type: ignore[assignment]
    tab._finish_preview = lambda *args: calls.append(args)  # type: ignore[method-assign]

    tab._run_preview(["/does/not/exist.jpg", "/nor/this.jpg"], "4:5")

    assert calls, "preview worker died silently instead of reporting the error"
    message, image, error = calls[-1]
    assert message.startswith("Could not compose — ")
    assert error is not None
    assert image is None


def test_preview_button_does_not_require_an_output_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    from auto_border_pano.gui import compose_tab

    captured: dict[str, Any] = {}

    class _StubThread:
        def __init__(self, target: Any, args: tuple[Any, ...], daemon: bool) -> None:
            captured["target"] = target
            captured["args"] = args

        def start(self) -> None:
            captured["started"] = True

    monkeypatch.setattr(threading, "Thread", _StubThread)

    tab = compose_tab.ComposeTab.__new__(compose_tab.ComposeTab)
    tab.images = ["a.jpg", "b.jpg"]
    tab.output_path = StubVar("")  # type: ignore[assignment]
    tab.ratio = StubVar(pipeline.DEFAULT_RATIO.display)  # type: ignore[assignment]
    tab.status = StubVar()  # type: ignore[assignment]
    tab.preview_btn = StubButton()  # type: ignore[assignment]
    tab.save_btn = StubButton()  # type: ignore[assignment]
    tab.hint = StubVar("")  # type: ignore[assignment]
    tab.hint_label = _StubLabel()  # type: ignore[assignment]

    tab.preview()

    assert captured.get("started") is True
    assert captured["target"] == tab._run_preview
    assert captured["args"] == (["a.jpg", "b.jpg"], pipeline.DEFAULT_RATIO.name)


def test_save_without_an_output_prefix_says_so_inline(monkeypatch: pytest.MonkeyPatch) -> None:
    """No modal any more -- the reason and the fix go in the inline hint."""
    from auto_border_pano.gui import compose_tab

    started: list[bool] = []

    class _StubThread:
        def __init__(self, target: Any, args: tuple[Any, ...], daemon: bool) -> None:
            pass

        def start(self) -> None:
            started.append(True)

    monkeypatch.setattr(threading, "Thread", _StubThread)

    tab = compose_tab.ComposeTab.__new__(compose_tab.ComposeTab)
    tab.images = ["a.jpg", "b.jpg"]
    tab.output_path = StubVar("")  # type: ignore[assignment]
    hint_label = _StubLabel()
    tab.hint = StubVar("")  # type: ignore[assignment]
    tab.hint_label = hint_label  # type: ignore[assignment]

    tab.save()

    assert not started, "Save ran the worker without an output prefix"
    assert tab.hint.get() == "Choose where the composite should go."
    assert hint_label.style == "Error.TLabel"


def test_compose_tab_builds_a_working_ratio_combobox_under_real_tk(tk_root: tkinter.Tk) -> None:
    """Constructed via ``__new__`` (as above), the pure-logic tests would stay
    green even if ``__init__``/``_build_ui`` never ran -- e.g. if the ratio
    combobox were never wired up. Build a real ``ComposeTab`` on a withdrawn
    root so a broken constructor actually fails a committed test.
    """
    from auto_border_pano import pipeline
    from auto_border_pano.gui import compose_tab

    tab = compose_tab.ComposeTab(tk_root)

    assert tab.ratio.get() == pipeline.DEFAULT_RATIO.display
    assert list(tab.ratio_combo["values"]) == [r.display for r in pipeline.RATIOS.values()]
    assert tab.can_compose() is False
    assert tab.preview_btn.cget("text") == "Preview"
    assert tab.save_btn.cget("text") == "Save composite"
    assert tab.status.get() == compose_tab.EMPTY_STATE
    assert tab.hint.get() == compose_tab.EMPTY_STATE


def _state(button: Any) -> str:
    return str(button.cget("state"))


def _tk_tab(tk_root: tkinter.Tk) -> Any:
    from auto_border_pano.gui import compose_tab

    return compose_tab.ComposeTab(tk_root)


def test_add_is_disabled_once_three_images_are_listed(tk_root: tkinter.Tk) -> None:
    tab = _tk_tab(tk_root)
    assert _state(tab.add_btn) == "normal"
    tab.images = ["a.jpg", "b.jpg", "c.jpg"]
    tab._refresh_list()
    assert _state(tab.add_btn) == "disabled"
    tab.images = ["a.jpg", "b.jpg"]
    tab._refresh_list()
    assert _state(tab.add_btn) == "normal"


def test_save_and_preview_are_disabled_below_two_images_with_a_reason(tk_root: tkinter.Tk) -> None:
    from auto_border_pano.gui import compose_tab

    tab = _tk_tab(tk_root)
    assert _state(tab.save_btn) == "disabled"
    assert _state(tab.preview_btn) == "disabled"
    assert tab.hint.get() == compose_tab.EMPTY_STATE

    tab.images = ["a.jpg"]
    tab._refresh_list()
    assert _state(tab.save_btn) == "disabled"
    assert _state(tab.preview_btn) == "disabled"
    assert tab.hint.get() == compose_tab.ONE_MORE

    tab.images = ["a.jpg", "b.jpg"]
    tab._refresh_list()
    assert _state(tab.save_btn) == "normal"
    assert _state(tab.preview_btn) == "normal"
    assert tab.hint.get() == ""


def test_save_button_names_what_it_will_write(tk_root: tkinter.Tk) -> None:
    tab = _tk_tab(tk_root)
    assert tab.save_btn.cget("text") == "Save composite"
    tab.images = ["a.jpg", "b.jpg"]
    tab._refresh_list()
    assert tab.save_btn.cget("text") == "Save diptych"
    tab.images = ["a.jpg", "b.jpg", "c.jpg"]
    tab._refresh_list()
    assert tab.save_btn.cget("text") == "Save triptych"


def test_status_names_the_composite_and_the_bare_ratio(tk_root: tkinter.Tk) -> None:
    from auto_border_pano.gui import compose_tab

    tab = _tk_tab(tk_root)
    assert tab.status.get() == compose_tab.EMPTY_STATE
    tab.images = ["a.jpg", "b.jpg"]
    tab._refresh_list()
    assert tab.status.get() == "Diptych, 4:5"
    tab.images = ["a.jpg", "b.jpg", "c.jpg"]
    tab._refresh_list()
    assert tab.status.get() == "Triptych, 4:5"


def test_the_rail_names_the_same_layout_the_composite_gets(tk_root: tkinter.Tk) -> None:
    """The name in the rail and the name under the finished composite come
    from one solve; if they ever disagree the rail is lying."""
    from auto_border_pano.gui import compose_tab

    fixtures = Path(__file__).parent / "fixtures"
    sources = [
        str(fixtures / "compose_wide.jpg"),
        str(fixtures / "compose_square.jpg"),
        str(fixtures / "compose_tall.jpg"),
    ]
    _, expected = pipeline.compose_preview(sources, pipeline.DEFAULT_RATIO)

    tab = _tk_tab(tk_root)
    tab.images = list(sources)
    tab._run_name_layout(tab._solve_token, sources, pipeline.DEFAULT_RATIO.name)
    tk_root.update()
    assert tab._solved == expected
    assert tab.layout_name.get() == compose_tab.present_layout(expected, 3)
    assert tab.status.get() == f"Triptych, {compose_tab.present_layout(expected, 3).lower()}, 4:5"


def test_the_layout_name_is_blank_below_two_images_and_for_unreadable_files(
    tk_root: tkinter.Tk,
) -> None:
    tab = _tk_tab(tk_root)
    tab.images = ["a.jpg"]
    tab._refresh_list()
    assert tab.layout_name.get() == ""

    tab.images = ["/does/not/exist.jpg", "/nor/this.jpg"]
    tab._run_name_layout(tab._solve_token, tab.images, "4:5")
    tk_root.update()
    assert tab.layout_name.get() == ""
    assert tab.status.get() == "Diptych, 4:5"


def test_changing_the_ratio_re_solves_the_layout(
    tk_root: tkinter.Tk, monkeypatch: pytest.MonkeyPatch
) -> None:
    requested: list[tuple[Any, ...]] = []

    class _StubThread:
        def __init__(self, target: Any, args: tuple[Any, ...], daemon: bool) -> None:
            requested.append(args)

        def start(self) -> None:
            pass

    tab = _tk_tab(tk_root)
    tab.images = ["a.jpg", "b.jpg"]
    monkeypatch.setattr(threading, "Thread", _StubThread)
    tab.ratio.set(pipeline.RATIOS["1:1"].display)
    tab._on_ratio_change()

    assert requested, "changing the ratio did not re-solve the layout"
    _token, sources, ratio_name = requested[-1]
    assert sources == ["a.jpg", "b.jpg"]
    assert ratio_name == "1:1"


def test_a_late_solve_does_not_overwrite_a_newer_one(tk_root: tkinter.Tk) -> None:
    """The user can add a third image before the two-image solve returns."""
    from auto_border_pano.gui import compose_tab

    tab = _tk_tab(tk_root)
    tab.images = ["a.jpg", "b.jpg"]
    stale_token = tab._solve_token
    # A newer request supersedes the one in flight.
    tab.images = ["a.jpg", "b.jpg", "c.jpg"]
    tab._refresh_list()
    tab._apply_layout_name(tab._solve_token, "row", 3, {})
    assert tab.layout_name.get() == compose_tab.present_layout("row", 3)

    tab._apply_layout_name(stale_token, "column", 2, {})
    assert tab.layout_name.get() == compose_tab.present_layout("row", 3)
    assert tab._solved == "row"


def test_present_layout_reads_the_solver_name_as_a_sentence() -> None:
    from auto_border_pano import layout
    from auto_border_pano.gui import compose_tab

    assert compose_tab.present_layout("row", 3) == "Row of three"
    assert compose_tab.present_layout("row-one-then-two", 3) == "Row one then two"
    assert compose_tab.present_layout("", 3) == ""
    # Two panels have an everyday name for their arrangement; three do not.
    assert compose_tab.present_layout("row", 2) == "Side by side"
    assert compose_tab.present_layout("column", 2) == "One above the other"
    # Every arrangement the solver can return is presentable, so nothing has
    # to be added here when the solver gains one.
    for count in (2, 3):
        for name, _node in layout.candidates(count):
            assert compose_tab.present_layout(name, count)[0].isupper()


def test_reorder_buttons_are_disabled_without_a_selection(tk_root: tkinter.Tk) -> None:
    tab = _tk_tab(tk_root)
    tab.images = ["a.jpg", "b.jpg", "c.jpg"]
    tab._refresh_list()
    assert _state(tab.up_btn) == "disabled"
    assert _state(tab.down_btn) == "disabled"
    assert _state(tab.remove_btn) == "disabled"


def test_up_is_disabled_at_the_top_and_down_at_the_bottom(tk_root: tkinter.Tk) -> None:
    tab = _tk_tab(tk_root)
    tab.images = ["a.jpg", "b.jpg", "c.jpg"]

    tab._selection = 0
    tab._refresh_list()
    assert _state(tab.up_btn) == "disabled"
    assert _state(tab.down_btn) == "normal"
    assert _state(tab.remove_btn) == "normal"

    tab._selection = 1
    tab._refresh_list()
    assert _state(tab.up_btn) == "normal"
    assert _state(tab.down_btn) == "normal"

    tab._selection = 2
    tab._refresh_list()
    assert _state(tab.up_btn) == "normal"
    assert _state(tab.down_btn) == "disabled"


def test_finishing_a_save_opens_no_dialog(
    tk_root: tkinter.Tk, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The success modal is gone: the status line already said it."""
    from tkinter import messagebox

    def _explode(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("compose tab opened a dialog")

    monkeypatch.setattr(messagebox, "showinfo", _explode)
    monkeypatch.setattr(messagebox, "showerror", _explode)

    tab = _tk_tab(tk_root)
    tab.images = ["a.jpg", "b.jpg"]
    tab._refresh_list()
    tab._finish("Saved out_diptych.jpg — two up, 4:5", None, None, "two up")
    assert tab.status.get() == "Saved out_diptych.jpg — two up, 4:5"


def test_a_compose_failure_is_reported_inline(
    tk_root: tkinter.Tk, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tkinter import messagebox

    def _explode(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("compose tab opened a dialog")

    monkeypatch.setattr(messagebox, "showerror", _explode)

    tab = _tk_tab(tk_root)
    tab.images = ["a.jpg", "b.jpg"]
    tab._refresh_list()
    tab._finish("Could not compose — no such file", None, "no such file")
    assert tab.hint.get() == "no such file"
    assert str(tab.hint_label.cget("style")) == "Error.TLabel"


def test_the_rows_gain_their_dimensions_once_the_headers_are_read(
    tk_root: tkinter.Tk, tmp_path: Path
) -> None:
    """The list shows each negative's pixel size, but the sizes come off a
    worker thread. A row must render before they arrive and pick them up
    after, without a second solve being kicked off in the process."""
    from PIL import Image

    first = tmp_path / "a.jpg"
    second = tmp_path / "b.jpg"
    Image.new("RGB", (4000, 1700), "grey").save(first, "JPEG")
    Image.new("RGB", (1200, 1600), "grey").save(second, "JPEG")

    tab = _tk_tab(tk_root)
    tab.images = [str(first), str(second)]
    tab._refresh_list()

    # Before the worker reports: rows exist, sizes do not.
    assert tab.listbox.count == 2
    assert tab.listbox.items[0].size is None

    token = tab._solve_token
    sizes = {str(first): (4000, 1700), str(second): (1200, 1600)}
    tab._apply_layout_name(token, "row", 2, sizes)

    assert [item.size for item in tab.listbox.items] == [(4000, 1700), (1200, 1600)]
    assert tab._solve_token == token, "applying sizes must not start another solve"


def test_moving_a_negative_keeps_it_selected(tk_root: tkinter.Tk) -> None:
    """Order is the composite's order, so the thing you are moving has to
    stay the thing you are moving -- otherwise a second press moves whatever
    happened to land under it."""
    tab = _tk_tab(tk_root)
    tab.images = ["a.jpg", "b.jpg", "c.jpg"]
    tab._refresh_list()
    tab.listbox.select(2)

    tab.move_up()

    assert tab.images == ["a.jpg", "c.jpg", "b.jpg"]
    assert tab.listbox.selected_index == 1
    assert tab._selection == 1

    tab.move_up()

    assert tab.images == ["c.jpg", "a.jpg", "b.jpg"]
    assert tab.listbox.selected_index == 0


def test_removing_a_negative_leaves_a_sane_selection(tk_root: tkinter.Tk) -> None:
    tab = _tk_tab(tk_root)
    tab.images = ["a.jpg", "b.jpg", "c.jpg"]
    tab._refresh_list()
    tab.listbox.select(2)

    tab.remove()

    assert tab.images == ["a.jpg", "b.jpg"]
    assert tab._selection == tab.listbox.selected_index
    assert tab._selection is None or 0 <= tab._selection < 2
