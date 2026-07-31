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
from auto_border_pano.gui.preview import PreviewPanes

MIN_IMAGES = 2
MAX_IMAGES = 3

_RATIO_BY_DISPLAY: dict[str, str] = {r.display: r.name for r in pipeline.RATIOS.values()}


class ComposeTab:
    def __init__(self, parent: tk.Misc) -> None:
        self.root = parent
        self.frame = ttk.Frame(parent, padding="10")
        self.images: list[str] = []
        self._selection: int | None = None

        self.output_path = tk.StringVar()
        self.ratio = tk.StringVar(value=pipeline.DEFAULT_RATIO.display)
        self.status = tk.StringVar(value="Add two or three images")

        self._build_ui()

    def can_compose(self) -> bool:
        return MIN_IMAGES <= len(self.images) <= MAX_IMAGES

    def _build_ui(self) -> None:
        self.frame.columnconfigure(0, weight=1)

        listbox_row = ttk.Frame(self.frame)
        listbox_row.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=5)
        listbox_row.columnconfigure(0, weight=1)

        self.listbox = tk.Listbox(listbox_row, height=4)
        self.listbox.grid(row=0, column=0, sticky=(tk.W, tk.E))
        self.listbox.bind("<<ListboxSelect>>", self._on_select)

        buttons = ttk.Frame(listbox_row)
        buttons.grid(row=0, column=1, padx=5)
        ttk.Button(buttons, text="Add", command=self.add_image).pack(fill="x")
        ttk.Button(buttons, text="Up", command=self.move_up).pack(fill="x")
        ttk.Button(buttons, text="Down", command=self.move_down).pack(fill="x")
        ttk.Button(buttons, text="Remove", command=self.remove).pack(fill="x")

        ratio_row = ttk.Frame(self.frame)
        ratio_row.grid(row=1, column=0, sticky=tk.W, pady=5)
        ttk.Label(ratio_row, text="Aspect ratio:").pack(side="left")
        self.ratio_combo = ttk.Combobox(
            ratio_row,
            textvariable=self.ratio,
            values=[r.display for r in pipeline.RATIOS.values()],
            state="readonly",
            width=18,
        )
        self.ratio_combo.pack(side="left", padx=8)

        output_row = ttk.Frame(self.frame)
        output_row.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=5)
        output_row.columnconfigure(1, weight=1)
        ttk.Label(output_row, text="Output:").grid(row=0, column=0)
        ttk.Entry(output_row, textvariable=self.output_path).grid(
            row=0, column=1, sticky=(tk.W, tk.E), padx=5
        )
        ttk.Button(output_row, text="Browse", command=self.browse_output).grid(row=0, column=2)

        self.compose_btn = ttk.Button(self.frame, text="Compose", command=self.compose)
        self.compose_btn.grid(row=3, column=0, pady=10)

        ttk.Label(self.frame, textvariable=self.status).grid(row=4, column=0, sticky=tk.W)

        self.previews = PreviewPanes(self.frame, "Composite")
        self.previews.frame.grid(row=5, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=10)
        self.frame.rowconfigure(5, weight=1)

    def _refresh_list(self) -> None:
        self.listbox.delete(0, tk.END)
        for path in self.images:
            self.listbox.insert(tk.END, Path(path).name)
        self.status.set(
            f"{len(self.images)} image(s)" if self.can_compose() else "Add two or three images"
        )

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
        if not self.output_path.get():
            self.output_path.set(str(Path(filename).with_suffix("")) + "_composite")
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

    def _finish(self, message: str, path: str | None, error: str | None) -> None:
        """Runs on the main thread. All widget mutation happens here."""
        self.status.set(message)
        try:
            if path is not None:
                self.previews.rebuild(["Composite"])
                with Image.open(path) as img:
                    self.previews.show_images([img.copy()])
        finally:
            self.compose_btn.config(state="normal")
        if error is not None:
            messagebox.showerror("Error", error)
        else:
            messagebox.showinfo("Success", message)

    def _run_compose(self, sources: list[str], prefix: str, ratio_name: str) -> None:
        try:
            result = pipeline.compose_images(sources, prefix, pipeline.RATIOS[ratio_name])
        except Exception as error:
            self.root.after(0, self._finish, "Failed", None, str(error))
            return
        self.root.after(
            0,
            self._finish,
            f"Wrote {result.path.name} using the {result.layout_name} layout",
            str(result.path),
            None,
        )

    def compose(self) -> None:
        if not self.can_compose():
            messagebox.showerror("Error", f"Select {MIN_IMAGES} or {MAX_IMAGES} images")
            return
        prefix = self.output_path.get()
        if not prefix:
            messagebox.showerror("Error", "Please choose an output prefix")
            return
        ratio_name = _RATIO_BY_DISPLAY.get(self.ratio.get(), pipeline.DEFAULT_RATIO.name)
        sources = list(self.images)
        self.compose_btn.config(state="disabled")
        self.status.set("Working...")
        threading.Thread(
            target=self._run_compose, args=(sources, prefix, ratio_name), daemon=True
        ).start()
