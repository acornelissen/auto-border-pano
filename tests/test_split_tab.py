"""Tests for the Split tab: `PanoramaSplitterGUI`, its worker threads and previews."""

import threading
from pathlib import Path
from tkinter import messagebox
from typing import Any

import pytest
from PIL import Image

from auto_border_pano import gui, pipeline
from tests.conftest import StubButton, StubRoot, StubVar, synthetic_panorama


def test_run_single_survives_non_oserror_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A worker thread must never die silently, even on a non-OSError exception.

    PIL.Image.DecompressionBombError subclasses Exception directly, not
    OSError or ValueError, so a narrow except tuple lets it kill the daemon
    thread before `_finish` is ever scheduled -- the Process button stays
    disabled and the status stays "Working..." forever.
    """

    def boom(*_args: Any, **_kwargs: Any) -> list[Path]:
        raise Image.DecompressionBombError("synthetic bomb")

    monkeypatch.setattr(pipeline, "process_image", boom)

    stub_root = StubRoot()
    app = gui.PanoramaSplitterGUI.__new__(gui.PanoramaSplitterGUI)
    app.root = stub_root  # type: ignore[assignment]
    finished: list[tuple[str, str | None, int | None, str | None]] = []
    app._finish = lambda message, prefix, count, error: finished.append(  # type: ignore[method-assign]
        (message, prefix, count, error)
    )

    app._run_single(str(tmp_path / "pano.jpg"), str(tmp_path / "out"), pipeline.DEFAULT_RATIO.name)

    assert stub_root.calls, "root.after was never scheduled -- worker died silently"
    assert finished == [("Failed", None, None, "synthetic bomb")]


def test_run_batch_survives_non_oserror_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """process_folder itself already swallows per-file exceptions (see
    test_process_folder_continues_after_a_bad_file in test_pipeline.py), so
    to exercise _run_batch's own except clause we need process_folder to
    raise directly -- e.g. a failure outside the per-file loop.
    """
    source_dir = tmp_path / "in"
    source_dir.mkdir()
    synthetic_panorama(600, 200).save(source_dir / "a.jpg", "JPEG", quality=95)

    def boom(*_args: Any, **_kwargs: Any) -> pipeline.BatchResult:
        raise Image.DecompressionBombError("synthetic bomb")

    monkeypatch.setattr(pipeline, "process_folder", boom)

    stub_root = StubRoot()
    app = gui.PanoramaSplitterGUI.__new__(gui.PanoramaSplitterGUI)
    app.root = stub_root  # type: ignore[assignment]
    finished: list[tuple[str, str | None, int | None, str | None]] = []
    app._finish = lambda message, prefix, count, error: finished.append(  # type: ignore[method-assign]
        (message, prefix, count, error)
    )

    app._run_batch(str(source_dir), str(tmp_path / "out"), pipeline.DEFAULT_RATIO.name)

    assert stub_root.calls, "root.after was never scheduled -- worker died silently"
    assert finished == [("Failed", None, None, "synthetic bomb")]


def test_finish_reenables_button_even_if_update_preview_raises() -> None:
    """A surprise exception from update_preview must not wedge the GUI.

    update_preview's own except Exception only covers the image-decode step;
    PreviewPanes.rebuild and the strict zip sit outside any try. If either
    raises, the Process button must still come back to "normal" via a
    finally, not be left disabled forever.
    """

    class _StubButton:
        def __init__(self) -> None:
            self.last_state: str | None = None

        def config(self, state: str) -> None:
            self.last_state = state

    app = gui.PanoramaSplitterGUI.__new__(gui.PanoramaSplitterGUI)
    app.progress = StubVar()  # type: ignore[assignment]
    app.status = StubVar()  # type: ignore[assignment]
    app.process_btn = _StubButton()  # type: ignore[assignment]

    def boom(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("synthetic preview failure")

    app.update_preview = boom  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="synthetic preview failure"):
        app._finish("Complete", "prefix", 3, None)

    assert app.process_btn.last_state == "normal", "Process button was left disabled"  # type: ignore[attr-defined]


def test_process_images_threads_the_selected_ratio_not_the_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """process_images is the only code that reads self.ratio.get() and hands it
    to the worker thread. If the combobox were bound to the wrong StringVar, or
    process_images passed the default instead of the selection, every other
    test would still pass while the GUI silently ignored the user's choice.
    """
    source = tmp_path / "pano.jpg"
    synthetic_panorama(600, 200).save(source, "JPEG", quality=95)
    non_default_ratio = "1.91:1"
    non_default_label = pipeline.RATIOS[non_default_ratio].display
    assert non_default_ratio != pipeline.DEFAULT_RATIO.name

    captured: dict[str, Any] = {}

    class _StubThread:
        def __init__(self, target: Any, args: tuple[Any, ...], daemon: bool) -> None:
            captured["target"] = target
            captured["args"] = args
            captured["daemon"] = daemon

        def start(self) -> None:
            captured["started"] = True

    monkeypatch.setattr(threading, "Thread", _StubThread)

    app = gui.PanoramaSplitterGUI.__new__(gui.PanoramaSplitterGUI)
    app.input_path = StubVar(str(source))  # type: ignore[assignment]
    app.output_path = StubVar(str(tmp_path / "out"))  # type: ignore[assignment]
    app.is_folder_mode = StubVar(False)  # type: ignore[assignment]
    app.progress = StubVar()  # type: ignore[assignment]
    app.status = StubVar()  # type: ignore[assignment]
    app.ratio = StubVar(non_default_label)  # type: ignore[assignment]
    app.process_btn = StubButton()  # type: ignore[assignment]

    app.process_images()

    assert captured.get("started") is True
    assert captured["args"] == (str(source), str(tmp_path / "out"), non_default_ratio)
    assert captured["target"] == app._run_single


def test_process_images_falls_back_to_default_ratio_for_an_unrecognised_label(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The label-to-ratio lookup in process_images must be total. The readonly
    combobox can never produce a value outside pipeline.RATIOS today, but a
    future caller setting self.ratio programmatically (a saved preference, a
    test, a CLI-to-GUI handoff) must degrade to the documented default
    instead of raising StopIteration/KeyError.
    """
    source = tmp_path / "pano.jpg"
    synthetic_panorama(600, 200).save(source, "JPEG", quality=95)

    captured: dict[str, Any] = {}

    class _StubThread:
        def __init__(self, target: Any, args: tuple[Any, ...], daemon: bool) -> None:
            captured["target"] = target
            captured["args"] = args
            captured["daemon"] = daemon

        def start(self) -> None:
            captured["started"] = True

    monkeypatch.setattr(threading, "Thread", _StubThread)

    app = gui.PanoramaSplitterGUI.__new__(gui.PanoramaSplitterGUI)
    app.input_path = StubVar(str(source))  # type: ignore[assignment]
    app.output_path = StubVar(str(tmp_path / "out"))  # type: ignore[assignment]
    app.is_folder_mode = StubVar(False)  # type: ignore[assignment]
    app.progress = StubVar()  # type: ignore[assignment]
    app.status = StubVar()  # type: ignore[assignment]
    app.ratio = StubVar("Not A Real Label (9:9)")  # type: ignore[assignment]
    app.process_btn = StubButton()  # type: ignore[assignment]

    app.process_images()

    assert captured.get("started") is True
    assert captured["args"] == (
        str(source),
        str(tmp_path / "out"),
        pipeline.DEFAULT_RATIO.name,
    )
    assert captured["target"] == app._run_single


def test_process_images_rejects_empty_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "pano.jpg"
    synthetic_panorama(600, 200).save(source, "JPEG", quality=95)

    errors: list[tuple[str, str]] = []
    app = gui.PanoramaSplitterGUI.__new__(gui.PanoramaSplitterGUI)
    app.input_path = StubVar(str(source))  # type: ignore[assignment]
    app.output_path = StubVar("")  # type: ignore[assignment]

    monkeypatch.setattr(messagebox, "showerror", lambda title, msg: errors.append((title, msg)))
    app.process_images()

    assert errors, "empty output path should have raised an error dialog"


def test_finish_message_reports_count_and_ratio(monkeypatch: pytest.MonkeyPatch) -> None:
    app = gui.PanoramaSplitterGUI.__new__(gui.PanoramaSplitterGUI)
    stub_root = StubRoot()
    app.root = stub_root  # type: ignore[assignment]

    written = [Path("/tmp/out_1_padded.jpg"), Path("/tmp/out_2_section1.jpg")]
    monkeypatch.setattr(pipeline, "process_image", lambda *a, **k: written)
    finished: list[tuple[str, str | None, int | None, str | None]] = []
    app._finish = lambda message, prefix, count, error: finished.append(  # type: ignore[method-assign]
        (message, prefix, count, error)
    )

    app._run_single("src.jpg", "out", "1.91:1")

    assert finished == [("Wrote 1 detail frames at Landscape (1.91:1)", "out", 1, None)]


def test_finish_batch_reports_count_and_ratio(monkeypatch: pytest.MonkeyPatch) -> None:
    app = gui.PanoramaSplitterGUI.__new__(gui.PanoramaSplitterGUI)
    app.progress = StubVar()  # type: ignore[assignment]
    app.status = StubVar()  # type: ignore[assignment]
    app.process_btn = StubButton()  # type: ignore[assignment]
    app.update_preview = lambda *a, **k: None  # type: ignore[method-assign]

    result = pipeline.BatchResult(
        written=[Path("/tmp/a_1_padded.jpg")],
        last_prefix=Path("/tmp/a"),
        last_count=1,
        succeeded_count=1,
    )

    messages: list[tuple[str, str]] = []
    monkeypatch.setattr(messagebox, "showinfo", lambda title, msg: messages.append((title, msg)))
    app._finish_batch(result, "1.91:1")

    assert app.status.value == "Wrote 1 of 1 images at Landscape (1.91:1)"  # type: ignore[attr-defined]
    assert messages == [("Success", "Wrote 1 of 1 images at Landscape (1.91:1)")]


def test_finish_batch_reports_no_panoramas_found_instead_of_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A JPEG-free folder gives succeeded_count=0, failed=[], total_count=0.
    Showing a green "Success" dialog for that would tell the user files were
    written when nothing was processed at all.
    """
    app = gui.PanoramaSplitterGUI.__new__(gui.PanoramaSplitterGUI)
    app.progress = StubVar()  # type: ignore[assignment]
    app.status = StubVar()  # type: ignore[assignment]
    app.process_btn = StubButton()  # type: ignore[assignment]

    result = pipeline.BatchResult()
    assert result.total_count == 0

    messages: list[tuple[str, str]] = []
    monkeypatch.setattr(messagebox, "showinfo", lambda title, msg: messages.append((title, msg)))
    app._finish_batch(result, pipeline.DEFAULT_RATIO.name)

    assert messages == [("No panoramas found", "No JPG files found in the input folder")]
    assert app.process_btn.last_state == "normal"  # type: ignore[attr-defined]


def test_split_tab_builds_under_a_notebook_page_with_working_previews(tmp_path: Path) -> None:
    """Every splitter test above builds `PanoramaSplitterGUI` via `__new__`,
    which never runs `_build_ui` -- so a broken constructor, such as one
    that assumes `self.root` is the Tk root rather than a notebook page,
    would stay green forever. Build a real instance under a `ttk.Frame`
    (as `gui.app.run` does, nesting it inside a notebook) on a withdrawn
    root, and exercise `update_preview` against real preview panes.
    """
    import tkinter
    from tkinter import ttk

    from auto_border_pano import gui, pipeline

    source = tmp_path / "pano.jpg"
    synthetic_panorama(600, 200).save(source, "JPEG", quality=95)
    written = pipeline.process_image(source, tmp_path / "out", pipeline.DEFAULT_RATIO)
    count = len(written) - 1

    root = tkinter.Tk()
    root.withdraw()
    try:
        page = ttk.Frame(root)
        app = gui.PanoramaSplitterGUI(page)

        assert app.ratio.get() == pipeline.DEFAULT_RATIO.display
        assert app.previews.labels == []

        app.update_preview(str(tmp_path / "out"), count)

        assert len(app.previews.labels) == count + 1
        for label in app.previews.labels:
            assert label.cget("text") == ""
    finally:
        root.destroy()
