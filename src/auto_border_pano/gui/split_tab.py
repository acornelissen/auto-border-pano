"""The Split tab: one panorama, or a folder of them, cut into frames.

A port of the tkinter tab, not a redesign. Every behaviour here was argued
for once already: no modal dialogs, a real radio pair for the mode, live
readouts that never show a stale count, and a progress bar that only exists
while a run is in flight.

Two things did change, both because Qt lets them.

The crossing back to the GUI thread is gone. Under tkinter every worker
hand-rolled a guarded `root.after`; here a job returns plain data and
`work.submit` delivers it on the GUI thread, and per-frame progress is a
signal the worker emits, which Qt queues to this widget's thread by itself.

What did not change is staleness. A user can pick a second file before the
first header read comes back, so the inspection still carries a monotonic
token, and the ratio still travels with its own answer rather than being
re-read from a combobox that may have moved on.
"""

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from auto_border_pano import pipeline
from auto_border_pano.gui import shell, theme
from auto_border_pano.gui.strip import ContactStrip
from auto_border_pano.gui.work import submit

# Built once so a run can do a plain dict lookup rather than scanning
# pipeline.RATIOS every time.
_RATIO_BY_DISPLAY: dict[str, str] = {r.display: r.name for r in pipeline.RATIOS.values()}

NO_COUNT = "Load a source to see the frame count"
"""Shown whenever the frame count is not known: no file, folder mode, or an
unreadable file. Never a stale or guessed number."""

UNCOUNTED_ACTION = "Cut frames"
"""The button's label while the count is unknown. Once it is known the
button counts what it will produce."""


def preview_titles(count: int) -> list[str]:
    """Labels for the strip: the whole panorama, then each detail frame."""
    return ["FRAME 1 · WHOLE PANORAMA"] + [f"FRAME {n + 1} · DETAIL" for n in range(1, count + 1)]


class SplitTab(QWidget):
    """The rail reads top to bottom as a sentence: this file, at this ratio,
    to here, go. The strip lies on the light table beside it.
    """

    band_changed = Signal(str, str)
    """(subject, detail) for the rebate band. The band belongs to the shell,
    not to a tab, so the tab only ever states what it would say."""

    # Emitted from the worker thread while a run is in flight. Qt queues
    # these to this widget's thread, so the slots may touch widgets freely.
    frame_written = Signal(int, int, object)
    source_started = Signal(int, int, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._subject = ""
        self._detail = ""
        # Monotonic; only the newest inspection may write to the readouts.
        self._inspect_token = 0

        self._build()

        self.source_row.field.textChanged.connect(self._on_selection_changed)
        self.folder_radio.toggled.connect(self._on_selection_changed)
        self.ratio_box.currentIndexChanged.connect(self._on_selection_changed)
        self.frame_written.connect(self._set_frame_progress)
        self.source_started.connect(self._set_progress)

    # --- Construction -------------------------------------------------------

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.columns = shell.TwoColumn(self)
        outer.addWidget(self.columns)

        rail = self.columns.rail_layout

        rail.addWidget(shell.section("Source"))
        rail.addSpacing(theme.S)
        self.source_row = shell.PathRow("Choose…")
        self.source_row.button.clicked.connect(self.browse_input)
        rail.addWidget(self.source_row)

        rail.addSpacing(theme.S)
        self.facts_label = shell.data_label()
        rail.addWidget(self.facts_label)

        rail.addSpacing(theme.S)
        modes = QWidget()
        mode_row = QHBoxLayout(modes)
        mode_row.setContentsMargins(0, 0, 0, 0)
        mode_row.setSpacing(theme.M)
        # A real control, not a label reporting which browse button was last
        # pressed -- that left no way back to single-file mode.
        self.single_radio = QRadioButton("One frame")
        self.single_radio.setChecked(True)
        self.folder_radio = QRadioButton("Whole folder")
        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.single_radio)
        self.mode_group.addButton(self.folder_radio)
        mode_row.addWidget(self.single_radio)
        mode_row.addWidget(self.folder_radio)
        mode_row.addStretch(1)
        rail.addWidget(modes)

        rail.addSpacing(theme.L)
        rail.addWidget(shell.section("Format"))
        rail.addSpacing(theme.S)
        self.ratio_box = shell.Combo()
        self.ratio_box.addItems([r.display for r in pipeline.RATIOS.values()])
        self.ratio_box.setCurrentText(pipeline.DEFAULT_RATIO.display)
        rail.addWidget(self.ratio_box)

        rail.addSpacing(theme.S)
        self.count_label = shell.help_label(NO_COUNT)
        rail.addWidget(self.count_label)

        rail.addSpacing(theme.L)
        rail.addWidget(shell.section("Destination"))
        rail.addSpacing(theme.S)
        self.dest_row = shell.PathRow("Choose folder")
        self.dest_row.button.clicked.connect(self.browse_output)
        rail.addWidget(self.dest_row)

        rail.addSpacing(theme.L)
        self.action_btn = QPushButton(UNCOUNTED_ACTION)
        self.action_btn.setObjectName("Primary")
        self.action_btn.clicked.connect(self.process_images)
        rail.addWidget(self.action_btn)

        rail.addSpacing(theme.M)
        self.status_label = shell.help_label("Ready")
        rail.addWidget(self.status_label)

        rail.addSpacing(theme.S)
        # The strip is the real progress indicator -- frames appear as they
        # are written -- so the bar only earns its space during a run. At
        # rest it was a dead grey slab saying nothing.
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setVisible(False)
        rail.addWidget(self.progress_bar)

        rail.addSpacing(theme.S)
        # The inline replacement for the old error modals.
        self.error_label = QLabel("")
        self.error_label.setObjectName("Error")
        self.error_label.setWordWrap(True)
        rail.addWidget(self.error_label)

        rail.addStretch(1)

        # An object lying on the light table, not a panel filling it.
        self.strip = ContactStrip(self.columns.table)
        self.columns.table_layout.addWidget(self.strip, 0, Qt.AlignmentFlag.AlignTop)
        self.columns.table_layout.addStretch(1)

    # --- What the band should say ------------------------------------------

    @property
    def subject(self) -> str:
        return self._subject

    @property
    def detail(self) -> str:
        return self._detail

    def _set_band(self, subject: str, detail: str) -> None:
        if subject == self._subject and detail == self._detail:
            return
        self._subject = subject
        self._detail = detail
        self.band_changed.emit(subject, detail)

    # --- The live readouts --------------------------------------------------

    def _ratio_name(self) -> str:
        """The bare ratio name behind the combobox's label.

        Total by construction: an unrecognised value (only reachable by
        future code setting the combobox programmatically) falls back to the
        documented default rather than raising.
        """
        return _RATIO_BY_DISPLAY.get(self.ratio_box.currentText(), pipeline.DEFAULT_RATIO.name)

    def _on_selection_changed(self, *_args: object) -> None:
        """Re-read the source's header. GUI thread only.

        Bumping the token first means any inspection already in flight is
        stale from here on, whichever way this call ends.
        """
        self._inspect_token += 1
        token = self._inspect_token
        source = self.source_row.text()
        # The band names whatever is loaded, folder or file -- it is the one
        # thing on screen that says what you are working on.
        subject = Path(source).name if source else ""
        if not source or self.folder_radio.isChecked():
            self._clear_facts(subject)
            return
        ratio_name = self._ratio_name()

        def read() -> pipeline.SourceFacts | None:
            # Worker thread. Touches no widget, only the plain strings above.
            try:
                return pipeline.inspect_source(source, pipeline.RATIOS[ratio_name])
            except Exception:
                # An unreadable file is not something the user has to act on
                # yet; a run reports it properly if they press the button.
                return None

        submit(
            read,
            lambda facts: self._apply_facts(token, facts, ratio_name, subject),
            lambda _error: self._apply_facts(token, None, ratio_name, subject),
        )

    def _apply_facts(
        self,
        token: int,
        facts: pipeline.SourceFacts | None,
        ratio_name: str = "",
        subject: str = "",
    ) -> None:
        """Runs on the GUI thread. All widget mutation happens here.

        The ratio arrives with the answer rather than being re-read: these
        facts were computed for THAT ratio, and the combobox may have moved
        on. Reading it again would caption one ratio's frame count with
        another ratio's name.
        """
        if token != self._inspect_token:
            return
        if facts is None:
            self._clear_facts(subject)
            return
        self.facts_label.setText(f"{facts.width} × {facts.height} · {facts.native_ratio}")  # noqa: RUF001
        self.count_label.setText(f"{facts.frame_count} frames")
        self.action_btn.setText(f"Cut {facts.frame_count} frames")
        self._set_band(subject, f"{ratio_name} · {facts.frame_count} frames" if ratio_name else "")

    def _clear_facts(self, subject: str = "") -> None:
        self.facts_label.setText("")
        self.count_label.setText(NO_COUNT)
        self.action_btn.setText(UNCOUNTED_ACTION)
        self._set_band(subject, "")

    def _set_error(self, message: str) -> None:
        self.error_label.setText(message)

    # --- Choosing -----------------------------------------------------------

    def browse_input(self) -> None:
        """One button, because the radio pair already says what is wanted."""
        if self.folder_radio.isChecked():
            self.browse_folder()
            return
        self.browse_file()

    def browse_file(self) -> None:
        filename, _filter = QFileDialog.getOpenFileName(
            self, "Select panorama image", "", "Images (*.jpg *.jpeg *.JPG *.JPEG);;All files (*)"
        )
        if not filename:
            return
        self.single_radio.setChecked(True)
        self.source_row.setText(filename)
        self.dest_row.setText(str(Path(filename).with_suffix("")) + "_output")

    def browse_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select input folder")
        if not folder:
            return
        chosen = Path(folder)
        self.folder_radio.setChecked(True)
        self.source_row.setText(folder)
        self.dest_row.setText(str(chosen.parent / f"{chosen.name}_output"))

    def browse_output(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select output folder")
        if not folder:
            return
        if self.folder_radio.isChecked():
            self.dest_row.setText(folder)
            return
        source = self.source_row.text()
        self.dest_row.setText(str(Path(folder) / Path(source).stem) if source else folder)

    # --- Running ------------------------------------------------------------

    def update_preview(self, output_prefix: str, count: int) -> None:
        self.strip.set_frames(preview_titles(count))
        self.strip.show_paths(pipeline.output_paths(output_prefix, count))

    def _set_frame_progress(self, done: int, total: int, path: object) -> None:
        """Runs on the GUI thread. Progress *is* the strip.

        Each frame appears as it lands on disk, so a single-file run is no
        longer a bar going 0 to 100 with nothing in between.
        """
        if self.strip.frame_count != total:
            self.strip.set_frames(preview_titles(total - 1))
        self.strip.mark_written(done, Path(str(path)))
        self.progress_bar.setValue(int((done + 1) / total * 100) if total else 0)
        self.status_label.setText(f"Cutting frame {done + 1} of {total}")

    def _set_progress(self, done: int, total: int, name: str) -> None:
        self.progress_bar.setValue(int((done + 1) / total * 100) if total else 0)
        self.status_label.setText(f"Source {done + 1} of {total} · {name}")

    def _finish(
        self, message: str, prefix: str | None, count: int | None, error: str | None
    ) -> None:
        """Runs on the GUI thread. All widget mutation happens here."""
        self.progress_bar.setValue(100)
        self.progress_bar.setVisible(False)
        self.status_label.setText(message)
        try:
            if prefix is not None and count is not None:
                self.update_preview(prefix, count)
        finally:
            self.action_btn.setEnabled(True)
        # Success is the status line and the strip filling in; a modal would
        # only cover the frames the user came to see. Failure is reported the
        # same way, inline and in chinagraph -- the status line already
        # carries the sentence, so a dialog would be it twice with a click.
        if error is not None:
            self._set_error(error)

    def _finish_batch(self, result: pipeline.BatchResult, ratio_name: str) -> None:
        """Runs on the GUI thread. All widget mutation happens here."""
        self.progress_bar.setValue(100)
        self.progress_bar.setVisible(False)
        succeeded = result.succeeded_count
        total = result.total_count
        failed = result.failed
        ratio = pipeline.RATIOS[ratio_name].name

        if total == 0:
            self.status_label.setText(
                "No JPGs in that folder. Auto Border Pano reads .jpg and .jpeg."
            )
            self.action_btn.setEnabled(True)
            return

        if failed:
            names = ", ".join(path.name for path, _ in failed)
            message = f"Cut {succeeded} of {total} sources. {names} could not be read."
            # The status names the files; the reasons go to the error label
            # so nothing the user needs to act on is lost.
            self._set_error("; ".join(f"{path.name}: {reason}" for path, reason in failed))
        else:
            message = f"Cut {total} sources at {ratio}. {len(result.written)} frames written."
        self.status_label.setText(message)
        try:
            if result.last_prefix is not None and result.last_count is not None:
                self.update_preview(str(result.last_prefix), result.last_count)
        finally:
            self.action_btn.setEnabled(True)

    def _start_single(self, source: str, prefix: str, ratio_name: str) -> None:
        def cut() -> list[Path]:
            # Worker thread. `frame_written.emit` is the only crossing, and
            # Qt queues it to the GUI thread by itself.
            return pipeline.process_image(
                source,
                prefix,
                pipeline.RATIOS[ratio_name],
                on_frame=lambda done, total, path: self.frame_written.emit(done, total, path),
            )

        def done(written: list[Path]) -> None:
            # `count` is the detail-frame count update_preview expects; the
            # sentence counts every frame written, so the button's verb and
            # the number in the result agree.
            ratio = pipeline.RATIOS[ratio_name].name
            message = f"Cut {len(written)} frames at {ratio} into {Path(prefix).name}"
            self._finish(message, prefix, len(written) - 1, None)

        def failed(error: BaseException) -> None:
            self._finish(f"Could not cut {Path(source).name} — {error}", None, None, str(error))

        submit(cut, done, failed)

    def _start_batch(self, source: str, destination: str, ratio_name: str) -> None:
        def cut() -> pipeline.BatchResult:
            return pipeline.process_folder(
                source,
                destination,
                pipeline.RATIOS[ratio_name],
                on_progress=lambda done, total, path: self.source_started.emit(
                    done, total, path.name
                ),
            )

        def done(result: pipeline.BatchResult) -> None:
            self._finish_batch(result, ratio_name)

        def failed(error: BaseException) -> None:
            self._finish(f"Could not cut {Path(source).name} — {error}", None, None, str(error))

        submit(cut, done, failed)

    def process_images(self) -> None:
        self._set_error("")
        source = self.source_row.text()
        if not source or not Path(source).exists():
            self._set_error("That file is not there any more. Choose another source.")
            return
        destination = self.dest_row.text()
        if not destination:
            self._set_error("Choose where the frames should go.")
            return
        self.action_btn.setEnabled(False)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.status_label.setText("Cutting frames")
        ratio_name = self._ratio_name()
        if self.folder_radio.isChecked():
            self._start_batch(source, destination, ratio_name)
            return
        self._start_single(source, destination, ratio_name)
