"""The diptych and triptych tab.

Pick two or three images, choose a target ratio, and the arrangement is
solved automatically from the images' own shapes.
"""

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

from PIL import Image

from auto_border_pano import pipeline
from auto_border_pano.gui import theme
from auto_border_pano.gui.preview import PreviewPanes

MIN_IMAGES = 2
MAX_IMAGES = 3

EMPTY_STATE = "Add two negatives for a diptych, three for a triptych."
ONE_MORE = "Add one more negative."
NO_PREFIX = "Choose where the composite should go."
ORDER_HINT = "Left to right, in this order."

_RATIO_BY_DISPLAY: dict[str, str] = {r.display: r.name for r in pipeline.RATIOS.values()}


def _composite_noun(count: int) -> str:
    """What this many negatives makes. Empty when it makes nothing yet."""
    if count == MIN_IMAGES:
        return "Diptych"
    if count == MAX_IMAGES:
        return "Triptych"
    return ""


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
        self.frame = ttk.Frame(parent, padding=theme.SPACE_L)
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
        self.hint = tk.StringVar(value=EMPTY_STATE)

        self._build_ui()

    def can_compose(self) -> bool:
        return MIN_IMAGES <= len(self.images) <= MAX_IMAGES

    def _build_ui(self) -> None:
        self.frame.columnconfigure(0, weight=1)

        ttk.Label(self.frame, text="NEGATIVES", style="Section.TLabel").grid(
            row=0, column=0, sticky=tk.W
        )

        listbox_row = ttk.Frame(self.frame)
        listbox_row.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=theme.SPACE_M)
        listbox_row.columnconfigure(0, weight=1)

        # A raw Tk widget: ttk.Style cannot reach it, so the theme tokens are
        # applied by hand until Stage 5 replaces it outright.
        self.listbox = tk.Listbox(
            listbox_row,
            height=4,
            background=theme.LIGHTBOX,
            foreground=theme.REBATE,
            selectbackground=theme.CHINAGRAPH,
            selectforeground=theme.LIGHTBOX,
            borderwidth=0,
            highlightthickness=1,
            highlightbackground=theme.SPROCKET,
            highlightcolor=theme.CHINAGRAPH,
            activestyle="none",
            font=theme.font(listbox_row, "data"),
        )
        self.listbox.grid(row=0, column=0, sticky=(tk.W, tk.E))
        self.listbox.bind("<<ListboxSelect>>", self._on_select)

        buttons = ttk.Frame(listbox_row)
        buttons.grid(row=0, column=1, padx=theme.SPACE_S)
        self.add_btn = ttk.Button(buttons, text="+ Add", command=self.add_image)
        self.add_btn.pack(fill="x")
        self.up_btn = ttk.Button(buttons, text="↑", command=self.move_up)
        self.up_btn.pack(fill="x")
        self.down_btn = ttk.Button(buttons, text="↓", command=self.move_down)
        self.down_btn.pack(fill="x")
        self.remove_btn = ttk.Button(buttons, text="×", command=self.remove)  # noqa: RUF001
        self.remove_btn.pack(fill="x")

        ttk.Label(self.frame, text=ORDER_HINT, style="Help.TLabel").grid(
            row=2, column=0, sticky=tk.W
        )

        ratio_row = ttk.Frame(self.frame)
        ratio_row.grid(row=3, column=0, sticky=tk.W, pady=theme.SPACE_M)
        ttk.Label(ratio_row, text="Aspect ratio:").pack(side="left")
        self.ratio_combo = ttk.Combobox(
            ratio_row,
            textvariable=self.ratio,
            values=[r.display for r in pipeline.RATIOS.values()],
            state="readonly",
            width=18,
        )
        self.ratio_combo.pack(side="left", padx=theme.SPACE_S)

        output_row = ttk.Frame(self.frame)
        output_row.grid(row=4, column=0, sticky=(tk.W, tk.E), pady=theme.SPACE_M)
        output_row.columnconfigure(1, weight=1)
        ttk.Label(output_row, text="Output:").grid(row=0, column=0)
        ttk.Entry(output_row, textvariable=self.output_path, style="TEntry").grid(
            row=0, column=1, sticky=(tk.W, tk.E), padx=theme.SPACE_S
        )
        ttk.Button(output_row, text="Browse", command=self.browse_output).grid(row=0, column=2)

        action_row = ttk.Frame(self.frame)
        action_row.grid(row=5, column=0, pady=theme.SPACE_L)
        self.preview_btn = ttk.Button(
            action_row, text="Preview", command=self.preview, style="Link.TButton"
        )
        self.preview_btn.pack(side="left", padx=theme.SPACE_S)
        self.save_btn = ttk.Button(
            action_row, text="Save composite", command=self.save, style="Primary.TButton"
        )
        self.save_btn.pack(side="left", padx=theme.SPACE_S)

        # Why the disabled buttons are disabled, and what to do about it.
        self.hint_label = ttk.Label(self.frame, textvariable=self.hint, style="Help.TLabel")
        self.hint_label.grid(row=6, column=0, sticky=tk.W)

        ttk.Label(self.frame, textvariable=self.status, style="Help.TLabel").grid(
            row=7, column=0, sticky=tk.W
        )

        self.previews = PreviewPanes(self.frame, "Composite")
        self.previews.frame.grid(
            row=8, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=theme.SPACE_M
        )
        self.frame.rowconfigure(8, weight=1)

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

        ready = self.can_compose()
        self._set_buttons_state("normal" if ready else "disabled")
        self.save_btn.config(text=_save_label(count))
        if ready:
            self._set_hint("")
        else:
            self._set_hint(ONE_MORE if count == MIN_IMAGES - 1 else EMPTY_STATE)

    def _refresh_list(self) -> None:
        self.listbox.delete(0, tk.END)
        for path in self.images:
            self.listbox.insert(tk.END, Path(path).name)
        count = len(self.images)
        noun = _composite_noun(count)
        self.status.set(f"{noun}, {self._bare_ratio()}" if noun else EMPTY_STATE)
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

    def _on_select(self, _event: object) -> None:
        selection: tuple[int, ...] = self.listbox.curselection()  # type: ignore[no-untyped-call]
        self._selection = int(selection[0]) if selection else None
        self._apply_button_states()

    def add_image(self) -> None:
        # The Add button is disabled at MAX_IMAGES, so this guard is a safety
        # net for programmatic callers, not something a user can reach.
        if len(self.images) >= MAX_IMAGES:
            return
        filename = filedialog.askopenfilename(
            title="Select Image",
            filetypes=[("Image files", "*.jpg *.jpeg *.JPG *.JPEG"), ("All files", "*.*")],
        )
        if not filename:
            return
        self.images.append(filename)
        self._refresh_list()

    def _swap(self, first: int, second: int) -> None:
        self.images[first], self.images[second] = self.images[second], self.images[first]

    def move_up(self) -> None:
        index = self._selection
        if index is None or index == 0:
            return
        self._swap(index, index - 1)
        self._selection = index - 1
        self._refresh_list()
        self.listbox.selection_set(self._selection)
        self._apply_button_states()

    def move_down(self) -> None:
        index = self._selection
        if index is None or index >= len(self.images) - 1:
            return
        self._swap(index, index + 1)
        self._selection = index + 1
        self._refresh_list()
        self.listbox.selection_set(self._selection)
        self._apply_button_states()

    def remove(self) -> None:
        index = self._selection
        if index is None or index >= len(self.images):
            return
        del self.images[index]
        self._selection = None
        self._refresh_list()

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
                self.previews.rebuild([layout_name.upper()])
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
                self.previews.rebuild([layout_name.upper()])
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
        resting = f"{_composite_noun(len(sources))}, {ratio.name}"
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
