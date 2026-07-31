"""The diptych and triptych tab.

Pick two or three images, choose a target ratio, and the arrangement is
solved automatically from the images' own shapes.
"""

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image

from auto_border_pano import pipeline
from auto_border_pano.gui import theme
from auto_border_pano.gui.preview import PreviewPanes

MIN_IMAGES = 2
MAX_IMAGES = 3

_RATIO_BY_DISPLAY: dict[str, str] = {r.display: r.name for r in pipeline.RATIOS.values()}


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
        self.status = tk.StringVar(value="Add two or three images")

        self._build_ui()

    def can_compose(self) -> bool:
        return MIN_IMAGES <= len(self.images) <= MAX_IMAGES

    def _build_ui(self) -> None:
        self.frame.columnconfigure(0, weight=1)

        listbox_row = ttk.Frame(self.frame)
        listbox_row.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=theme.SPACE_M)
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
        ttk.Button(buttons, text="Add", command=self.add_image).pack(fill="x")
        ttk.Button(buttons, text="Up", command=self.move_up).pack(fill="x")
        ttk.Button(buttons, text="Down", command=self.move_down).pack(fill="x")
        ttk.Button(buttons, text="Remove", command=self.remove).pack(fill="x")

        ratio_row = ttk.Frame(self.frame)
        ratio_row.grid(row=1, column=0, sticky=tk.W, pady=theme.SPACE_M)
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
        output_row.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=theme.SPACE_M)
        output_row.columnconfigure(1, weight=1)
        ttk.Label(output_row, text="Output:").grid(row=0, column=0)
        ttk.Entry(output_row, textvariable=self.output_path, style="TEntry").grid(
            row=0, column=1, sticky=(tk.W, tk.E), padx=theme.SPACE_S
        )
        ttk.Button(output_row, text="Browse", command=self.browse_output).grid(row=0, column=2)

        action_row = ttk.Frame(self.frame)
        action_row.grid(row=3, column=0, pady=theme.SPACE_L)
        self.preview_btn = ttk.Button(
            action_row, text="Preview", command=self.preview, style="Link.TButton"
        )
        self.preview_btn.pack(side="left", padx=theme.SPACE_S)
        self.save_btn = ttk.Button(
            action_row, text="Save", command=self.save, style="Primary.TButton"
        )
        self.save_btn.pack(side="left", padx=theme.SPACE_S)

        ttk.Label(self.frame, textvariable=self.status, style="Help.TLabel").grid(
            row=4, column=0, sticky=tk.W
        )

        self.previews = PreviewPanes(self.frame, "Composite")
        self.previews.frame.grid(
            row=5, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=theme.SPACE_M
        )
        self.frame.rowconfigure(5, weight=1)

    def _refresh_list(self) -> None:
        self.listbox.delete(0, tk.END)
        for path in self.images:
            self.listbox.insert(tk.END, Path(path).name)
        self.status.set(
            f"{len(self.images)} image(s)" if self.can_compose() else "Add two or three images"
        )
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

    def add_image(self) -> None:
        if len(self.images) >= MAX_IMAGES:
            messagebox.showinfo("Limit", f"At most {MAX_IMAGES} images")
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

    def move_down(self) -> None:
        index = self._selection
        if index is None or index >= len(self.images) - 1:
            return
        self._swap(index, index + 1)
        self._selection = index + 1
        self._refresh_list()
        self.listbox.selection_set(self._selection)

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

    def _finish(self, message: str, path: str | None, error: str | None) -> None:
        """Runs on the main thread once Save's worker reports back.

        All widget mutation happens here, never on the worker thread.
        """
        self.status.set(message)
        try:
            if path is not None:
                self.previews.rebuild(["Composite"])
                with Image.open(path) as img:
                    self.previews.show_images([img.copy()])
        finally:
            self._set_buttons_state("normal")
        if error is not None:
            messagebox.showerror("Error", error)
        else:
            messagebox.showinfo("Success", message)

    def _finish_preview(self, message: str, image: Image.Image | None, error: str | None) -> None:
        """Runs on the main thread once Preview's worker reports back.

        Unlike `_finish`, there is no file to reload -- the rendered image
        travels back as plain data through `root.after` and is shown
        directly, without ever touching disk.
        """
        self.status.set(message)
        try:
            if image is not None:
                self.previews.rebuild(["Composite"])
                self.previews.show_images([image])
        finally:
            self._set_buttons_state("normal")
        if error is not None:
            messagebox.showerror("Error", error)

    def _run_compose(self, sources: list[str], prefix: str, ratio_name: str) -> None:
        try:
            result = pipeline.compose_images(sources, prefix, pipeline.RATIOS[ratio_name])
        except Exception as error:
            self.root.after(0, self._finish, "Failed", None, str(error))
            return
        self.root.after(
            0,
            self._finish,
            f"Saved {result.path.name} using the {result.layout_name} layout",
            str(result.path),
            None,
        )

    def _run_preview(self, sources: list[str], ratio_name: str) -> None:
        try:
            image, layout_name = pipeline.compose_preview(sources, pipeline.RATIOS[ratio_name])
        except Exception as error:
            self.root.after(0, self._finish_preview, "Failed", None, str(error))
            return
        self.root.after(
            0, self._finish_preview, f"Previewing the {layout_name} layout", image, None
        )

    def save(self) -> None:
        if not self.can_compose():
            messagebox.showerror("Error", f"Select {MIN_IMAGES} or {MAX_IMAGES} images")
            return
        prefix = self.output_path.get()
        if not prefix:
            messagebox.showerror("Error", "Please choose an output prefix")
            return
        ratio_name = _RATIO_BY_DISPLAY.get(self.ratio.get(), pipeline.DEFAULT_RATIO.name)
        sources = list(self.images)
        self._set_buttons_state("disabled")
        self.status.set("Working...")
        threading.Thread(
            target=self._run_compose, args=(sources, prefix, ratio_name), daemon=True
        ).start()

    def preview(self) -> None:
        if not self.can_compose():
            messagebox.showerror("Error", f"Select {MIN_IMAGES} or {MAX_IMAGES} images")
            return
        ratio_name = _RATIO_BY_DISPLAY.get(self.ratio.get(), pipeline.DEFAULT_RATIO.name)
        sources = list(self.images)
        self._set_buttons_state("disabled")
        self.status.set("Working...")
        threading.Thread(target=self._run_preview, args=(sources, ratio_name), daemon=True).start()
