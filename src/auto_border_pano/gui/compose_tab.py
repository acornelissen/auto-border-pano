"""The diptych and triptych tab.

Pick two or three images, choose a target ratio, and the arrangement is
solved automatically from the images' own shapes.
"""

import contextlib
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

from PIL import Image

from auto_border_pano import pipeline
from auto_border_pano.gui import shell, theme, tooltip
from auto_border_pano.gui.sources import Source, SourcesList
from auto_border_pano.gui.strip import ContactStrip

MIN_IMAGES = 2
MAX_IMAGES = 3

EMPTY_STATE = "Add two sources for a diptych, three for a triptych."
ONE_MORE = "Add one more source."
NO_PREFIX = "Choose where the composite should go."
ORDER_HINT = "Left to right, in this order."

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


class ComposeTab:
    def __init__(self, parent: tk.Misc) -> None:
        self.root = parent
        self.columns = shell.TwoColumn(parent)
        self.frame = self.columns.frame
        self.images: list[str] = []
        self._selection: int | None = None
        # Tracks the last prefix this class itself derived from the first
        # image, so _refresh_list can tell "the user hasn't touched this
        # field" apart from "the user typed their own prefix" and only
        # overwrite the former.
        self._derived_prefix: str = ""

        self.output_path = tk.StringVar()
        self.ratio = tk.StringVar(value=pipeline.DEFAULT_RATIO.display)
        self.status = tk.StringVar(value=EMPTY_STATE)
        self.hint = tk.StringVar(value="")
        self.layout_name = tk.StringVar(value="")
        # What the rebate band should stencil while this tab is in front:
        # what is loaded, and what this tab will make of it. The band belongs
        # to the shell, not to either tab, so each tab just states these and
        # the shell decides whose to show.
        self.subject = tk.StringVar()
        self.detail = tk.StringVar()

        # The arrangement the solver last returned for the current list and
        # ratio, and the token of the request that produced it. Every solve
        # is stamped with a token so a slow two-image solve landing after a
        # third image was added cannot overwrite the newer answer.
        self._solved: str = ""
        self._solve_token = 0
        # Pixel sizes by path, filled in by the solve worker below. Cached
        # because the same source is re-listed on every add, remove and
        # reorder, and re-reading its header each time would be wasteful.
        self._sizes: dict[str, tuple[int, int]] = {}

        self._build_ui()

    def can_compose(self) -> bool:
        return MIN_IMAGES <= len(self.images) <= MAX_IMAGES

    def _build_ui(self) -> None:
        # The rail reads top to bottom as a sentence -- these sources, at
        # this format, to here, go -- and in the same order as the Split
        # tab's rail, so switching tabs no longer re-lays-out the window.
        rail = self.columns.rail

        shell.section(rail, "Sources", row=0)

        # Numbered rows in the contact strip's own visual language, because
        # the number *is* the arrangement: reordering here moves a numbered
        # frame there. The tk.Listbox this replaces was a black rectangle
        # with a sunken border among ttk widgets, and said nothing about the
        # one thing that matters -- that the order is the composite's order.
        self.listbox = SourcesList(rail, on_select=self._on_select)
        self.listbox.canvas.grid(row=1, column=0, sticky=(tk.W, tk.E))

        # A row under the list rather than a column beside it: the list is
        # the subject, the four controls act on it. Add is a different kind
        # of action from the other three -- it grows the list, they act on
        # whichever row is selected -- so it sits alone at the left edge and
        # they cluster at the right, and the gap between them says so.
        buttons = ttk.Frame(rail)
        buttons.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=(theme.SPACE_S, 0))
        self.add_btn = ttk.Button(buttons, text="+ Add", command=self.add_image)
        self.add_btn.pack(side="left")
        # Packed right to left so the three read, left to right, as up, down
        # and remove while staying flush with the rail's right edge.
        self.remove_btn = ttk.Button(buttons, text="×", width=3, command=self.remove)  # noqa: RUF001
        self.remove_btn.pack(side="right")
        self.down_btn = ttk.Button(buttons, text="↓", width=3, command=self.move_down)
        self.down_btn.pack(side="right", padx=(0, theme.SPACE_S))
        self.up_btn = ttk.Button(buttons, text="↑", width=3, command=self.move_up)
        self.up_btn.pack(side="right", padx=(0, theme.SPACE_S))

        # These three are glyphs, so the tooltip is their only name. It shows
        # on focus as well as hover, which is what keeps them reachable
        # without a pointer.
        tooltip.attach(self.up_btn, "Move earlier")
        tooltip.attach(self.down_btn, "Move later")
        tooltip.attach(self.remove_btn, "Remove")

        ttk.Label(rail, text=ORDER_HINT, style="Help.TLabel", wraplength=shell.RAIL_WIDTH).grid(
            row=3, column=0, sticky=tk.W, pady=(theme.SPACE_S, 0)
        )

        shell.section(rail, "Format", row=4)
        self.ratio_combo = ttk.Combobox(
            rail,
            textvariable=self.ratio,
            values=[r.display for r in pipeline.RATIOS.values()],
            state="readonly",
        )
        self.ratio_combo.grid(row=5, column=0, sticky=(tk.W, tk.E))
        self.ratio_combo.bind("<<ComboboxSelected>>", self._on_ratio_change)

        # The consequence of the ratio, stated before the user commits to it.
        ttk.Label(rail, textvariable=self.layout_name, style="Help.TLabel").grid(
            row=6, column=0, sticky=tk.W, pady=(theme.SPACE_S, 0)
        )

        shell.section(rail, "Destination", row=7)
        output_row = ttk.Frame(rail)
        output_row.grid(row=8, column=0, sticky=(tk.W, tk.E))
        output_row.columnconfigure(0, weight=1)
        # Field and button side by side, exactly as the Split tab builds its
        # own output row. The two rails are one product; a destination that
        # is laid out one way here and another way there is the most visible
        # way for them to drift apart.
        self.output_entry = shell.path_entry(output_row, self.output_path)
        ttk.Button(output_row, text="Choose folder", command=self.browse_output).grid(
            row=0, column=1, padx=(theme.SPACE_S, 0)
        )

        self.save_btn = ttk.Button(
            rail, text="Save composite", command=self.save, style="Primary.TButton"
        )
        self.save_btn.grid(row=9, column=0, sticky=(tk.W, tk.E), pady=(theme.SPACE_L, 0))

        # Preview is free and reversible, so it sits below the action that
        # writes to disk at text weight rather than beside it as a peer.
        # Hard against Save it read as a caption on the button; the same
        # step the Split tab puts between its primary button and the line
        # under it separates the two actions.
        self.preview_btn = ttk.Button(
            rail, text="Preview", command=self.preview, style="Link.TButton"
        )
        self.preview_btn.grid(row=10, column=0, sticky=tk.W, pady=(theme.SPACE_M, 0))

        # The resting sentence: what this makes, how it is arranged, at what
        # ratio -- the same slot the Split tab gives its status line.
        ttk.Label(
            rail, textvariable=self.status, style="Help.TLabel", wraplength=shell.RAIL_WIDTH
        ).grid(row=11, column=0, sticky=tk.W, pady=(theme.SPACE_M, 0))

        # Only ever a reason to act on: a file that would not compose, a
        # missing prefix, sources left out. The status line above carries
        # everything else, so the two can never read as competing sentences.
        self.hint_label = ttk.Label(
            rail, textvariable=self.hint, style="Help.TLabel", wraplength=shell.RAIL_WIDTH
        )
        self.hint_label.grid(row=12, column=0, sticky=tk.W, pady=(theme.SPACE_S, 0))
        rail.rowconfigure(13, weight=1)

        # One frame, not four: a composite is a single image. The strip
        # still renders its unexposed state before anything is composed.
        self.previews = ContactStrip(self.columns.table, frames=1)
        # Top of the table, at its natural height: the strip is an object
        # lying on the light table, not a panel filling it.
        self.previews.canvas.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N))

        self._refresh_list()

    def _bare_ratio(self) -> str:
        """The ratio as the user reads it, e.g. '4:5' -- never the display form."""
        name = _RATIO_BY_DISPLAY.get(self.ratio.get(), pipeline.DEFAULT_RATIO.name)
        return pipeline.RATIOS[name].name

    def _set_hint(self, text: str, *, error: bool = False) -> None:
        self.hint.set(text)
        self.hint_label.configure(style="Error.TLabel" if error else "Help.TLabel")

    def _apply_button_states(self) -> None:
        """The single place that decides which buttons are pressable.

        Every rule the interface used to report in a modal is enforced here
        instead: Add stops at MAX_IMAGES, Save and Preview need a composable
        set, and the reorder buttons need something selected to act on.
        """
        count = len(self.images)
        self.add_btn.config(state="normal" if count < MAX_IMAGES else "disabled")

        index = self._selection
        has_selection = index is not None and 0 <= index < count
        self.remove_btn.config(state="normal" if has_selection else "disabled")
        self.up_btn.config(state="normal" if has_selection and index != 0 else "disabled")
        self.down_btn.config(state="normal" if has_selection and index != count - 1 else "disabled")

        self._set_buttons_state("normal" if self.can_compose() else "disabled")
        self.save_btn.config(text=_save_label(count))
        # Why Save is disabled belongs to the status line, which is already
        # the sentence describing what the current set makes. Saying it in
        # the hint as well printed two near-identical sentences one above
        # the other, which reads as a rendering fault rather than as help.
        self._set_hint("")

    def _update_status(self) -> None:
        """State the consequence: what this makes, how it is arranged, at
        what ratio. The arrangement only appears once the solver has
        actually returned one -- never a guess."""
        count = len(self.images)
        noun = _composite_noun(count)
        if not noun:
            # One voice: the status line says what is missing, so the hint
            # under it stays free for things the user has to act on.
            self.status.set(ONE_MORE if count == 1 else EMPTY_STATE)
            self.detail.set("")
            return
        arrangement = present_layout(self._solved, count).lower()
        parts = (
            [noun, arrangement, self._bare_ratio()] if arrangement else [noun, self._bare_ratio()]
        )
        self.status.set(", ".join(parts))
        self.detail.set(f"{self._bare_ratio()} · {noun.lower()}")

    def _request_layout_name(self) -> None:
        """Ask, off the main thread, how these sources will be arranged.

        Reads every piece of tk state here on the main thread and hands the
        worker plain strings; `name_layout` opens files, so it must not run
        here. The token makes the answer discardable: add a third image
        while a two-image solve is in flight and the older reply is dropped
        instead of overwriting the newer one.
        """
        self._solve_token += 1
        self._solved = ""
        self.layout_name.set("")
        self._update_status()

        sources = list(self.images)
        # The sizes shown in the list are wanted whether or not the set is
        # composable yet -- one source still has dimensions worth showing.
        if not sources:
            return
        threading.Thread(
            target=self._run_name_layout,
            args=(self._solve_token, sources, self._bare_ratio()),
            daemon=True,
        ).start()

    def _run_name_layout(self, token: int, sources: list[str], ratio_name: str) -> None:
        """Worker. Touches no tk object; reports back through root.after."""
        sizes: dict[str, tuple[int, int]] = {}
        for source in sources:
            # Header reads only, and one unreadable file must not cost the
            # others their dimensions.
            with contextlib.suppress(OSError):
                facts = pipeline.inspect_source(source)
                sizes[source] = (facts.width, facts.height)
        try:
            name = pipeline.name_layout(sources, pipeline.RATIOS[ratio_name])
        except (ValueError, OSError):
            # A count the solver cannot arrange, or a file it cannot read.
            # Either way there is no name to show, and showing a stale or
            # guessed one would be worse than showing nothing.
            name = ""
        # Scheduling is the only crossing back; if the window closed while
        # the solve was in flight there is nothing left to tell.
        # RuntimeError as well as TclError: Tk raises the former when the
        # interpreter has no main loop left to schedule onto.
        with contextlib.suppress(tk.TclError, RuntimeError):
            self.root.after(0, self._apply_layout_name, token, name, len(sources), sizes)

    def _apply_layout_name(
        self, token: int, name: str, count: int, sizes: dict[str, tuple[int, int]]
    ) -> None:
        """Runs on the main thread. Late answers are dropped, not shown."""
        if token != self._solve_token:
            return
        self._solved = name
        self.layout_name.set(present_layout(name, count))
        self._update_status()
        if sizes and not sizes.items() <= self._sizes.items():
            self._sizes.update(sizes)
            # Redraw the rows now the dimensions are known. Straight to the
            # widget, not through _refresh_list, which would start another
            # solve and loop.
            self.listbox.set_items(
                [Source(path=path, size=self._sizes.get(path)) for path in self.images]
            )

    def _on_ratio_change(self, _event: object = None) -> None:
        self._request_layout_name()

    def _refresh_list(self) -> None:
        # Sizes may be unknown until the worker below reports; a row renders
        # without them rather than waiting.
        self.listbox.set_items(
            [Source(path=path, size=self._sizes.get(path)) for path in self.images]
        )
        # The band counts what is loaded here, since no single filename
        # describes a composite.
        count = len(self.images)
        self.subject.set(f"{count} sources" if count else "")
        self._request_layout_name()
        self._apply_button_states()
        # The output prefix is derived from the first image. If the field
        # still holds that derived value -- i.e. the user hasn't typed their
        # own -- re-derive it from the current first image, so add A, add B,
        # remove A, Save no longer writes next to A's now-absent name.
        if self.output_path.get() != self._derived_prefix:
            return
        derived = str(Path(self.images[0]).with_suffix("")) + "_composite" if self.images else ""
        if derived != self.output_path.get():
            self.output_path.set(derived)
        self._derived_prefix = derived

    def _on_select(self, index: int | None) -> None:
        self._selection = index
        self._apply_button_states()

    def add_image(self) -> None:
        # The Add button is disabled at MAX_IMAGES, so this guard is a safety
        # net for programmatic callers, not something a user can reach.
        if len(self.images) >= MAX_IMAGES:
            return
        chosen = filedialog.askopenfilenames(
            title="Choose sources",
            filetypes=[("Image files", "*.jpg *.jpeg *.JPG *.JPEG"), ("All files", "*.*")],
        )
        if not chosen:
            return
        self._accept(list(chosen))

    def _accept(self, chosen: list[str]) -> None:
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
        folder = filedialog.askdirectory(title="Select Output Folder")
        if folder:
            self.output_path.set(str(Path(folder) / "composite"))

    def _set_buttons_state(self, state: str) -> None:
        self.preview_btn.config(state=state)
        self.save_btn.config(state=state)

    def _finish(
        self, message: str, path: str | None, error: str | None, layout_name: str = ""
    ) -> None:
        """Runs on the main thread once Save's worker reports back.

        All widget mutation happens here, never on the worker thread. The
        layout name travels separately from the status message so the pane
        title can stand on its own under the image.
        """
        self.status.set(message)
        try:
            if path is not None:
                self.previews.set_frames([layout_name])
                with Image.open(path) as img:
                    self.previews.show_images([img.copy()])
        finally:
            self._apply_button_states()
        if error is not None:
            self._set_hint(error, error=True)

    def _finish_preview(
        self,
        message: str,
        image: Image.Image | None,
        error: str | None,
        layout_name: str = "",
    ) -> None:
        """Runs on the main thread once Preview's worker reports back.

        Unlike `_finish`, there is no file to reload -- the rendered image
        travels back as plain data through `root.after` and is shown
        directly, without ever touching disk.

        The layout name arrives as its own argument rather than being read
        back out of `message`. The two carry different things: the stencil
        under the frame names the arrangement, and the status line stays on
        the resting sentence, so nothing has to parse a sentence to find a
        noun.
        """
        self.status.set(message)
        try:
            if image is not None:
                self.previews.set_frames([layout_name])
                self.previews.show_images([image])
        finally:
            self._apply_button_states()
        if error is not None:
            self._set_hint(error, error=True)

    def _run_compose(self, sources: list[str], prefix: str, ratio_name: str) -> None:
        try:
            ratio = pipeline.RATIOS[ratio_name]
            result = pipeline.compose_images(sources, prefix, ratio)
        except Exception as error:
            self.root.after(0, self._finish, f"Could not compose — {error}", None, str(error))
            return
        self.root.after(
            0,
            self._finish,
            f"Saved {result.path.name} — {result.layout_name}, {ratio.name}",
            str(result.path),
            None,
            result.layout_name,
        )

    def _run_preview(self, sources: list[str], ratio_name: str) -> None:
        ratio = pipeline.RATIOS[ratio_name]
        try:
            image, layout_name = pipeline.compose_preview(sources, ratio)
        except Exception as error:
            self.root.after(
                0, self._finish_preview, f"Could not compose — {error}", None, str(error)
            )
            return
        # The status line goes back to the resting sentence -- the preview
        # is on screen, so a past-tense narration of it would be noise. The
        # arrangement is named in the stencil under the frame instead.
        arrangement = present_layout(layout_name, len(sources)).lower()
        resting = f"{_composite_noun(len(sources))}, {arrangement}, {ratio.name}"
        self.root.after(0, self._finish_preview, resting, image, None, layout_name)

    def save(self) -> None:
        # Save is disabled unless this holds; the guard is a safety net.
        if not self.can_compose():
            return
        prefix = self.output_path.get()
        if not prefix:
            self._set_hint(NO_PREFIX, error=True)
            return
        ratio_name = _RATIO_BY_DISPLAY.get(self.ratio.get(), pipeline.DEFAULT_RATIO.name)
        sources = list(self.images)
        self._set_buttons_state("disabled")
        self.status.set("Composing")
        threading.Thread(
            target=self._run_compose, args=(sources, prefix, ratio_name), daemon=True
        ).start()

    def preview(self) -> None:
        # Preview is disabled unless this holds; the guard is a safety net.
        if not self.can_compose():
            return
        ratio_name = _RATIO_BY_DISPLAY.get(self.ratio.get(), pipeline.DEFAULT_RATIO.name)
        sources = list(self.images)
        self._set_buttons_state("disabled")
        self.status.set("Composing")
        threading.Thread(target=self._run_preview, args=(sources, ratio_name), daemon=True).start()
