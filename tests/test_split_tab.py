"""Tests for the Split tab: `PanoramaSplitterGUI`, its worker threads and previews."""

import threading
import tkinter
from pathlib import Path
from tkinter import messagebox
from typing import Any

import pytest
from PIL import Image

from auto_border_pano import gui, pipeline
from auto_border_pano.gui import split_tab
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
    assert finished == [("Could not cut pano.jpg — synthetic bomb", None, None, "synthetic bomb")]


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
    assert finished == [("Could not cut in — synthetic bomb", None, None, "synthetic bomb")]


def test_finish_reenables_button_even_if_update_preview_raises() -> None:
    """A surprise exception from update_preview must not wedge the GUI.

    update_preview's own except Exception only covers the image-decode step;
    ContactStrip.set_frames and the strict zip sit outside any try. If either
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
    app.error = StubVar("")  # type: ignore[assignment]
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
    app.error = StubVar("")  # type: ignore[assignment]
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
    app.error = StubVar("")  # type: ignore[assignment]
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


def test_process_images_rejects_empty_output(tmp_path: Path) -> None:
    """The old empty-output error was a modal titled "Error". It is now an
    inline label, so assert on the label's variable, not on messagebox.
    """
    source = tmp_path / "pano.jpg"
    synthetic_panorama(600, 200).save(source, "JPEG", quality=95)

    app = gui.PanoramaSplitterGUI.__new__(gui.PanoramaSplitterGUI)
    app.input_path = StubVar(str(source))  # type: ignore[assignment]
    app.output_path = StubVar("")  # type: ignore[assignment]
    app.error = StubVar("")  # type: ignore[assignment]

    app.process_images()

    assert app.error.value == "Choose where the frames should go."  # type: ignore[attr-defined]


def test_process_images_reports_a_missing_input_in_the_inline_error_label(
    tmp_path: Path,
) -> None:
    app = gui.PanoramaSplitterGUI.__new__(gui.PanoramaSplitterGUI)
    app.input_path = StubVar(str(tmp_path / "gone.jpg"))  # type: ignore[assignment]
    app.output_path = StubVar(str(tmp_path / "out"))  # type: ignore[assignment]
    app.error = StubVar("stale message from the last run")  # type: ignore[assignment]

    app.process_images()

    expected = "That file is not there any more. Choose another source."
    assert app.error.value == expected  # type: ignore[attr-defined]


def test_process_images_uses_no_error_modal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Input validation must never open a dialog: the message belongs next to
    the control the user has to fix.
    """
    dialogs: list[tuple[str, str]] = []
    monkeypatch.setattr(messagebox, "showerror", lambda title, msg: dialogs.append((title, msg)))

    app = gui.PanoramaSplitterGUI.__new__(gui.PanoramaSplitterGUI)
    app.input_path = StubVar(str(tmp_path / "gone.jpg"))  # type: ignore[assignment]
    app.output_path = StubVar("")  # type: ignore[assignment]
    app.error = StubVar("")  # type: ignore[assignment]

    app.process_images()

    assert dialogs == []


def test_finish_message_counts_every_frame_and_names_the_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The sentence counts all frames written, including the whole-panorama
    frame, so it agrees with the "Cut frames" button. `update_preview` still
    gets the detail count.
    """
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

    assert finished == [("Cut 2 frames at 1.91:1 into out", "out", 1, None)]


def test_finish_shows_no_success_modal(monkeypatch: pytest.MonkeyPatch) -> None:
    """The success modal covered the previews it was announcing. It is gone,
    and this test exists so it cannot come back unnoticed.
    """
    modals: list[tuple[str, str]] = []
    monkeypatch.setattr(messagebox, "showinfo", lambda title, msg: modals.append((title, msg)))

    app = gui.PanoramaSplitterGUI.__new__(gui.PanoramaSplitterGUI)
    app.progress = StubVar()  # type: ignore[assignment]
    app.status = StubVar()  # type: ignore[assignment]
    app.error = StubVar("")  # type: ignore[assignment]
    app.process_btn = StubButton()  # type: ignore[assignment]
    app.update_preview = lambda *a, **k: None  # type: ignore[method-assign]

    app._finish("Cut 2 frames at 4:5 into out", "out", 1, None)

    assert modals == []
    assert app.status.value == "Cut 2 frames at 4:5 into out"  # type: ignore[attr-defined]


def test_finish_reports_a_processing_failure_inline_and_never_in_a_dialog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failure the user did not cause must not be silent -- but it must not
    be a modal either. The status line already carries the sentence, so a
    dialog on top of it is the same message twice with a click attached."""
    dialogs: list[tuple[str, str]] = []
    monkeypatch.setattr(messagebox, "showerror", lambda title, msg: dialogs.append((title, msg)))

    app = gui.PanoramaSplitterGUI.__new__(gui.PanoramaSplitterGUI)
    app.progress = StubVar()  # type: ignore[assignment]
    app.status = StubVar()  # type: ignore[assignment]
    app.error = StubVar("")  # type: ignore[assignment]
    app.process_btn = StubButton()  # type: ignore[assignment]

    app._finish("Could not cut pano.jpg — broken", None, None, "broken")

    assert dialogs == []
    assert app.status.value == "Could not cut pano.jpg — broken"  # type: ignore[attr-defined]
    assert app.error.value == "broken"  # type: ignore[attr-defined]


def test_finish_batch_reports_sources_and_frames(monkeypatch: pytest.MonkeyPatch) -> None:
    modals: list[tuple[str, str]] = []
    monkeypatch.setattr(messagebox, "showinfo", lambda title, msg: modals.append((title, msg)))

    app = gui.PanoramaSplitterGUI.__new__(gui.PanoramaSplitterGUI)
    app.progress = StubVar()  # type: ignore[assignment]
    app.status = StubVar()  # type: ignore[assignment]
    app.error = StubVar("")  # type: ignore[assignment]
    app.process_btn = StubButton()  # type: ignore[assignment]
    app.update_preview = lambda *a, **k: None  # type: ignore[method-assign]

    result = pipeline.BatchResult(
        written=[Path("/tmp/a_1_padded.jpg"), Path("/tmp/a_2_section1.jpg")],
        last_prefix=Path("/tmp/a"),
        last_count=1,
        succeeded_count=1,
    )

    app._finish_batch(result, "1.91:1")

    assert app.status.value == "Cut 1 sources at 1.91:1. 2 frames written."  # type: ignore[attr-defined]
    assert modals == []


def test_finish_batch_names_every_failed_file_and_keeps_the_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The old partial-failure warning modal is gone; the status names the
    files and the inline error label keeps the reasons.
    """
    warnings: list[tuple[str, str]] = []
    monkeypatch.setattr(messagebox, "showwarning", lambda title, msg: warnings.append((title, msg)))

    app = gui.PanoramaSplitterGUI.__new__(gui.PanoramaSplitterGUI)
    app.progress = StubVar()  # type: ignore[assignment]
    app.status = StubVar()  # type: ignore[assignment]
    app.error = StubVar("")  # type: ignore[assignment]
    app.process_btn = StubButton()  # type: ignore[assignment]
    app.update_preview = lambda *a, **k: None  # type: ignore[method-assign]

    result = pipeline.BatchResult(
        written=[Path("/tmp/a_1_padded.jpg")],
        failed=[(Path("/tmp/b.jpg"), "portrait input")],
        last_prefix=Path("/tmp/a"),
        last_count=1,
        succeeded_count=1,
    )

    app._finish_batch(result, "1.91:1")

    assert app.status.value == "Cut 1 of 2 sources. b.jpg could not be read."  # type: ignore[attr-defined]
    assert app.error.value == "b.jpg: portrait input"  # type: ignore[attr-defined]
    assert warnings == []


def test_finish_batch_reports_an_empty_folder_in_the_status_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A JPEG-free folder gives succeeded_count=0, failed=[], total_count=0.
    That used to be an informational modal; the status line carries it now,
    and it must still not read as success.
    """
    modals: list[tuple[str, str]] = []
    monkeypatch.setattr(messagebox, "showinfo", lambda title, msg: modals.append((title, msg)))

    app = gui.PanoramaSplitterGUI.__new__(gui.PanoramaSplitterGUI)
    app.progress = StubVar()  # type: ignore[assignment]
    app.status = StubVar()  # type: ignore[assignment]
    app.error = StubVar("")  # type: ignore[assignment]
    app.process_btn = StubButton()  # type: ignore[assignment]

    result = pipeline.BatchResult()
    assert result.total_count == 0

    app._finish_batch(result, pipeline.DEFAULT_RATIO.name)

    expected = "No JPGs in that folder. Auto Border Pano reads .jpg and .jpeg."
    assert app.status.value == expected  # type: ignore[attr-defined]
    assert modals == []
    assert app.process_btn.last_state == "normal"  # type: ignore[attr-defined]


def test_set_progress_names_the_source(monkeypatch: pytest.MonkeyPatch) -> None:
    app = gui.PanoramaSplitterGUI.__new__(gui.PanoramaSplitterGUI)
    app.progress = StubVar()  # type: ignore[assignment]
    app.status = StubVar()  # type: ignore[assignment]

    app._set_progress(0, 3, "horizons3-hp5-4.jpg")

    assert app.status.value == "Source 1 of 3 · horizons3-hp5-4.jpg"  # type: ignore[attr-defined]


def test_apply_facts_fills_the_readouts_and_the_button_label() -> None:
    app = gui.PanoramaSplitterGUI.__new__(gui.PanoramaSplitterGUI)
    app._inspect_token = 7
    app.facts = StubVar("")  # type: ignore[assignment]
    app.frame_count = StubVar("")  # type: ignore[assignment]
    app.action = StubVar("")  # type: ignore[assignment]

    app._apply_facts(7, pipeline.SourceFacts(19921, 6607, "3.01:1", 4))

    assert app.facts.value == "19921 × 6607 · 3.01:1"  # type: ignore[attr-defined]  # noqa: RUF001
    assert app.frame_count.value == "4 frames"  # type: ignore[attr-defined]
    assert app.action.value == "Cut 4 frames"  # type: ignore[attr-defined]


def test_apply_facts_ignores_a_stale_inspection() -> None:
    """The user can pick a second source before the first header read comes
    back. The older answer must not overwrite the newer one -- that would leave
    the rail describing a file that is no longer loaded.
    """
    app = gui.PanoramaSplitterGUI.__new__(gui.PanoramaSplitterGUI)
    app._inspect_token = 2
    app.facts = StubVar("")  # type: ignore[assignment]
    app.frame_count = StubVar("")  # type: ignore[assignment]
    app.action = StubVar("")  # type: ignore[assignment]

    # The newer request (token 2) lands first.
    app._apply_facts(2, pipeline.SourceFacts(4000, 1000, "4.00:1", 5))
    # The older one (token 1) arrives late and must be dropped entirely.
    app._apply_facts(1, pipeline.SourceFacts(100, 100, "1.00:1", 2))

    assert app.facts.value == "4000 × 1000 · 4.00:1"  # type: ignore[attr-defined]  # noqa: RUF001
    assert app.frame_count.value == "5 frames"  # type: ignore[attr-defined]
    assert app.action.value == "Cut 5 frames"  # type: ignore[attr-defined]


def test_apply_facts_resets_the_readouts_when_the_file_cannot_be_read() -> None:
    app = gui.PanoramaSplitterGUI.__new__(gui.PanoramaSplitterGUI)
    app._inspect_token = 1
    app.facts = StubVar("19921 × 6607 · 3.01:1")  # type: ignore[assignment]  # noqa: RUF001
    app.frame_count = StubVar("4 frames")  # type: ignore[assignment]
    app.action = StubVar("Cut 4 frames")  # type: ignore[assignment]

    app._apply_facts(1, None)

    assert app.facts.value == ""  # type: ignore[attr-defined]
    assert app.frame_count.value == split_tab.NO_COUNT  # type: ignore[attr-defined]
    assert app.action.value == split_tab.UNCOUNTED_ACTION  # type: ignore[attr-defined]


def test_inspect_never_touches_a_tk_object_and_returns_through_after(tmp_path: Path) -> None:
    """The worker reads the header; every var it feeds is set on the main
    thread, via root.after, by _apply_facts.
    """
    source = tmp_path / "pano.jpg"
    synthetic_panorama(600, 200).save(source, "JPEG", quality=95)

    app = gui.PanoramaSplitterGUI.__new__(gui.PanoramaSplitterGUI)
    stub_root = StubRoot()
    app.root = stub_root  # type: ignore[assignment]
    app._inspect_token = 3
    app.facts = StubVar("")  # type: ignore[assignment]
    app.frame_count = StubVar("")  # type: ignore[assignment]
    app.action = StubVar("")  # type: ignore[assignment]

    app._inspect(3, str(source), pipeline.DEFAULT_RATIO.name)

    assert stub_root.calls, "root.after was never scheduled -- worker died silently"
    assert app.facts.value == "600 × 200 · 3.00:1"  # type: ignore[attr-defined]  # noqa: RUF001


def test_inspect_reports_an_unreadable_source_as_no_count(tmp_path: Path) -> None:
    app = gui.PanoramaSplitterGUI.__new__(gui.PanoramaSplitterGUI)
    stub_root = StubRoot()
    app.root = stub_root  # type: ignore[assignment]
    app._inspect_token = 1
    app.facts = StubVar("stale")  # type: ignore[assignment]
    app.frame_count = StubVar("9 frames")  # type: ignore[assignment]
    app.action = StubVar("Cut 9 frames")  # type: ignore[assignment]

    app._inspect(1, str(tmp_path / "gone.jpg"), pipeline.DEFAULT_RATIO.name)

    assert app.frame_count.value == split_tab.NO_COUNT  # type: ignore[attr-defined]
    assert app.action.value == split_tab.UNCOUNTED_ACTION  # type: ignore[attr-defined]


@pytest.mark.parametrize("ratio_name", list(pipeline.RATIOS))
def test_frame_count_readout_matches_what_the_pipeline_actually_writes(
    tmp_path: Path, ratio_name: str
) -> None:
    """The count in the rail is a promise about files on disk. Check it against
    the real thing, for every ratio, rather than against a stub.
    """
    source = tmp_path / "pano.jpg"
    synthetic_panorama(600, 200).save(source, "JPEG", quality=95)
    ratio = pipeline.RATIOS[ratio_name]
    written = pipeline.process_image(source, tmp_path / f"out-{ratio_name}", ratio)

    app = gui.PanoramaSplitterGUI.__new__(gui.PanoramaSplitterGUI)
    stub_root = StubRoot()
    app.root = stub_root  # type: ignore[assignment]
    app._inspect_token = 1
    app.facts = StubVar("")  # type: ignore[assignment]
    app.frame_count = StubVar("")  # type: ignore[assignment]
    app.action = StubVar("")  # type: ignore[assignment]

    app._inspect(1, str(source), ratio_name)

    assert app.frame_count.value == f"{len(written)} frames"  # type: ignore[attr-defined]
    assert app.action.value == f"Cut {len(written)} frames"  # type: ignore[attr-defined]


def test_the_readouts_reset_with_no_file_and_in_folder_mode(
    tk_root: tkinter.Tk, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No file, or a folder, means no frame count -- never a stale or guessed
    one. Built under real Tk because the traces on the path and the mode are
    what drive this.

    The inspection thread runs inline here: `root.after` is only legal from a
    worker while `mainloop` is running, and there is no mainloop in a test.
    """
    from tkinter import ttk

    class _InlineThread:
        def __init__(self, target: Any, args: tuple[Any, ...], daemon: bool) -> None:
            self._target = target
            self._args = args

        def start(self) -> None:
            self._target(*self._args)

    monkeypatch.setattr(threading, "Thread", _InlineThread)

    source = tmp_path / "pano.jpg"
    synthetic_panorama(600, 200).save(source, "JPEG", quality=95)

    app = gui.PanoramaSplitterGUI(ttk.Frame(tk_root))

    assert app.frame_count.get() == split_tab.NO_COUNT
    assert app.facts.get() == ""

    app.input_path.set(str(source))
    tk_root.update()
    assert app.frame_count.get() == "5 frames"
    assert app.facts.get() == "600 × 200 · 3.00:1"  # noqa: RUF001

    app.is_folder_mode.set(True)
    tk_root.update()
    assert app.frame_count.get() == split_tab.NO_COUNT
    assert app.facts.get() == ""

    app.is_folder_mode.set(False)
    tk_root.update()
    assert app.frame_count.get() == "5 frames"

    app.input_path.set("")
    tk_root.update()
    assert app.frame_count.get() == split_tab.NO_COUNT
    assert app.facts.get() == ""


def test_the_mode_radios_actually_switch_mode(tk_root: tkinter.Tk) -> None:
    """The old `Mode:` label reported a control that did not exist. These are
    real radios: invoking one must flip the variable, not just describe it.
    """
    from tkinter import ttk

    app = gui.PanoramaSplitterGUI(ttk.Frame(tk_root))
    assert not hasattr(app, "mode_label")

    radios = [widget for widget in _descendants(app.root) if isinstance(widget, ttk.Radiobutton)]
    assert [radio.cget("text") for radio in radios] == ["One frame", "Whole folder"]

    radios[1].invoke()
    assert app.is_folder_mode.get() is True
    radios[0].invoke()
    assert app.is_folder_mode.get() is False


def _descendants(widget: Any) -> list[Any]:
    found = []
    for child in widget.winfo_children():
        found.append(child)
        found.extend(_descendants(child))
    return found


def test_split_tab_builds_under_a_notebook_page_with_working_previews(
    tk_root: tkinter.Tk, tmp_path: Path
) -> None:
    """Every splitter test above builds `PanoramaSplitterGUI` via `__new__`,
    which never runs `_build_ui` -- so a broken constructor, such as one
    that assumes `self.root` is the Tk root rather than a notebook page,
    would stay green forever. Build a real instance under a `ttk.Frame`
    (as `gui.app.run` does, nesting it inside a notebook) on a withdrawn
    root, and exercise `update_preview` against real preview panes.
    """
    from tkinter import ttk

    from auto_border_pano import gui, pipeline

    source = tmp_path / "pano.jpg"
    synthetic_panorama(600, 200).save(source, "JPEG", quality=95)
    written = pipeline.process_image(source, tmp_path / "out", pipeline.DEFAULT_RATIO)
    count = len(written) - 1

    page = ttk.Frame(tk_root)
    app = gui.PanoramaSplitterGUI(page)

    assert app.ratio.get() == pipeline.DEFAULT_RATIO.display
    # The strip shows an unexposed frame from construction. It never shows
    # an empty box: that absence was the loudest complaint in the audit.
    assert app.previews.frame_count > 0
    assert app.previews.errors == []

    app.update_preview(str(tmp_path / "out"), count)

    assert app.previews.frame_count == count + 1
    assert app.previews.errors == [], "every written frame should have decoded"


def test_a_single_run_reports_every_frame_as_it_lands(
    tk_root: tkinter.Tk, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Progress *is* the preview.

    `_run_single` used to report nothing at all, so on the most common
    workflow the bar went 0 to 100 with no intermediate state. It now hands
    every frame to the strip as the frame lands on disk. This is the wiring
    between `pipeline.process_image`'s callback and `ContactStrip`, so it
    exercises both ends rather than a stub of either.
    """
    from tkinter import ttk

    source = tmp_path / "pano.jpg"
    synthetic_panorama(600, 200).save(source, "JPEG", quality=95)

    page = ttk.Frame(tk_root)
    app = gui.PanoramaSplitterGUI(page)

    # `root.after` needs a running mainloop, which pytest has not got; run
    # the callback inline instead, exactly as StubRoot does elsewhere here.
    monkeypatch.setattr(
        app.root, "after", lambda _delay, callback, *args: callback(*args), raising=False
    )

    seen: list[str] = []
    original = app._set_frame_progress

    def spy(done: int, total: int, path: Path) -> None:
        seen.append(f"{done + 1}/{total}")
        original(done, total, path)

    app._set_frame_progress = spy  # type: ignore[method-assign]

    app._run_single(str(source), str(tmp_path / "out"), pipeline.DEFAULT_RATIO.name)

    expected_frames = pipeline.inspect_source(source, pipeline.DEFAULT_RATIO).frame_count
    assert seen == [f"{n}/{expected_frames}" for n in range(1, expected_frames + 1)]
    assert app.previews.frame_count == expected_frames
    assert app.previews.errors == []
