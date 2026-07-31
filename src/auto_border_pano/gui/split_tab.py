"""tkinter front end.

Importing this module raises ImportError when tkinter is missing; the
friendly message lives in cli.gui_main.
"""

import contextlib
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

from auto_border_pano import pipeline
from auto_border_pano.gui import shell, theme
from auto_border_pano.gui.strip import ContactStrip

# Built once so process_images can do a plain dict lookup rather than
# scanning pipeline.RATIOS on every run.
_RATIO_BY_DISPLAY: dict[str, str] = {r.display: r.name for r in pipeline.RATIOS.values()}

NO_COUNT = "Load a source to see the frame count"
"""Shown whenever the frame count is not known: no file, folder mode, or an
unreadable file. Never a stale or guessed number."""

UNCOUNTED_ACTION = "Cut frames"
"""The button's label while the count is unknown. Once it is known the
button counts what it will produce."""


def preview_titles(count: int) -> list[str]:
    """Labels for the preview panes: the whole panorama plus each detail frame.

    Frame numbers run 1..count+1 across the whole strip; only the first
    frame holds the whole panorama. The caps are in the string because ttk
    has no text-transform.
    """
    return ["FRAME 1 · WHOLE PANORAMA"] + [f"FRAME {n + 1} · DETAIL" for n in range(1, count + 1)]


class PanoramaSplitterGUI:
    def __init__(self, root: tk.Misc) -> None:
        self.root = root

        self.input_path = tk.StringVar()
        self.output_path = tk.StringVar()
        self.is_folder_mode = tk.BooleanVar(value=False)
        self.progress = tk.DoubleVar()
        self.status = tk.StringVar(value="Ready")
        # Inline replacement for the old error modals: a chinagraph label
        # under the primary button, cleared at the start of every run.
        self.error = tk.StringVar()
        self.ratio = tk.StringVar(value=pipeline.DEFAULT_RATIO.display)
        # What the app read off the source's header: dimensions and native
        # ratio in mono, the frame count the chosen ratio implies, and the
        # button's own label, which counts what it will produce.
        self.facts = tk.StringVar()
        self.frame_count = tk.StringVar(value=NO_COUNT)
        self.action = tk.StringVar(value=UNCOUNTED_ACTION)
        # What the rebate band should stencil while this tab is in front:
        # what is loaded, and what this tab will make of it. The band belongs
        # to the shell, not to either tab, so each tab just states these and
        # the shell decides whose to show.
        self.subject = tk.StringVar()
        self.detail = tk.StringVar()
        # Monotonic; only the newest inspection may write to the vars above.
        # The user can pick a second file before the first header read comes
        # back, and the older answer must not overwrite the newer one.
        self._inspect_token = 0

        self._build_ui()
        self.input_path.trace_add("write", self._on_selection_changed)
        self.is_folder_mode.trace_add("write", self._on_selection_changed)

    def _build_ui(self) -> None:
        columns = shell.TwoColumn(self.root)
        columns.frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        rail = columns.rail

        # The rail reads top to bottom as a sentence: this file, at this
        # ratio, to here, go.
        shell.section(rail, "Source", row=0)

        input_row = ttk.Frame(rail)
        input_row.grid(row=1, column=0, sticky=(tk.W, tk.E))
        input_row.columnconfigure(0, weight=1)
        self.input_entry = shell.path_entry(input_row, self.input_path)
        ttk.Button(input_row, text="Choose…", command=self.browse_input).grid(
            row=0, column=1, padx=(theme.SPACE_S, 0)
        )

        ttk.Label(rail, textvariable=self.facts, style="Data.TLabel").grid(
            row=2, column=0, sticky=tk.W, pady=(theme.SPACE_S, 0)
        )

        modes = ttk.Frame(rail)
        modes.grid(row=3, column=0, sticky=tk.W, pady=(theme.SPACE_S, 0))
        # A real control, not the old read-only "Mode:" label -- that label
        # reported the state of a control that did not exist, and a user
        # could not get back to single-file mode without re-browsing.
        ttk.Radiobutton(modes, text="One frame", value=False, variable=self.is_folder_mode).pack(
            side="left"
        )
        ttk.Radiobutton(modes, text="Whole folder", value=True, variable=self.is_folder_mode).pack(
            side="left", padx=(theme.SPACE_M, 0)
        )

        shell.section(rail, "Format", row=4)

        self.ratio_box = ttk.Combobox(
            rail,
            textvariable=self.ratio,
            values=[r.display for r in pipeline.RATIOS.values()],
            state="readonly",
        )
        self.ratio_box.grid(row=5, column=0, sticky=(tk.W, tk.E))
        self.ratio_box.bind("<<ComboboxSelected>>", self._on_selection_changed)

        ttk.Label(rail, textvariable=self.frame_count, style="Help.TLabel").grid(
            row=6, column=0, sticky=tk.W, pady=(theme.SPACE_S, 0)
        )

        shell.section(rail, "Destination", row=7)

        output_row = ttk.Frame(rail)
        output_row.grid(row=8, column=0, sticky=(tk.W, tk.E))
        output_row.columnconfigure(0, weight=1)
        self.output_entry = shell.path_entry(output_row, self.output_path)
        ttk.Button(output_row, text="Choose folder", command=self.browse_output).grid(
            row=0, column=1, padx=(theme.SPACE_S, 0)
        )

        self.process_btn = ttk.Button(
            rail, textvariable=self.action, command=self.process_images, style="Primary.TButton"
        )
        self.process_btn.grid(row=9, column=0, sticky=(tk.W, tk.E), pady=(theme.SPACE_L, 0))

        ttk.Label(rail, textvariable=self.status, style="Help.TLabel").grid(
            row=10, column=0, sticky=tk.W, pady=(theme.SPACE_M, 0)
        )
        # The strip is the real progress indicator now -- frames appear as
        # they are written -- so the bar only earns its space while a run is
        # in flight. At rest it was a dead grey slab under the status line
        # saying nothing, which is what the removed Progress frame used to do.
        self.progress_bar = ttk.Progressbar(rail, variable=self.progress, maximum=100)
        self.progress_bar.grid(row=11, column=0, sticky=(tk.W, tk.E), pady=(theme.SPACE_S, 0))
        self.progress_bar.grid_remove()
        self.error_label = ttk.Label(rail, textvariable=self.error, style="Error.TLabel")
        self.error_label.grid(row=12, column=0, sticky=tk.W, pady=(theme.SPACE_S, 0))
        # Everything above is fixed height; the slack goes below the rail so
        # the controls stay together at the top.
        rail.rowconfigure(13, weight=1)

        # The strip renders its unexposed empty state from construction, so
        # the largest thing on screen says something before the first run.
        self.previews = ContactStrip(columns.table)
        # Top of the table, at its natural height: the strip is an object
        # lying on the light table, not a panel filling it.
        self.previews.canvas.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N))

    def _report(self, callback: object, *args: object) -> None:
        """Cross back to the main thread from a worker. The only crossing.

        Guarded because the window can close while a worker is still in
        flight: `after` then raises TclError, or RuntimeError when the
        interpreter has no main loop left to schedule onto, and an unguarded
        call kills the worker thread with an unhandled exception. There is
        nothing left to tell by then, so dropping the report is correct.
        """
        with contextlib.suppress(tk.TclError, RuntimeError):
            self.root.after(0, callback, *args)  # type: ignore[arg-type]

    # --- The live readouts --------------------------------------------------

    def _on_selection_changed(self, *_args: object) -> None:
        """Re-read the source's header. Main thread only.

        Bumping the token first means any inspection already in flight is
        stale from here on, whichever way this call ends.
        """
        self._inspect_token += 1
        token = self._inspect_token
        source = self.input_path.get()
        # The band names whatever is loaded, folder or file -- it is the one
        # thing on screen that says what you are working on.
        self.subject.set(Path(source).name if source else "")
        if not source or self.is_folder_mode.get():
            self._clear_facts()
            return
        # Read both vars here, on the main thread, and hand the worker plain
        # strings -- it must never touch a tk object, including a tk var.
        ratio_name = _RATIO_BY_DISPLAY.get(self.ratio.get(), pipeline.DEFAULT_RATIO.name)
        threading.Thread(
            target=self._inspect, args=(token, source, ratio_name), daemon=True
        ).start()

    def _inspect(self, token: int, source: str, ratio_name: str) -> None:
        """Runs on a worker thread. Touches nothing but plain values."""
        try:
            facts: pipeline.SourceFacts | None = pipeline.inspect_source(
                source, pipeline.RATIOS[ratio_name]
            )
        except Exception:
            # An unreadable file is not an error the user has to act on yet;
            # process_images reports it properly if they press the button.
            facts = None
        self._report(self._apply_facts, token, facts, ratio_name)

    def _apply_facts(
        self, token: int, facts: pipeline.SourceFacts | None, ratio_name: str = ""
    ) -> None:
        """Runs on the main thread. All widget mutation happens here.

        The ratio arrives with the answer rather than being re-read here:
        these facts were computed for THAT ratio, and the combobox may have
        moved on since. Reading it again would caption one ratio's frame
        count with another ratio's name.
        """
        if token != self._inspect_token:
            return
        if facts is None:
            self._clear_facts()
            return
        self.facts.set(f"{facts.width} × {facts.height} · {facts.native_ratio}")  # noqa: RUF001
        self.frame_count.set(f"{facts.frame_count} frames")
        self.action.set(f"Cut {facts.frame_count} frames")
        self.detail.set(f"{ratio_name} · {facts.frame_count} frames" if ratio_name else "")

    def _clear_facts(self) -> None:
        self.facts.set("")
        self.frame_count.set(NO_COUNT)
        self.action.set(UNCOUNTED_ACTION)
        self.detail.set("")

    def browse_input(self) -> None:
        """One button, because the radio pair already says what is wanted."""
        if self.is_folder_mode.get():
            self.browse_folder()
            return
        self.browse_file()

    def browse_file(self) -> None:
        filename = filedialog.askopenfilename(
            title="Select Panorama Image",
            filetypes=[("Image files", "*.jpg *.jpeg *.JPG *.JPEG"), ("All files", "*.*")],
        )
        if not filename:
            return
        self.input_path.set(filename)
        self.is_folder_mode.set(False)
        self.output_path.set(str(Path(filename).with_suffix("")) + "_output")

    def browse_folder(self) -> None:
        folder = filedialog.askdirectory(title="Select Input Folder")
        if not folder:
            return
        chosen = Path(folder)
        self.input_path.set(folder)
        self.is_folder_mode.set(True)
        self.output_path.set(str(chosen.parent / f"{chosen.name}_output"))

    def browse_output(self) -> None:
        folder = filedialog.askdirectory(title="Select Output Folder")
        if not folder:
            return
        if self.is_folder_mode.get():
            self.output_path.set(folder)
            return
        source = self.input_path.get()
        self.output_path.set(str(Path(folder) / Path(source).stem) if source else folder)

    def update_preview(self, output_prefix: str, count: int) -> None:
        self.previews.set_frames(preview_titles(count))
        self.previews.show_paths(pipeline.output_paths(output_prefix, count))

    def _finish(
        self, message: str, prefix: str | None, count: int | None, error: str | None
    ) -> None:
        """Runs on the main thread. All widget mutation happens here."""
        self.progress.set(100)
        self.progress_bar.grid_remove()
        self.status.set(message)
        try:
            if prefix is not None and count is not None:
                self.update_preview(prefix, count)
        finally:
            self.process_btn.config(state="normal")
        # Success is reported by the status line and the previews filling
        # in; a modal would only cover the previews the user came to see.
        # Failures are reported the same way, inline and in chinagraph --
        # the status line already carries the sentence, so a dialog on top
        # of it would be the same message twice with a click attached.
        if error is not None:
            self.error.set(error)

    def _finish_batch(self, result: pipeline.BatchResult, ratio_name: str) -> None:
        """Runs on the main thread. All widget mutation happens here."""
        self.progress.set(100)
        self.progress_bar.grid_remove()
        succeeded = result.succeeded_count
        total = result.total_count
        failed = result.failed
        ratio = pipeline.RATIOS[ratio_name].name

        if total == 0:
            self.status.set("No JPGs in that folder. Auto Border Pano reads .jpg and .jpeg.")
            self.process_btn.config(state="normal")
            return

        if failed:
            names = ", ".join(path.name for path, _ in failed)
            message = f"Cut {succeeded} of {total} sources. {names} could not be read."
            # The status names the files; the reasons go to the error label
            # so nothing the user needs to act on is lost.
            self.error.set("; ".join(f"{path.name}: {reason}" for path, reason in failed))
        else:
            message = f"Cut {total} sources at {ratio}. {len(result.written)} frames written."
        self.status.set(message)
        try:
            if result.last_prefix is not None and result.last_count is not None:
                self.update_preview(str(result.last_prefix), result.last_count)
        finally:
            self.process_btn.config(state="normal")

    def _run_single(self, source: str, prefix: str, ratio_name: str) -> None:
        def report(done: int, total: int, path: Path) -> None:
            # Worker thread. Hands plain data back and touches nothing tk.
            self._report(self._set_frame_progress, done, total, path)

        try:
            written = pipeline.process_image(
                source, prefix, pipeline.RATIOS[ratio_name], on_frame=report
            )
        except Exception as error:
            message = f"Could not cut {Path(source).name} — {error}"
            self._report(self._finish, message, None, None, str(error))
            return
        # `count` is the detail-frame count update_preview expects; the
        # sentence counts every frame written, so the button's verb and the
        # number in the result agree.
        count = len(written) - 1
        ratio = pipeline.RATIOS[ratio_name].name
        message = f"Cut {len(written)} frames at {ratio} into {Path(prefix).name}"
        self._report(self._finish, message, prefix, count, None)

    def _run_batch(self, source: str, destination: str, ratio_name: str) -> None:
        def report(done: int, total: int, path: Path) -> None:
            self._report(self._set_progress, done, total, path.name)

        try:
            result = pipeline.process_folder(
                source, destination, pipeline.RATIOS[ratio_name], on_progress=report
            )
        except Exception as error:
            message = f"Could not cut {Path(source).name} — {error}"
            self._report(self._finish, message, None, None, str(error))
            return
        self._report(self._finish_batch, result, ratio_name)

    def _set_frame_progress(self, done: int, total: int, path: Path) -> None:
        """Runs on the main thread. Progress *is* the preview.

        Each frame appears on the strip as it lands on disk, so the bar is
        no longer the only thing moving during a run -- and on a single file
        it used to be the only thing that did not move, going 0 to 100 with
        nothing in between.
        """
        if self.previews.frame_count != total:
            self.previews.set_frames(preview_titles(total - 1))
        self.previews.mark_written(done, path)
        self.progress.set((done + 1) / total * 100 if total else 0)
        self.status.set(f"Cutting frame {done + 1} of {total}")

    def _set_progress(self, done: int, total: int, name: str) -> None:
        self.progress.set((done + 1) / total * 100 if total else 0)
        self.status.set(f"Source {done + 1} of {total} · {name}")

    def process_images(self) -> None:
        self.error.set("")
        source = self.input_path.get()
        if not source or not Path(source).exists():
            self.error.set("That file is not there any more. Choose another source.")
            return
        destination = self.output_path.get()
        if not destination:
            self.error.set("Choose where the frames should go.")
            return
        self.process_btn.config(state="disabled")
        self.progress.set(0)
        self.progress_bar.grid()
        self.status.set("Cutting frames")
        # Map the displayed label back to the bare ratio name here, on the
        # main thread -- the worker thread must never touch a tkinter
        # object, only the plain string handed to it below. The lookup is
        # total: an unrecognised value (only reachable by future code
        # setting self.ratio programmatically, since the combobox is
        # readonly and populated from the same mapping) falls back to the
        # documented default instead of raising.
        selected_display = self.ratio.get()
        ratio_name = _RATIO_BY_DISPLAY.get(selected_display, pipeline.DEFAULT_RATIO.name)
        target = self._run_batch if self.is_folder_mode.get() else self._run_single
        threading.Thread(target=target, args=(source, destination, ratio_name), daemon=True).start()
