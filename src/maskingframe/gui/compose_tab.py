"""The diptych and triptych tab, as Qt draws it.

Pick two or three images, choose a target ratio, and the arrangement is
solved automatically from the images' own shapes.

Two things carry over from the tkinter build unchanged in spirit and are
worth stating up front, because both were earned:

1. **No modal ever.** Every rule this interface has is enforced by making
   the control unpressable, and the one thing left to say -- a file that
   would not compose, a missing destination, sources left out -- goes to an
   inline chinagraph line. There is not a `QMessageBox` in this module.
2. **Never state an arrangement the solver has not returned.** The layout
   name is live, recomputed off the GUI thread whenever the list or the
   ratio changes, and it shows nothing rather than something stale.

What is genuinely new is the concurrency. Qt queues a worker's result back
to the GUI thread by itself, so `gui.work.submit` takes a job that returns
plain data and hands it to a callback here. There is no `root.after` and no
window-closed guard. The token guard stays, because staleness does not.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from PIL import Image
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from maskingframe import pipeline
from maskingframe.gui import settings, shell, theme
from maskingframe.gui.sources import Source, SourcesList
from maskingframe.gui.strip import BorderPreview, ContactStrip, Rect
from maskingframe.gui.work import submit

MIN_IMAGES = 2
MAX_IMAGES = 3

EMPTY_STATE = "Add two sources for a diptych, three for a triptych."
ONE_MORE = "Add one more source."
NO_PREFIX = "Choose where the composite should go."
ORDER_HINT = "Left to right, in this order."
WORKING = "Composing"

IMAGE_FILTER = "Image files (*.jpg *.jpeg *.JPG *.JPEG);;All files (*)"

_RATIO_BY_DISPLAY: dict[str, str] = {r.display: r.name for r in pipeline.RATIOS.values()}


def _composite_noun(count: int) -> str:
    """What this many sources makes. Empty when it makes nothing yet."""
    if count == MIN_IMAGES:
        return "Diptych"
    if count == MAX_IMAGES:
        return "Triptych"
    return ""


_NUMBER_WORDS = {2: "two", 3: "three"}

# Two panels in a row or a column are not "a row of two" -- they are side by
# side, or one above the other. Only these two cases get their own phrasing,
# and only because a diptych has an everyday name for its arrangement that a
# triptych does not. Everything else is derived, so a new arrangement in the
# solver cannot go unnamed here.
_TWO_UP_PHRASING = {"row": "side by side", "column": "one above the other"}

# Everything the axis word alone decides. A `row` runs left to right and the
# pair inside it is stacked; a `column` runs top to bottom and the pair
# inside it is side by side. Both facts follow from the axis, which is why
# the split names below need no table of their own.
_AXIS: dict[str, tuple[tuple[str, str], str]] = {
    "row": (("left", "right"), "stacked"),
    "column": (("on top", "below"), "side by side"),
}


def _split_arrangement(axis: str, groups: list[str]) -> str:
    """Name a `<axis>-<n>-then-<n>` arrangement the way a photographer would.

    `Row one then two` says nothing about where the panels are; this says
    which side each group is on and how the group of two is arranged, both
    read off the axis rather than off a table of arrangements.
    """
    positions, pairing = _AXIS[axis]
    parts = []
    for group, position in zip(groups, positions, strict=False):
        pairing_words = "" if group == "one" else f" {pairing}"
        parts.append(f"{group}{pairing_words} {position}")
    return ", ".join(parts)


def present_layout(name: str, count: int) -> str:
    """Turn the solver's own name for an arrangement into human copy.

    Derived mechanically from whatever `layout.candidates` yields. A bare
    axis name (`row`, `column`) gets the count of panels in it, or the
    everyday two-up phrasing; a split name (`row-one-then-two`) is read as
    axis plus the two groups, and the axis alone says which side each group
    sits on. Deliberately not a lookup table of every arrangement: such a
    table rots silently the day the solver gains one, whereas this only ever
    fails to *improve* on a name it has not seen.
    `test_present_layout_reads_the_solver_name_as_a_sentence` walks the
    solver's own candidate list, so an unnamed arrangement fails the suite.
    """
    if not name:
        return ""
    axis, _, tail = name.partition("-")
    if not tail:
        if count == MIN_IMAGES and axis in _TWO_UP_PHRASING:
            words = _TWO_UP_PHRASING[axis]
        else:
            words = f"{axis} of {_NUMBER_WORDS.get(count, str(count))}"
    elif axis in _AXIS and tail.count("-then-") == 1:
        words = _split_arrangement(axis, tail.split("-then-"))
    else:
        # An arrangement whose name does not parse still reads as words
        # rather than as a slug.
        words = name.replace("-", " ")
    return words[0].upper() + words[1:]


def _save_label(count: int) -> str:
    """Name what Save will actually write, live as the list changes."""
    if count == MIN_IMAGES:
        return "Save diptych"
    if count == MAX_IMAGES:
        return "Save triptych"
    return "Save composite"


@dataclass(frozen=True)
class _Solve:
    """What the off-thread solve brings back. Plain data, no widgets."""

    token: int
    name: str
    count: int
    sizes: dict[str, tuple[int, int]]


@dataclass(frozen=True)
class _Composed:
    """A finished Save. The path is where it landed on disk."""

    path: Path
    layout_name: str
    ratio_name: str


@dataclass(frozen=True)
class _Previewed:
    """A finished Preview. The image never touches disk."""

    image: Image.Image
    layout_name: str
    ratio_name: str
    count: int


def _solve_job(
    token: int,
    sources: list[str],
    ratio_name: str,
    style: pipeline.FrameStyle,
) -> _Solve:
    """Runs on a worker. Opens files, touches no widget.

    One unreadable file must not cost the others their dimensions, and a
    count the solver cannot arrange is not an error to report -- it is
    simply no name to show.

    The style arrives as an argument for the same reason the ratio does: a
    job that re-read the controls could solve for one gap and have its
    answer captioned with another.
    """
    sizes: dict[str, tuple[int, int]] = {}
    for source in sources:
        try:
            facts = pipeline.inspect_source(source)
        except OSError:
            continue
        sizes[source] = (facts.width, facts.height)
    try:
        name = pipeline.name_layout(sources, pipeline.RATIOS[ratio_name], style)
    except (ValueError, OSError):
        name = ""
    return _Solve(token=token, name=name, count=len(sources), sizes=sizes)


class ComposeTab(QWidget):
    """Two or three sources, one frame."""

    band_changed = Signal(str, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.images: list[str] = []
        self._selection: int | None = None
        # Tracks the last prefix this class itself derived from the first
        # image, so _refresh_list can tell "the user hasn't touched this
        # field" apart from "the user typed their own prefix" and only
        # overwrite the former.
        self._derived_prefix: str = ""
        self._subject = ""
        self._detail = ""

        # The arrangement the solver last returned for the current list and
        # ratio, and the token of the request that produced it. Every solve
        # is stamped so a slow two-image solve landing after a third image
        # was added cannot overwrite the newer answer.
        self._solved: str = ""
        self._solve_token = 0
        # Pixel sizes by path. Cached because the same source is re-listed
        # on every add, remove and reorder, and re-reading its header each
        # time would be wasteful.
        self._sizes: dict[str, tuple[int, int]] = {}

        self._build_ui()
        self._refresh_list()

    # --- what the band stencils ---------------------------------------------

    @property
    def subject(self) -> str:
        return self._subject

    @property
    def detail(self) -> str:
        return self._detail

    def _set_band(self, subject: str, detail: str) -> None:
        if (subject, detail) == (self._subject, self._detail):
            return
        self._subject, self._detail = subject, detail
        self.band_changed.emit(subject, detail)

    # --- construction -------------------------------------------------------

    def _build_ui(self) -> None:
        # The rail reads top to bottom as a sentence -- these sources, at
        # this format, to here, go -- and in the same order as the Split
        # tab's rail, so switching tabs does not re-lay-out the window.
        self.columns = shell.TwoColumn(self)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.columns)

        rail = self.columns.rail_layout

        rail.addWidget(shell.section("Sources"))
        rail.addSpacing(theme.S)

        # Numbered rows in the contact strip's own visual language, because
        # the number *is* the arrangement: reordering here moves a numbered
        # frame there.
        self.listbox = SourcesList()
        self.listbox.selection_changed.connect(self._on_select)
        rail.addWidget(self.listbox)

        # A row under the list rather than a column beside it: the list is
        # the subject, the four controls act on it. Add grows the list, the
        # other three act on whichever row is selected, so it sits alone at
        # the left edge and they cluster at the right.
        buttons = QWidget()
        button_row = QHBoxLayout(buttons)
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(theme.S)

        self.add_btn = QPushButton("+ Add")
        self.add_btn.clicked.connect(self.add_image)
        button_row.addWidget(self.add_btn)
        button_row.addStretch(1)

        self.up_btn = self._glyph_button("↑", "Move earlier", self.move_up)
        self.down_btn = self._glyph_button("↓", "Move later", self.move_down)
        self.remove_btn = self._glyph_button("×", "Remove", self.remove)  # noqa: RUF001
        for button in (self.up_btn, self.down_btn, self.remove_btn):
            button_row.addWidget(button)

        rail.addSpacing(theme.S)
        rail.addWidget(buttons)

        rail.addSpacing(theme.S)
        rail.addWidget(shell.help_label(ORDER_HINT))

        rail.addSpacing(theme.L)
        rail.addWidget(shell.section("Format"))
        rail.addSpacing(theme.S)
        self.ratio_combo = shell.Combo()
        self.ratio_combo.addItems([r.display for r in pipeline.RATIOS.values()])
        self.ratio_combo.setCurrentText(pipeline.DEFAULT_RATIO.display)
        self.ratio_combo.currentIndexChanged.connect(self._on_ratio_change)
        rail.addWidget(self.ratio_combo)

        # The consequence of the ratio, stated before the user commits to it.
        rail.addSpacing(theme.S)
        self.layout_label = shell.help_label("")
        rail.addWidget(self.layout_label)

        # Between FORMAT and DESTINATION, the same slot the Split tab gives
        # it: the two rails are one product and must not drift apart.
        rail.addSpacing(theme.L)
        self.border_controls = shell.BorderControls(show_gutter=True, show_detail_toggle=False)
        self.border_controls.set_style(settings.load_style(settings.COMPOSE))
        self.border_controls.style_changed.connect(self._on_style_changed)
        rail.addWidget(self.border_controls)

        rail.addSpacing(theme.L)
        rail.addWidget(shell.section("Destination"))
        rail.addSpacing(theme.S)
        # Field and button side by side, exactly as the Split tab builds its
        # own output row. The two rails are one product.
        self.output_row = shell.PathRow("Choose folder")
        self.output_row.button.clicked.connect(self.browse_output)
        rail.addWidget(self.output_row)

        rail.addSpacing(theme.L)
        self.save_btn = QPushButton(_save_label(0))
        self.save_btn.setObjectName("Primary")
        self.save_btn.clicked.connect(self.save)
        rail.addWidget(self.save_btn)

        # Preview is free and reversible, so it sits below the action that
        # writes to disk rather than beside it as a peer -- but it is still a
        # button. Styled as bare text it read as a caption hanging off the
        # primary; an outline with no fill keeps the hierarchy and the
        # affordance at the same time.
        rail.addSpacing(theme.S)
        self.preview_btn = QPushButton("Preview")
        self.preview_btn.setObjectName("Secondary")
        self.preview_btn.clicked.connect(self.preview)
        rail.addWidget(self.preview_btn)

        # Only ever a reason to act on: a file that would not compose, a
        # missing prefix, sources left out.
        rail.addSpacing(theme.M)
        self.hint_label = shell.help_label("")
        rail.addWidget(self.hint_label)

        # The resting sentence: what this makes, how it is arranged, at what
        # ratio -- the same slot the Split tab gives its status line.
        rail.addSpacing(theme.S)
        self.status_label = shell.help_label(EMPTY_STATE)
        rail.addWidget(self.status_label)
        rail.addStretch(1)

        # One frame, not four: a composite is a single image. The strip
        # still renders its unexposed state before anything is composed.
        self.previews = ContactStrip(frames=1)
        # Top of the table, at its natural height: the strip is an object
        # lying on the light table, not a panel filling it.
        # No stretch under it: the strip fills the table, so the composite
        # preview is as large as the window allows.
        self.columns.table_layout.addWidget(self.previews, 1)

    def _glyph_button(self, glyph: str, tip: str, handler: Callable[[], None]) -> QPushButton:
        """A one-glyph button whose tooltip is its only accessible name."""
        button = QPushButton(glyph)
        button.setFixedWidth(34)
        button.setToolTip(tip)
        button.setAccessibleName(tip)
        button.clicked.connect(handler)
        return button

    # --- state --------------------------------------------------------------

    def can_compose(self) -> bool:
        return MIN_IMAGES <= len(self.images) <= MAX_IMAGES

    def _bare_ratio(self) -> str:
        """The ratio as the user reads it, e.g. '4:5' -- never the display form."""
        return pipeline.RATIOS[self._ratio_name()].name

    def _ratio_name(self) -> str:
        return _RATIO_BY_DISPLAY.get(self.ratio_combo.currentText(), pipeline.DEFAULT_RATIO.name)

    def _style(self) -> pipeline.FrameStyle:
        """The border and gap as the controls currently read.

        Always called on the GUI thread and captured into a local before a
        job starts, never from inside one.
        """
        return self.border_controls.frame_style()

    def _on_style_changed(self, style: pipeline.FrameStyle) -> None:
        """Persist the choice and re-solve: the gap can change which
        arrangement wins, so the name in the rail would otherwise be
        describing the previous solution."""
        settings.save_style(settings.COMPOSE, style)
        self._discard_stale_preview()
        self._request_layout_name()
        self._refresh_border_preview()

    def _aspects(self) -> list[float] | None:
        """The sources' aspect ratios, or None while any is still unknown.

        Read from the cache the off-thread solve fills in, never from disk:
        this is called on every slider move, and a header read on the GUI
        thread is exactly what stalls a 132MP scan.
        """
        if not self.can_compose():
            return None
        aspects = []
        for path in self.images:
            size = self._sizes.get(path)
            if size is None or size[1] <= 0:
                return None
            aspects.append(size[0] / size[1])
        return aspects

    def _refresh_border_preview(self) -> None:
        """Draw the border, and the gaps between panels, on the strip.

        The gaps are as much of a composite as the outer border is, so they
        are shown in their own colour rather than left to the imagination.
        With fewer than two sources there is no arrangement to solve, and
        the outer border goes on alone.
        """
        style = self._style()
        ratio = pipeline.RATIOS[self._ratio_name()]
        gaps: tuple[Rect, ...] = ()
        aspects = self._aspects()
        if aspects is not None:
            try:
                solved = pipeline.composite_rects(aspects, ratio, style)
                gaps = tuple(Rect(*gap) for gap in solved.gaps)
            except ValueError:
                # No arrangement fits these shapes at this ratio. The outer
                # border is still true, so it is still drawn.
                gaps = ()
        self.previews.set_border_preview(
            BorderPreview(
                aspect=ratio.width / ratio.height,
                border=style.border_percent / 100,
                colour=style.border_colour,
                gaps=gaps,
                gap_colour=style.gutter_colour,
            )
        )

    def _discard_stale_preview(self) -> None:
        """Drop a render that the settings have moved on from.

        A composed preview has the border and the gaps rendered into it, so
        the moment either changes the image on the table is a picture of
        settings nobody has any more. Dropping it puts the empty frame and
        the live overlay back, and those do agree with the rail.

        Called from the handlers for the things that make a render stale --
        the style, the ratio, the sources -- and deliberately not from
        `_refresh_border_preview`, which also runs when a background solve
        lands. A solve landing is new information about the settings in
        force, not a change to them, and clearing there would pull a
        just-rendered preview off the table.

        The note goes in the hint rather than the status line: the status
        line is the live sentence describing the composite, and the solve
        that a style change kicks off rewrites it as soon as it lands.
        """
        if self.previews.clear_images():
            self._set_hint(shell.STALE_PREVIEW)

    @property
    def status(self) -> str:
        return self.status_label.text()

    @property
    def hint(self) -> str:
        return self.hint_label.text()

    @property
    def layout_name(self) -> str:
        return self.layout_label.text()

    def _set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def _set_hint(self, text: str, *, error: bool = False) -> None:
        self.hint_label.setText(text)
        self._restyle(self.hint_label, "Error" if error else "Help")

    @staticmethod
    def _restyle(label: QLabel, name: str) -> None:
        """Swap a label between voices. Qt only re-reads the stylesheet for a
        widget whose object name changed if it is told to."""
        if label.objectName() == name:
            return
        label.setObjectName(name)
        style = label.style()
        style.unpolish(label)
        style.polish(label)

    def _apply_button_states(self) -> None:
        """The single place that decides which buttons are pressable.

        Every rule the interface used to report in a modal is enforced here
        instead: Add stops at MAX_IMAGES, Save and Preview need a composable
        set, and the reorder buttons need something selected to act on.
        Called from construction and from everything that changes the list
        or the selection, so it can never be out of date.
        """
        count = len(self.images)
        self.add_btn.setEnabled(count < MAX_IMAGES)

        index = self._selection
        has_selection = index is not None and 0 <= index < count
        self.remove_btn.setEnabled(has_selection)
        self.up_btn.setEnabled(has_selection and index != 0)
        self.down_btn.setEnabled(has_selection and index != count - 1)

        self._set_buttons_enabled(self.can_compose())
        self.save_btn.setText(_save_label(count))
        # Why Save is disabled belongs to the status line, which is already
        # the sentence describing what the current set makes. Saying it in
        # the hint as well printed two near-identical sentences one above
        # the other, which reads as a rendering fault rather than as help.
        self._set_hint("")

    def _set_buttons_enabled(self, enabled: bool) -> None:
        self.preview_btn.setEnabled(enabled)
        self.save_btn.setEnabled(enabled)

    def _update_status(self) -> None:
        """State the consequence: what this makes, how it is arranged, at
        what ratio. The arrangement only appears once the solver has
        actually returned one -- never a guess."""
        count = len(self.images)
        noun = _composite_noun(count)
        if not noun:
            # One voice: the status line says what is missing, so the hint
            # under it stays free for things the user has to act on.
            self._set_status(ONE_MORE if count == 1 else EMPTY_STATE)
            self._set_band(self._subject, "")
            return
        arrangement = present_layout(self._solved, count).lower()
        parts = (
            [noun, arrangement, self._bare_ratio()] if arrangement else [noun, self._bare_ratio()]
        )
        self._set_status(", ".join(parts))
        self._set_band(self._subject, f"{self._bare_ratio()} · {noun.lower()}")

    # --- the live solve -----------------------------------------------------

    def _request_layout_name(self) -> None:
        """Ask, off the GUI thread, how these sources will be arranged.

        `name_layout` opens files, so it must not run here. The token makes
        the answer discardable: add a third image while a two-image solve is
        in flight and the older reply is dropped instead of overwriting the
        newer one.
        """
        self._solve_token += 1
        self._solved = ""
        self.layout_label.setText("")
        self._update_status()

        sources = list(self.images)
        # The sizes shown in the list are wanted whether or not the set is
        # composable yet -- one source still has dimensions worth showing.
        if not sources:
            return
        token = self._solve_token
        ratio_name = self._ratio_name()
        style = self._style()
        submit(
            lambda: _solve_job(token, sources, ratio_name, style),
            self._apply_layout_name,
            self._solve_failed,
        )

    def _solve_failed(self, _error: BaseException) -> None:
        """A solve that blew up has no name to show, and nothing to say: the
        rail simply stays empty rather than reporting an internal fault."""
        return

    def _apply_layout_name(self, solved: _Solve) -> None:
        """Runs on the GUI thread. Late answers are dropped, not shown."""
        if solved.token != self._solve_token:
            return
        self._solved = solved.name
        self.layout_label.setText(present_layout(solved.name, solved.count))
        self._update_status()
        if solved.sizes and not solved.sizes.items() <= self._sizes.items():
            self._sizes.update(solved.sizes)
            # Redraw the rows now the dimensions are known. Straight to the
            # widget, not through _refresh_list, which would start another
            # solve and loop.
            self.listbox.set_items(self._rows())
        # The gaps can only be solved once every source's shape is known,
        # which is exactly what has just arrived.
        self._refresh_border_preview()

    # --- the list -----------------------------------------------------------

    def _rows(self) -> list[Source]:
        return [Source(path=path, size=self._sizes.get(path)) for path in self.images]

    def _refresh_list(self) -> None:
        # Sizes may be unknown until the worker reports; a row renders
        # without them rather than waiting.
        self.listbox.set_items(self._rows())
        # The band counts what is loaded here, since no single filename
        # describes a composite.
        count = len(self.images)
        self._set_band(f"{count} sources" if count else "", self._detail)
        self._request_layout_name()
        self._apply_button_states()
        # The set of sources decides the arrangement, and so the gaps.
        self._refresh_border_preview()
        # A composite of a set of sources that has changed is stale as well.
        self._discard_stale_preview()
        # The output prefix is derived from the first image. If the field
        # still holds that derived value -- i.e. the user hasn't typed their
        # own -- re-derive it from the current first image, so add A, add B,
        # remove A, Save no longer writes next to A's now-absent name.
        if self.output_row.text() != self._derived_prefix:
            return
        derived = str(Path(self.images[0]).with_suffix("")) + "_composite" if self.images else ""
        if derived != self.output_row.text():
            self.output_row.setText(derived)
        self._derived_prefix = derived

    def _on_select(self, index: object) -> None:
        self._selection = index if isinstance(index, int) else None
        self._apply_button_states()

    def add_image(self) -> None:
        # The Add button is disabled at MAX_IMAGES, so this guard is a safety
        # net for programmatic callers, not something a user can reach.
        if len(self.images) >= MAX_IMAGES:
            return
        chosen, _filter = QFileDialog.getOpenFileNames(self, "Choose sources", "", IMAGE_FILTER)
        if not chosen:
            return
        self._accept(list(chosen))

    def _accept(self, chosen: Sequence[str]) -> None:
        """Take as many of the chosen files as there is room for.

        The dialog lets a user pick any number, so pick five for a triptych
        and three arrive rather than the whole selection being refused. The
        surplus is named in the hint: silently dropping files the user
        explicitly selected would be worse than the modal this replaced.
        """
        room = MAX_IMAGES - len(self.images)
        self.images.extend(chosen[:room])
        self._refresh_list()
        surplus = chosen[room:]
        if surplus:
            names = ", ".join(Path(path).name for path in surplus)
            self._set_hint(f"A composite takes at most {MAX_IMAGES}. Left out {names}.")

    def _swap(self, first: int, second: int) -> None:
        self.images[first], self.images[second] = self.images[second], self.images[first]

    def move_up(self) -> None:
        index = self._selection
        if index is None or index == 0:
            return
        self._swap(index, index - 1)
        self._refresh_list()
        # The moved source stays selected, so a second press keeps moving
        # the same one rather than whatever landed under the cursor.
        self.listbox.select(index - 1)

    def move_down(self) -> None:
        index = self._selection
        if index is None or index >= len(self.images) - 1:
            return
        self._swap(index, index + 1)
        self._refresh_list()
        self.listbox.select(index + 1)

    def remove(self) -> None:
        index = self._selection
        if index is None or index >= len(self.images):
            return
        del self.images[index]
        self._refresh_list()
        # `set_items` clamps or clears the selection for us; take whatever it
        # settled on rather than second-guessing it.
        self._selection = self.listbox.selected_index
        self._apply_button_states()

    def browse_output(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select output folder")
        if folder:
            self.output_row.setText(str(Path(folder) / "composite"))

    # --- writing and previewing ---------------------------------------------

    def save(self) -> None:
        # Save is disabled unless this holds; the guard is a safety net.
        if not self.can_compose():
            return
        prefix = self.output_row.text()
        if not prefix:
            self._set_hint(NO_PREFIX, error=True)
            return
        ratio = pipeline.RATIOS[self._ratio_name()]
        style = self._style()
        sources = list(self.images)
        self._set_buttons_enabled(False)
        self._set_status(WORKING)

        def job() -> _Composed:
            result = pipeline.compose_images(sources, prefix, ratio, style)
            return _Composed(result.path, result.layout_name, ratio.name)

        submit(job, self._finish, self._failed)

    def preview(self) -> None:
        # Preview is disabled unless this holds; the guard is a safety net.
        if not self.can_compose():
            return
        ratio = pipeline.RATIOS[self._ratio_name()]
        style = self._style()
        sources = list(self.images)
        self._set_buttons_enabled(False)
        self._set_status(WORKING)

        def job() -> _Previewed:
            image, layout_name = pipeline.compose_preview(sources, ratio, style)
            return _Previewed(image, layout_name, ratio.name, len(sources))

        submit(job, self._finish_preview, self._failed)

    def _failed(self, error: BaseException) -> None:
        """One failure path for both actions. Inline, never modal."""
        self._set_status(f"Could not compose — {error}")
        self._apply_button_states()
        self._set_hint(str(error), error=True)

    def _finish(self, composed: _Composed) -> None:
        """Runs on the GUI thread once Save's job returns.

        The layout name travels separately from the status message so the
        pane title can stand on its own under the image.
        """
        self._set_status(
            f"Saved {composed.path.name} — {composed.layout_name}, {composed.ratio_name}"
        )
        try:
            self.previews.set_frames([composed.layout_name])
            self.previews.show_paths([composed.path])
        finally:
            self._apply_button_states()

    def _finish_preview(self, previewed: _Previewed) -> None:
        """Runs on the GUI thread once Preview's job returns.

        Unlike `_finish` there is no file to reload -- the rendered image
        travels back as plain data and is shown directly, without ever
        touching disk. The status line goes back to the resting sentence,
        because the preview is on screen and a past-tense narration of it
        would be noise; the arrangement is named in the stencil under the
        frame instead.
        """
        arrangement = present_layout(previewed.layout_name, previewed.count).lower()
        self._set_status(
            f"{_composite_noun(previewed.count)}, {arrangement}, {previewed.ratio_name}"
        )
        try:
            self.previews.set_frames([previewed.layout_name])
            self.previews.show_images([previewed.image])
        finally:
            self._apply_button_states()

    def _on_ratio_change(self, _index: int = 0) -> None:
        # A new ratio is a new frame shape, so anything already rendered is
        # a picture of the old one.
        self._discard_stale_preview()
        self._request_layout_name()
        self._refresh_border_preview()
