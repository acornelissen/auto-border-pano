"""Tests for the GUI worker threads' error handling.

These do not create a real Tk root or display; `_run_single`/`_run_batch`
are plain functions that only touch tk objects through `root.after`, so a
stub root with an `.after` that runs the callback immediately is enough to
exercise them headlessly.
"""

import threading
from pathlib import Path
from tkinter import messagebox
from typing import Any

import pytest
from PIL import Image

from auto_border_pano import gui, pipeline
from tests.conftest import synthetic_panorama


class _StubRoot:
    """Records `after` calls and runs the callback immediately, synchronously."""

    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []

    def after(self, _delay: int, callback: Any, *args: Any) -> None:
        self.calls.append((callback, *args))
        callback(*args)


def test_preview_titles_track_the_frame_count() -> None:
    assert gui.preview_titles(2) == ["Whole", "Detail 1", "Detail 2"]
    assert gui.preview_titles(4) == [
        "Whole",
        "Detail 1",
        "Detail 2",
        "Detail 3",
        "Detail 4",
    ]


def test_preview_titles_match_output_paths_length() -> None:
    for count in (2, 3, 4, 5):
        assert len(gui.preview_titles(count)) == len(pipeline.output_paths("/tmp/x", count))


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

    stub_root = _StubRoot()
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

    stub_root = _StubRoot()
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
    _rebuild_preview_panes and the strict zip sit outside any try. If either
    raises, the Process button must still come back to "normal" via a
    finally, not be left disabled forever.
    """

    class _StubButton:
        def __init__(self) -> None:
            self.last_state: str | None = None

        def config(self, state: str) -> None:
            self.last_state = state

    app = gui.PanoramaSplitterGUI.__new__(gui.PanoramaSplitterGUI)
    app.progress = _StubVar()  # type: ignore[assignment]
    app.status = _StubVar()  # type: ignore[assignment]
    app.process_btn = _StubButton()  # type: ignore[assignment]

    def boom(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("synthetic preview failure")

    app.update_preview = boom  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="synthetic preview failure"):
        app._finish("Complete", "prefix", 3, None)

    assert app.process_btn.last_state == "normal", "Process button was left disabled"  # type: ignore[attr-defined]


class _StubVar:
    """Stand-in for a tk.DoubleVar/StringVar that just records the last value."""

    def __init__(self, value: Any = None) -> None:
        self.value: Any = value

    def set(self, value: Any) -> None:
        self.value = value

    def get(self) -> Any:
        return self.value


class _StubButton:
    def __init__(self) -> None:
        self.last_state: str | None = None

    def config(self, state: str) -> None:
        self.last_state = state


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
    app.input_path = _StubVar(str(source))  # type: ignore[assignment]
    app.output_path = _StubVar(str(tmp_path / "out"))  # type: ignore[assignment]
    app.is_folder_mode = _StubVar(False)  # type: ignore[assignment]
    app.progress = _StubVar()  # type: ignore[assignment]
    app.status = _StubVar()  # type: ignore[assignment]
    app.ratio = _StubVar(non_default_label)  # type: ignore[assignment]
    app.process_btn = _StubButton()  # type: ignore[assignment]

    app.process_images()

    assert captured.get("started") is True
    assert captured["args"] == (str(source), str(tmp_path / "out"), non_default_ratio)
    assert captured["target"] == app._run_single


def test_process_images_rejects_empty_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "pano.jpg"
    synthetic_panorama(600, 200).save(source, "JPEG", quality=95)

    errors: list[tuple[str, str]] = []
    app = gui.PanoramaSplitterGUI.__new__(gui.PanoramaSplitterGUI)
    app.input_path = _StubVar(str(source))  # type: ignore[assignment]
    app.output_path = _StubVar("")  # type: ignore[assignment]

    monkeypatch.setattr(messagebox, "showerror", lambda title, msg: errors.append((title, msg)))
    app.process_images()

    assert errors, "empty output path should have raised an error dialog"


def test_finish_message_reports_count_and_ratio(monkeypatch: pytest.MonkeyPatch) -> None:
    app = gui.PanoramaSplitterGUI.__new__(gui.PanoramaSplitterGUI)
    stub_root = _StubRoot()
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
    app.progress = _StubVar()  # type: ignore[assignment]
    app.status = _StubVar()  # type: ignore[assignment]
    app.process_btn = _StubButton()  # type: ignore[assignment]
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
    app.progress = _StubVar()  # type: ignore[assignment]
    app.status = _StubVar()  # type: ignore[assignment]
    app.process_btn = _StubButton()  # type: ignore[assignment]

    result = pipeline.BatchResult()
    assert result.total_count == 0

    messages: list[tuple[str, str]] = []
    monkeypatch.setattr(messagebox, "showinfo", lambda title, msg: messages.append((title, msg)))
    app._finish_batch(result, pipeline.DEFAULT_RATIO.name)

    assert messages == [("No panoramas found", "No JPG files found in the input folder")]
    assert app.process_btn.last_state == "normal"  # type: ignore[attr-defined]
