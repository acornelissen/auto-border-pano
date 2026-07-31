"""Tests for the Diptych / Triptych tab: `ComposeTab`, its workers and buttons."""

import threading
from pathlib import Path
from tkinter import messagebox
from typing import Any

import pytest

from auto_border_pano import pipeline
from tests.conftest import StubButton, StubVar


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
    message, path, error = calls[-1]
    assert error is None
    assert path is not None
    assert "layout" in message, f"expected the layout name in the message, got: {message!r}"
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
    _message, path, error = calls[-1]
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
    message, image, error = calls[-1]
    assert error is None
    assert image is not None
    assert "layout" in message, f"expected the layout name in the message, got: {message!r}"
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
    _message, image, error = calls[-1]
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

    tab.preview()

    assert captured.get("started") is True
    assert captured["target"] == tab._run_preview
    assert captured["args"] == (["a.jpg", "b.jpg"], pipeline.DEFAULT_RATIO.name)


def test_save_button_still_requires_an_output_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    from auto_border_pano.gui import compose_tab

    tab = compose_tab.ComposeTab.__new__(compose_tab.ComposeTab)
    tab.images = ["a.jpg", "b.jpg"]
    tab.output_path = StubVar("")  # type: ignore[assignment]

    errors: list[tuple[str, str]] = []
    monkeypatch.setattr(messagebox, "showerror", lambda title, msg: errors.append((title, msg)))

    tab.save()

    assert errors, "Save without an output prefix should have raised an error dialog"


def test_compose_tab_builds_a_working_ratio_combobox_under_real_tk() -> None:
    """Constructed via ``__new__`` (as above), the pure-logic tests would stay
    green even if ``__init__``/``_build_ui`` never ran -- e.g. if the ratio
    combobox were never wired up. Build a real ``ComposeTab`` on a withdrawn
    root so a broken constructor actually fails a committed test.
    """
    import tkinter

    from auto_border_pano import pipeline
    from auto_border_pano.gui import compose_tab

    root = tkinter.Tk()
    root.withdraw()
    try:
        tab = compose_tab.ComposeTab(root)

        assert tab.ratio.get() == pipeline.DEFAULT_RATIO.display
        assert list(tab.ratio_combo["values"]) == [r.display for r in pipeline.RATIOS.values()]
        assert tab.can_compose() is False
        assert tab.preview_btn.cget("text") == "Preview"
        assert tab.save_btn.cget("text") == "Save"
    finally:
        root.destroy()
