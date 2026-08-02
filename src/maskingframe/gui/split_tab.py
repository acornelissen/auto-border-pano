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

import math
from collections.abc import Sequence
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QTimer, Signal
from PySide6.QtGui import QAccessible, QAccessibleEvent
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

from maskingframe import pipeline
from maskingframe.gui import settings, shell, theme
from maskingframe.gui.ribbon import FrameRibbon
from maskingframe.gui.strip import BorderPreview, ContactStrip
from maskingframe.gui.work import submit

# Built once so a run can do a plain dict lookup rather than scanning
# pipeline.RATIOS every time.
_RATIO_BY_DISPLAY: dict[str, str] = {r.display: r.name for r in pipeline.RATIOS.values()}

NO_COUNT = "Load a source to see the frame count"
"""Shown whenever the frame count is not known: no file, folder mode, or an
unreadable file. Never a stale or guessed number."""

NO_POSITIONS = "Frames are spread evenly. Load one panorama to place them by hand."
"""What stands where the ribbon would be when there is nothing to place --
folder mode, or no source. Silence would read as a missing feature rather
than a decision."""

KEY_HELP = (
    "Left and Right move the selected frame, Shift by ten steps, "
    "Home and End to the ends. Up and Down pick a frame."
)
"""What the keys do, said where the frames are actually placed.

Nothing else in the interface mentioned them, so the keyboard route existed
and was undiscoverable. It stands in the same line as `NO_POSITIONS`: the
sentence under the ribbon says either what you can do or why you cannot.
"""

KEY_STEP = 0.01
"""How far one arrow press moves a frame, as a fraction of the panorama's
width. Shift is ten of these and Home/End a hundred, which spans the whole
width and lets the clamp do the rest.

A round number in the unit a position is actually stored in, so the help
text can state it exactly. The widgets emit a count of these rather than a
distance: how far a step moves is policy, and the tab is the only thing that
knows what a percent of this panorama is."""

NUDGE_SETTLE_MS = 120
"""How long the keys must be still before the frames are made again.

A drag renders once, on release. A held arrow has no release: auto-repeat
fires 25 to 30 times a second, and rendering per repeat would queue dozens
of previews of a scan that can be 132MP. This is the equivalent pause --
comfortably longer than any repeat interval, so a held key renders once when
it stops, and short enough that a single press still feels immediate. Only
the render waits; the positions themselves move on the keystroke."""

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
        # Monotonic too, and for the same reason: a settle during a render
        # starts a newer one, and the older answer must not land on top of it.
        self._render_token = 0
        # True while a run or a preview is in flight. The single fact the
        # button states are derived from, so neither action can be started
        # twice.
        self._running = False
        self._positions: tuple[float, ...] = ()
        self._source_size: tuple[int, int] | None = None
        self._window_fraction = 0.0
        # The positions as they were when a strip drag began. A strip drag
        # reports displacement from the press point, so the tab adds it to
        # where the frame started rather than to wherever it has got to --
        # otherwise every move event would compound the last one.
        self._drag_anchor: tuple[float, ...] = ()
        # Which detail frame is marked, in detail-frame indices. The one
        # copy: both views are told, neither is asked.
        self._selected: int | None = None
        # Parented to this widget, so it cannot outlive it and fire into a
        # destroyed tab.
        self._nudge_timer = QTimer(self)
        self._nudge_timer.setSingleShot(True)
        self._nudge_timer.setInterval(NUDGE_SETTLE_MS)
        self._nudge_timer.timeout.connect(self._rerender)

        self._build()
        self._apply_button_states()
        self._refresh_border_preview()

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

        rail.addSpacing(theme.S)
        counter = QWidget()
        counter_row = QHBoxLayout(counter)
        counter_row.setContentsMargins(0, 0, 0, 0)
        counter_row.setSpacing(theme.S)
        # Secondary, not primary: chinagraph is for marking up, and two more
        # filled blocks of it beside the action would cost that action its
        # primacy. These are chrome.
        # A true minus, not a hyphen: beside a `+` at the same size a hyphen
        # sits too high and reads as a dash rather than an operator.
        self.remove_btn = QPushButton("−")  # noqa: RUF001
        self.remove_btn.setObjectName("Secondary")
        self.remove_btn.clicked.connect(self.remove_frame)
        self.add_btn = QPushButton("+")
        self.add_btn.setObjectName("Secondary")
        self.add_btn.clicked.connect(self.add_frame)
        counter_row.addWidget(self.remove_btn)
        counter_row.addWidget(self.add_btn)
        counter_row.addStretch(1)
        rail.addWidget(counter)

        rail.addSpacing(theme.S)
        # The selection in words. The marking on the picture is chinagraph,
        # and a state carried by colour alone fails the floor this project
        # holds itself to -- so it is also said here, and handed to the
        # widgets as their accessible name.
        self.selection_label = shell.data_label()
        rail.addWidget(self.selection_label)

        rail.addSpacing(theme.L)
        # No gap control: a split writes one frame at a time, so there is
        # nothing for a gap to sit between.
        self.border_controls = shell.BorderControls(
            scope=settings.SPLIT, show_gutter=False, show_detail_toggle=True
        )
        self.border_controls.reload_presets()
        self.border_controls.restore_style(settings.load_style(settings.SPLIT))
        self.border_controls.style_changed.connect(self._on_style_changed)
        self.border_controls.style_settled.connect(self._on_style_settled)
        rail.addWidget(self.border_controls)

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

        # Preview is free and reversible, so it sits below the action that
        # writes to disk rather than beside it as a peer -- but it is still a
        # button. Styled as bare text it read as a caption hanging off the
        # primary; an outline with no fill keeps the hierarchy and the
        # affordance at the same time. Compose's rail says this identically.
        rail.addSpacing(theme.S)
        self.preview_btn = QPushButton("Preview")
        self.preview_btn.setObjectName("Secondary")
        self.preview_btn.clicked.connect(self.preview)
        rail.addWidget(self.preview_btn)

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

        # Source above, results below: the ribbon says where the frames come
        # from, the strip says what they are.
        self.ribbon = FrameRibbon(self.columns.table)
        self.ribbon.frame_moved.connect(self._on_frame_moved)
        self.ribbon.frame_settled.connect(self._on_frame_settled)
        self.ribbon.setVisible(False)
        self.columns.table_layout.addWidget(self.ribbon)

        self.ribbon_note = shell.help_label(NO_POSITIONS)
        self.columns.table_layout.addWidget(self.ribbon_note)

        self.columns.table_layout.addSpacing(theme.M)

        # An object lying on the light table, not a panel filling it.
        self.strip = ContactStrip(self.columns.table)
        self.strip.frame_dragged.connect(self._on_frame_dragged)
        self.strip.frame_drag_settled.connect(self._on_frame_drag_settled)
        # No top alignment and no stretch under it: the strip fills the
        # table, so the frames are as large as the window allows.
        self.columns.table_layout.addWidget(self.strip, 1)

        self.ribbon.frame_nudged.connect(self._on_frame_nudged)
        self.ribbon.selection_changed.connect(self._on_ribbon_selection)
        self.strip.frame_nudged.connect(self._on_strip_nudged)
        self.strip.selection_changed.connect(self._on_strip_selection)
        # Source, then results, matching how they sit on the table.
        self.setTabOrder(self.ribbon, self.strip)

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

    def _style(self) -> pipeline.FrameStyle:
        """The border the rail currently describes. GUI thread only.

        Named `_style` rather than `style` because `QWidget.style()` is
        already taken, and the control it reads is `frame_style()` for the
        same reason.
        """
        return self.border_controls.frame_style()

    def _on_style_changed(self, style: pipeline.FrameStyle) -> None:
        """Every movement of a control. Cheap work only.

        Persists the choice, so the next launch opens on the same border,
        and moves the live overlay. It deliberately does not touch a render
        already on the table: re-rendering per pixel of a drag is not
        possible, and dropping the render instead would blank the table for
        the length of the drag.
        """
        settings.save_style(settings.SPLIT, style)
        self._refresh_border_preview()

    def _on_style_settled(self, style: pipeline.FrameStyle) -> None:
        """The hand has stopped. Now the frames themselves can be redone.

        Persists too, and not only because a settle can follow a change:
        choosing a preset settles without ever changing, so saving here is
        the only thing that makes that choice survive a relaunch.
        """
        settings.save_style(settings.SPLIT, style)
        self._rerender()

    def _refresh_border_preview(self) -> None:
        """Show the border on the strip, as the rail currently describes it.

        Frame 1 always carries the border; the detail frames only do when
        the toggle says so, and the drawing has to say the same thing or it
        would be promising a frame the run will not write.
        """
        style = self._style()
        ratio = pipeline.RATIOS[self._ratio_name()]
        self.strip.set_border_preview(
            BorderPreview(
                aspect=ratio.width / ratio.height,
                border=style.border_percent / 100,
                colour=style.border_colour,
                first_frame_only=not style.border_detail_frames,
            )
        )

    # --- Where the detail frames land ---------------------------------------

    def positions(self) -> tuple[float, ...]:
        """Where the detail frames land. The one copy; both views read it."""
        return self._positions

    def _set_positions(self, positions: Sequence[float]) -> None:
        """Adopt a new plan and tell both views about it. GUI thread only.

        Normalised through `pipeline` rather than trusted: a drag is clamped
        by the widget that produced it, but the tab is the only thing that
        knows the source's real size, so the last word on what is inside the
        picture belongs here.
        """
        if self._source_size is None:
            self._positions = tuple(positions)
        else:
            width, height = self._source_size
            self._positions = pipeline.normalise_positions(
                positions, width, height, pipeline.RATIOS[self._ratio_name()]
            )
        self.ribbon.set_plan(self._positions, self._window_fraction)
        # The ribbon drops a selection the new plan cannot hold, so the tab
        # has to make the same decision or the two would disagree about
        # which frame is marked.
        if self._selected is not None and self._selected >= len(self._positions):
            self._set_selected(None)
        else:
            self._state_selection()

    def _show_ribbon(self, visible: bool) -> None:
        """Show the ribbon, or the sentence explaining why there isn't one.

        The note stays put either way: with the ribbon up it states the keys,
        because a user placing frames is exactly who needs to know they exist.
        """
        self.ribbon.setVisible(visible)
        self.ribbon_note.setText(KEY_HELP if visible else NO_POSITIONS)
        self.strip.set_draggable(visible)

    def _move_position(
        self, index: int, wanted: float, anchor: Sequence[float] | None = None
    ) -> None:
        """Move one frame, under the one ordering rule. GUI thread only.

        Both drags come through here. The rule itself lives in `pipeline`
        because it needs the source's size and the target ratio, which is
        knowledge neither the ribbon nor the strip has and neither should
        grow: the tab is the only place that holds both, so it is the only
        place the rule can be applied once for both views.
        """
        if self._source_size is None:
            return
        width, height = self._source_size
        base = self._positions if anchor is None else anchor
        self._set_positions(
            pipeline.move_position(
                base, index, wanted, width, height, pipeline.RATIOS[self._ratio_name()]
            )
        )

    def selected(self) -> int | None:
        """Which detail frame is marked, in detail-frame indices."""
        return self._selected

    def _set_selected(self, index: int | None) -> None:
        """Mark one detail frame in both views, and say so in the rail.

        The tab holds the one copy, as it does for the positions: two views
        that disagreed about which frame was selected would be two features.
        The ribbon speaks detail indices and the strip speaks strip indices,
        so the conversion happens here -- the same place the drags convert.
        """
        # An index with no position behind it is not a selection. Refused
        # here rather than at each reader: without a plan there is nothing to
        # place, and a phantom kept now would be promoted into a selection
        # the user never made the moment a panorama loaded.
        if index is not None and not 0 <= index < len(self._positions):
            index = None
        self._selected = index
        self.ribbon.set_selected(index)
        self.strip.set_selected(None if index is None else index + 1)
        self._state_selection()

    def _state_selection(self) -> None:
        """Say what is selected, once, in the one place that knows.

        The rail's sentence is handed to both widgets verbatim as their
        accessible description, so a screen reader and the screen say the
        same thing wherever focus is. It has to come from here: a percent of
        this panorama's width is knowledge neither widget has, and the strip
        saying only "Frame 3 of 5" told a user pressing Right that nothing
        had changed.
        """
        if self._selected is None or not 0 <= self._selected < len(self._positions):
            self._announce("")
            return
        along = math.floor(self._positions[self._selected] * 100 + 0.5)
        self._announce(f"Frame {self._selected + 2} · {along}% along")

    def _announce(self, sentence: str) -> None:
        """Say the sentence three times over: on screen, and to each view.

        Setting `accessibleDescription` stores a string and raises nothing,
        so a screen reader reads it once when focus arrives and never learns
        that it changed -- a user holding Right heard silence while the rail
        counted up. `updateAccessibility` is what turns the stored property
        into something spoken.

        The event goes to both views rather than to whichever has focus.
        Assistive technology speaks events for the object the user is on and
        ignores the rest, and the tab does not track focus; asking it to
        would be a second copy of a fact Qt already holds.
        """
        self.selection_label.setText(sentence)
        for view in (self.ribbon, self.strip):
            view.setAccessibleDescription(sentence)
            QAccessible.updateAccessibility(
                QAccessibleEvent(view, QAccessible.Event.DescriptionChanged)
            )

    def _nudge(self, index: int, steps: int) -> None:
        """Move one detail frame by `steps` of `KEY_STEP`. GUI thread only.

        Straight through `_move_position`, so a key press and a drag obey
        the one ordering rule and cannot disagree.
        """
        if not 0 <= index < len(self._positions):
            return
        self._move_position(index, self._positions[index] + steps * KEY_STEP)
        # Told, not just re-read: the frame has moved, so both views'
        # accessible names have to be redone to match the rail.
        self._set_selected(index)
        # Restarted on every repeat, so a held key renders once when it
        # stops. `_rerender` is still governed by `_render_token`, so a
        # render already in flight when this fires is dropped rather than
        # painted over the newer one.
        self._nudge_timer.start()

    def _on_frame_nudged(self, index: int, steps: int) -> None:
        self._nudge(index, steps)

    def _on_strip_nudged(self, index: int, steps: int) -> None:
        # Strip frame 1 is detail frame 0: frame 1 is the whole panorama.
        self._nudge(index - 1, steps)

    def _on_ribbon_selection(self, index: int) -> None:
        self._set_selected(index)

    def _on_strip_selection(self, index: int) -> None:
        self._set_selected(index - 1)

    def _on_frame_moved(self, index: int, wanted: float) -> None:
        """Every movement of a ribbon drag. Cheap work only."""
        self._move_position(index, wanted)

    def _on_frame_settled(self, _index: int) -> None:
        """The hand has stopped. Now the frames themselves can be redone."""
        self._rerender()

    def _on_frame_dragged(self, index: int, delta: float) -> None:
        """A drag inside strip frame `index`. Frame 0 is the whole panorama.

        The strip reports its delta in frame widths because it has no idea
        how wide the panorama is; here it becomes a fraction of the width,
        measured from where the frame stood when the drag began.
        """
        detail = index - 1
        if not 0 <= detail < len(self._positions):
            return
        if not self._drag_anchor:
            self._drag_anchor = self._positions
        wanted = self._drag_anchor[detail] + delta * self._window_fraction
        self._move_position(detail, wanted, anchor=self._drag_anchor)

    def _on_frame_drag_settled(self, _index: int) -> None:
        self._drag_anchor = ()
        self._rerender()

    def add_frame(self) -> None:
        """One more detail frame, in the widest stretch nothing covers.

        A new frame should land on something nobody is looking at yet, which
        is a judgement `pipeline` already makes; this only supplies the size
        of the source it needs to make it.
        """
        if self._source_size is None or not self._positions:
            return
        width, height = self._source_size
        self._set_positions(
            pipeline.insert_position(
                self._positions, width, height, pipeline.RATIOS[self._ratio_name()]
            )
        )
        self._apply_count_states()
        self._rerender()

    def remove_frame(self) -> None:
        """One fewer, taken from the end. Never below two."""
        if len(self._positions) <= 2:
            return
        self._set_positions(pipeline.drop_position(self._positions))
        self._apply_count_states()
        self._rerender()

    def _apply_count_states(self) -> None:
        """The one place that decides whether the pair is pressable.

        Derived from the plan itself, so it cannot go out of date, and it
        also updates every readout the count feeds -- the label, the
        button's number and the band all count what a run will actually
        write. The band is in here rather than only in `_apply_facts`
        because adding or removing a frame changes the count without any
        facts arriving, and a band left saying the old number is the one
        readout on screen contradicting the other two.

        The ratio comes from the combobox here, not from an answer in
        flight, and that is safe: any change to it bumps the inspection
        token, so a stale answer never reaches this.
        """
        placed = len(self._positions)
        self.add_btn.setEnabled(placed > 0)
        self.remove_btn.setEnabled(placed > 2)
        if placed:
            self.count_label.setText(f"{placed + 1} frames")
            self.action_btn.setText(f"Cut {placed + 1} frames")
            self._set_band(self._subject, f"{self._ratio_name()} · {placed + 1} frames")

    def _load_ribbon_picture(self, token: int) -> None:
        """Decode a small copy of the panorama for the ribbon to draw.

        Off the GUI thread like every other decode here, and behind the same
        inspection token: a user can pick a second file before the first
        picture arrives, and the older one must not land on the newer plan.
        """
        source = self.source_row.text()

        def read() -> Image.Image | None:
            # Worker thread. Returns plain data; touches no widget.
            try:
                return pipeline.ribbon_thumbnail(source)
            except Exception:
                return None

        def done(image: Image.Image | None) -> None:
            if token != self._inspect_token:
                return
            self.ribbon.set_source(image)

        submit(read, done, lambda _error: None, owner=self)

    def _rerender(self) -> None:
        """Make the frames on the table again, under the settings now in force.

        The frames a preview puts on the strip have their border rendered
        into them, so the moment the rail moves they are a picture of
        settings nobody has any more. The answer is to render them again,
        not to drop them: the old picture stays up, a moment out of date,
        and the new frames swap in when they land. Blanking the strip on
        every settle was the flicker this replaced.

        With nothing rendered there is nothing to redo -- the apertures are
        empty and the live overlay is already drawing exactly what the rail
        says. When a render *is* up and cannot be made again, the strip
        does go back to the overlay, and the status line says so.
        """
        if self.strip.exposed == 0:
            return
        if self._running or not self.can_preview():
            if self.strip.clear_images():
                self.status_label.setText(shell.STALE_PREVIEW)
            return
        self._render(updating=True)

    def _on_selection_changed(self, *_args: object) -> None:
        """Re-read the source's header. GUI thread only.

        Bumping the token first means any inspection already in flight is
        stale from here on, whichever way this call ends.
        """
        self._inspect_token += 1
        token = self._inspect_token
        source = self.source_row.text()
        # Everything this method reacts to -- the source, the mode, the ratio
        # -- also decides whether Preview is pressable.
        self._apply_button_states()
        # The ratio arrives through here too, and it decides the shape of the
        # frame the border is drawn around. The overlay can be redrawn now;
        # the frames cannot, because a new ratio gives the panorama a new
        # count and new positions and those have not arrived yet. Rendering
        # here would put frames on the strip that a run would not write, so
        # the re-render waits for the facts that describe it.
        self._refresh_border_preview()
        # The band names whatever is loaded, folder or file -- it is the one
        # thing on screen that says what you are working on.
        subject = Path(source).name if source else ""
        if not source or self.folder_radio.isChecked():
            self._clear_facts(subject)
            # No facts are coming, so this is the last chance to say that
            # whatever is on the strip is a picture of nothing selected.
            self._rerender()
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
            owner=self,
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

        The re-render is here rather than where the selection changed, and
        for the same reason: it draws the plan, and this is where the plan
        arrives. The token check above is what keeps that honest -- an
        answer that has been superseded starts no render at all.
        """
        if token != self._inspect_token:
            return
        if facts is None:
            self._clear_facts(subject)
            self._rerender()
            return
        self.facts_label.setText(f"{facts.width} × {facts.height} · {facts.native_ratio}")  # noqa: RUF001
        self.count_label.setText(f"{facts.frame_count} frames")
        self.action_btn.setText(f"Cut {facts.frame_count} frames")
        self._set_band(subject, f"{ratio_name} · {facts.frame_count} frames" if ratio_name else "")
        self._source_size = (facts.width, facts.height)
        self._window_fraction = facts.window_fraction
        self._set_positions(facts.positions)
        # The strip learns the count here, not when the first render lands.
        # Everything above this line already states it -- the rail, the band
        # and the button -- and the strip used to keep its construction-time
        # apertures until a preview arrived, so two parts of one screen
        # disagreed about how many frames there were.
        #
        # Only while the apertures are empty, because `set_frames` discards
        # every thumbnail. With a preview up the old picture stays up and is
        # relabelled by the render that is about to replace it -- that is the
        # rule `_rerender` documents, and it reads `strip.exposed` to decide,
        # so blanking the strip here would tell it there was nothing to redo
        # and no new preview would ever start.
        if self.strip.exposed == 0 and self.strip.frame_count != facts.frame_count:
            self._set_strip_frames(preview_titles(len(facts.positions)))
        self._show_ribbon(True)
        self._load_ribbon_picture(token)
        self._apply_count_states()
        self._state_selection()
        self._rerender()

    def _clear_facts(self, subject: str = "") -> None:
        self._nudge_timer.stop()
        self.facts_label.setText("")
        self.count_label.setText(NO_COUNT)
        self.action_btn.setText(UNCOUNTED_ACTION)
        self._set_band(subject, "")
        self._positions = ()
        self._source_size = None
        self._window_fraction = 0.0
        self._drag_anchor = ()
        self.ribbon.set_source(None)
        self.ribbon.set_plan((), 0.0)
        self._show_ribbon(False)
        self._set_selected(None)
        self._apply_count_states()

    def _set_error(self, message: str) -> None:
        self.error_label.setText(message)

    def can_preview(self) -> bool:
        """Preview needs a readable single panorama, and nothing else.

        No destination: previewing writes nothing, so demanding a folder
        first would be asking for a decision the action does not use. Folder
        mode is out because there is no one panorama to render.
        """
        source = self.source_row.text()
        return bool(source) and not self.folder_radio.isChecked() and Path(source).is_file()

    def _apply_button_states(self) -> None:
        """The single place that decides which buttons are pressable.

        Derived from two facts only -- is something in flight, and is there a
        panorama to preview -- so it cannot go out of date. Called from
        construction, from every change to the selection, and from both ends
        of a run.
        """
        self.action_btn.setEnabled(not self._running)
        self.preview_btn.setEnabled(not self._running and self.can_preview())

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

    def _set_strip_frames(self, titles: list[str]) -> None:
        """Relabel the strip and put the mark back where it was.

        `set_frames` drops a selection the new frame list cannot hold, which
        is right for the widget and wrong for the tab: rendering a preview
        must not silently unmark the frame the user is placing.
        """
        self.strip.set_frames(titles)
        # Clamped, not re-imposed: `set_frames` drops a selection the new
        # list cannot hold, and putting one back past its end would give the
        # strip an index every reader in it trusts and none of them check.
        wanted = None if self._selected is None else self._selected + 1
        if wanted is not None and not 1 <= wanted < len(titles):
            wanted = None
        self.strip.set_selected(wanted)

    def update_preview(self, output_prefix: str, count: int) -> None:
        self._set_strip_frames(preview_titles(count))
        self.strip.show_paths(pipeline.output_paths(output_prefix, count))

    def _set_frame_progress(self, done: int, total: int, path: object) -> None:
        """Runs on the GUI thread. Progress *is* the strip.

        Each frame appears as it lands on disk, so a single-file run is no
        longer a bar going 0 to 100 with nothing in between.
        """
        if self.strip.frame_count != total:
            self._set_strip_frames(preview_titles(total - 1))
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
        self._running = False
        try:
            if prefix is not None and count is not None:
                self.update_preview(prefix, count)
        finally:
            self._apply_button_states()
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
        self._running = False

        if total == 0:
            self.status_label.setText("No JPGs in that folder. Masking Frame reads .jpg and .jpeg.")
            self._apply_button_states()
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
            self._apply_button_states()

    def _start_single(self, source: str, prefix: str, ratio_name: str) -> None:
        # Read on the GUI thread and closed over, exactly like the ratio: a
        # worker re-reading the controls could render one border and caption
        # it with another.
        style = self._style()
        positions = self._positions or None

        def cut() -> list[Path]:
            # Worker thread. `frame_written.emit` is the only crossing, and
            # Qt queues it to the GUI thread by itself.
            return pipeline.process_image(
                source,
                prefix,
                pipeline.RATIOS[ratio_name],
                on_frame=lambda done, total, path: self.frame_written.emit(done, total, path),
                positions=positions,
                style=style,
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

        submit(cut, done, failed, owner=self)

    def _start_batch(self, source: str, destination: str, ratio_name: str) -> None:
        style = self._style()

        def cut() -> pipeline.BatchResult:
            return pipeline.process_folder(
                source,
                destination,
                pipeline.RATIOS[ratio_name],
                on_progress=lambda done, total, path: self.source_started.emit(
                    done, total, path.name
                ),
                style=style,
            )

        def done(result: pipeline.BatchResult) -> None:
            self._finish_batch(result, ratio_name)

        def failed(error: BaseException) -> None:
            self._finish(f"Could not cut {Path(source).name} — {error}", None, None, str(error))

        submit(cut, done, failed, owner=self)

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
        # A settle still pending from a nudge would land inside the run and
        # put the strip back to the overlay, over a status that has just
        # said the run is in flight.
        self._nudge_timer.stop()
        self._running = True
        self._apply_button_states()
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.status_label.setText("Cutting frames")
        ratio_name = self._ratio_name()
        if self.folder_radio.isChecked():
            self._start_batch(source, destination, ratio_name)
            return
        self._start_single(source, destination, ratio_name)

    def preview(self) -> None:
        """Render the frames a run would write, without writing any of them.

        No destination is read: nothing lands on disk, so there is nothing to
        ask where to put. The button is disabled unless `can_preview()`
        holds; the guard here is a safety net for programmatic callers.
        """
        if not self.can_preview() or self._running:
            return
        self._set_error("")
        self._render(updating=False)

    def _render(self, *, updating: bool) -> None:
        """Render the frames off the GUI thread and show them when they land.

        One path for both the button and a re-render; `updating` is the
        difference between them, and it is only ever about what the user
        sees. A pressed Preview owns the buttons and says it is working; a
        re-render leaves the rail alone, because the user is still in the
        middle of setting something and taking their controls away mid-drag
        would be the interface fighting them.

        The ratio and the style are read here, on the GUI thread, and
        travel into the job. A worker re-reading them could render one
        border and caption it with another. The token does the same job for
        time: a settle during a render starts a newer one, and the older
        answer is dropped rather than painted over the newer.
        """
        self._render_token += 1
        token = self._render_token
        source = self.source_row.text()
        ratio_name = self._ratio_name()
        style = self._style()
        positions = self._positions or None
        if updating:
            self.status_label.setText(shell.UPDATING_PREVIEW)
        else:
            # This render supersedes any settle still waiting, for the same
            # reason a run does.
            self._nudge_timer.stop()
            self._running = True
            self._apply_button_states()
            self.status_label.setText("Rendering preview")

        def render() -> list[Image.Image]:
            # Worker thread. Touches no widget; the frames come back as plain
            # data and are shown on the GUI thread below. `cached` lets a
            # second render of the same source skip the decode, which is
            # what makes re-rendering a 132MP scan bearable.
            return pipeline.preview_frames(
                source,
                pipeline.RATIOS[ratio_name],
                style,
                cached=True,
                positions=positions,
            )

        def done(frames: list[Image.Image]) -> None:
            if not updating:
                self._running = False
                self._apply_button_states()
            if token != self._render_token:
                return
            ratio = pipeline.RATIOS[ratio_name].name
            self.status_label.setText(f"Preview of {len(frames)} frames at {ratio}")
            self._set_strip_frames(preview_titles(len(frames) - 1))
            self.strip.show_images(frames)

        def failed(error: BaseException) -> None:
            # The same inline path a failed run takes. No modal, here or
            # anywhere else in this tab. The frames already on the strip
            # stay: they are out of date, but they are more use than an
            # empty table.
            if not updating:
                self._running = False
                self._apply_button_states()
            if token != self._render_token:
                return
            self.status_label.setText(f"Could not preview {Path(source).name} — {error}")
            self._set_error(str(error))

        submit(render, done, failed, owner=self)
