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


def test_preview_titles_matches_output_suffixes_count() -> None:
    # gui.update_preview zips these with strict=True; a length mismatch
    # would raise at runtime with every other test still passing.
    assert len(gui.PREVIEW_TITLES) == len(pipeline.OUTPUT_SUFFIXES)


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
    finished: list[tuple[str, str | None, str | None]] = []
    app._finish = lambda message, prefix, error: finished.append((message, prefix, error))  # type: ignore[method-assign]

    app._run_single(str(tmp_path / "pano.jpg"), str(tmp_path / "out"))

    assert stub_root.calls, "root.after was never scheduled -- worker died silently"
    assert finished == [("Failed", None, "synthetic bomb")]


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
    finished: list[tuple[str, str | None, str | None]] = []
    app._finish = lambda message, prefix, error: finished.append((message, prefix, error))  # type: ignore[method-assign]

    app._run_batch(str(source_dir), str(tmp_path / "out"))

    assert stub_root.calls, "root.after was never scheduled -- worker died silently"
    assert finished == [("Failed", None, "synthetic bomb")]
