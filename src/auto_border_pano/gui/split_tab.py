"""tkinter front end.

Importing this module raises ImportError when tkinter is missing; the
friendly message lives in cli.gui_main.
"""

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from auto_border_pano import pipeline
from auto_border_pano.gui import theme
from auto_border_pano.gui.preview import PreviewPanes

# Built once so process_images can do a plain dict lookup rather than
# scanning pipeline.RATIOS on every run.
_RATIO_BY_DISPLAY: dict[str, str] = {r.display: r.name for r in pipeline.RATIOS.values()}


def preview_titles(count: int) -> list[str]:
    """Labels for the preview panes: the whole panorama plus each detail frame."""
    return ["Whole"] + [f"Detail {n}" for n in range(1, count + 1)]


class PanoramaSplitterGUI:
    def __init__(self, root: tk.Misc) -> None:
        self.root = root

        self.input_path = tk.StringVar()
        self.output_path = tk.StringVar()
        self.is_folder_mode = tk.BooleanVar(value=False)
        self.progress = tk.DoubleVar()
        self.status = tk.StringVar(value="Ready")
        self.ratio = tk.StringVar(value=pipeline.DEFAULT_RATIO.display)

        self._build_ui()

    def _build_ui(self) -> None:
        main = ttk.Frame(self.root, padding=theme.SPACE_L)
        main.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main.columnconfigure(1, weight=1)

        ttk.Label(main, text="Input:").grid(row=0, column=0, sticky=tk.W, pady=theme.SPACE_S)
        ttk.Entry(main, textvariable=self.input_path, width=50, style="TEntry").grid(
            row=0, column=1, sticky=(tk.W, tk.E), padx=theme.SPACE_S
        )
        ttk.Button(main, text="Browse File", command=self.browse_file).grid(
            row=0, column=2, padx=theme.SPACE_S
        )
        ttk.Button(main, text="Browse Folder", command=self.browse_folder).grid(
            row=0, column=3, padx=theme.SPACE_S
        )

        ttk.Label(main, text="Output:").grid(row=1, column=0, sticky=tk.W, pady=theme.SPACE_S)
        ttk.Entry(main, textvariable=self.output_path, width=50, style="TEntry").grid(
            row=1, column=1, sticky=(tk.W, tk.E), padx=theme.SPACE_S
        )
        ttk.Button(main, text="Browse", command=self.browse_output).grid(
            row=1, column=2, padx=theme.SPACE_S
        )

        self.mode_label = ttk.Label(main, text="Mode: Single File")
        self.mode_label.grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=theme.SPACE_M)

        ratio_row = ttk.Frame(main)
        ratio_row.grid(row=3, column=0, columnspan=4, sticky=tk.W, pady=theme.SPACE_S)
        ttk.Label(ratio_row, text="Aspect ratio:").pack(side="left")
        ttk.Combobox(
            ratio_row,
            textvariable=self.ratio,
            values=[r.display for r in pipeline.RATIOS.values()],
            state="readonly",
            width=18,
        ).pack(side="left", padx=theme.SPACE_S)
        ttk.Label(
            ratio_row,
            text="detail frames are derived from this",
            style="Help.TLabel",
        ).pack(side="left")

        self.process_btn = ttk.Button(
            main, text="Process Images", command=self.process_images, style="Primary.TButton"
        )
        self.process_btn.grid(row=4, column=0, columnspan=4, pady=theme.SPACE_L)

        progress_frame = ttk.LabelFrame(main, text="Progress", padding=theme.SPACE_M)
        progress_frame.grid(row=5, column=0, columnspan=4, sticky=(tk.W, tk.E), pady=theme.SPACE_M)
        progress_frame.columnconfigure(0, weight=1)
        ttk.Progressbar(progress_frame, variable=self.progress, maximum=100).grid(
            row=0, column=0, sticky=(tk.W, tk.E), pady=theme.SPACE_S
        )
        ttk.Label(progress_frame, textvariable=self.status, style="Help.TLabel").grid(
            row=1, column=0, sticky=tk.W
        )

        self.previews = PreviewPanes(main, "Preview (Last Processed)")
        self.previews.frame.grid(
            row=6, column=0, columnspan=4, sticky=(tk.W, tk.E, tk.N, tk.S), pady=theme.SPACE_M
        )

        main.rowconfigure(6, weight=1)

    def browse_file(self) -> None:
        filename = filedialog.askopenfilename(
            title="Select Panorama Image",
            filetypes=[("Image files", "*.jpg *.jpeg *.JPG *.JPEG"), ("All files", "*.*")],
        )
        if not filename:
            return
        self.input_path.set(filename)
        self.is_folder_mode.set(False)
        self.mode_label.config(text="Mode: Single File")
        self.output_path.set(str(Path(filename).with_suffix("")) + "_output")

    def browse_folder(self) -> None:
        folder = filedialog.askdirectory(title="Select Input Folder")
        if not folder:
            return
        chosen = Path(folder)
        self.input_path.set(folder)
        self.is_folder_mode.set(True)
        self.mode_label.config(text="Mode: Folder Processing")
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
        self.previews.rebuild(preview_titles(count))
        self.previews.show_paths(pipeline.output_paths(output_prefix, count))

    def _finish(
        self, message: str, prefix: str | None, count: int | None, error: str | None
    ) -> None:
        """Runs on the main thread. All widget mutation happens here."""
        self.progress.set(100)
        self.status.set(message)
        try:
            if prefix is not None and count is not None:
                self.update_preview(prefix, count)
        finally:
            self.process_btn.config(state="normal")
        if error is not None:
            messagebox.showerror("Error", error)
        else:
            messagebox.showinfo("Success", message)

    def _finish_batch(self, result: pipeline.BatchResult, ratio_name: str) -> None:
        """Runs on the main thread. All widget mutation happens here."""
        self.progress.set(100)
        succeeded = result.succeeded_count
        total = result.total_count
        failed = result.failed
        ratio_display = pipeline.RATIOS[ratio_name].display

        if total == 0:
            message = "No panoramas found"
            self.status.set(message)
            self.process_btn.config(state="normal")
            messagebox.showinfo("No panoramas found", "No JPG files found in the input folder")
            return

        if failed:
            names = ", ".join(path.name for path, _ in failed)
            message = (
                f"Wrote {succeeded} of {total} images at {ratio_display}, "
                f"{len(failed)} failed: {names}"
            )
        else:
            message = f"Wrote {succeeded} of {total} images at {ratio_display}"
        self.status.set(message)
        try:
            if result.last_prefix is not None and result.last_count is not None:
                self.update_preview(str(result.last_prefix), result.last_count)
        finally:
            self.process_btn.config(state="normal")
        if failed:
            messagebox.showwarning("Completed with errors", message)
        else:
            messagebox.showinfo("Success", message)

    def _run_single(self, source: str, prefix: str, ratio_name: str) -> None:
        try:
            written = pipeline.process_image(source, prefix, pipeline.RATIOS[ratio_name])
        except Exception as error:
            self.root.after(0, self._finish, "Failed", None, None, str(error))
            return
        count = len(written) - 1
        message = f"Wrote {count} detail frames at {pipeline.RATIOS[ratio_name].display}"
        self.root.after(0, self._finish, message, prefix, count, None)

    def _run_batch(self, source: str, destination: str, ratio_name: str) -> None:
        def report(done: int, total: int, path: Path) -> None:
            self.root.after(0, self._set_progress, done, total, path.name)

        try:
            result = pipeline.process_folder(
                source, destination, pipeline.RATIOS[ratio_name], on_progress=report
            )
        except Exception as error:
            self.root.after(0, self._finish, "Failed", None, None, str(error))
            return
        self.root.after(0, self._finish_batch, result, ratio_name)

    def _set_progress(self, done: int, total: int, name: str) -> None:
        self.progress.set((done + 1) / total * 100 if total else 0)
        self.status.set(f"Processing {done + 1}/{total}: {name}")

    def process_images(self) -> None:
        source = self.input_path.get()
        if not source or not Path(source).exists():
            messagebox.showerror("Error", "Please select a valid input")
            return
        destination = self.output_path.get()
        if not destination:
            messagebox.showerror("Error", "Please select a valid output")
            return
        self.process_btn.config(state="disabled")
        self.progress.set(0)
        self.status.set("Working...")
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
