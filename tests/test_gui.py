"""Tests for the GUI worker threads' error handling.

These do not create a real Tk root or display; `_run_single`/`_run_batch`
are plain functions that only touch tk objects through `root.after`, so a
stub root with an `.after` that runs the callback immediately is enough to
exercise them headlessly.
"""

from pathlib import Path
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

    def __init__(self) -> None:
        self.value: Any = None

    def set(self, value: Any) -> None:
        self.value = value
