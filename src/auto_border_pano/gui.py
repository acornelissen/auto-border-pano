"""tkinter front end.

Importing this module raises ImportError when tkinter is missing; the
friendly message lives in cli.gui_main.
"""

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from auto_border_pano import pipeline

PREVIEW_TITLES = ("Padded Square", "Left Section", "Middle Section", "Right Section")
PREVIEW_MAX_PX = 150


class PanoramaSplitterGUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Panorama Splitter")
        self.root.geometry("800x600")

        self.input_path = tk.StringVar()
        self.output_path = tk.StringVar()
        self.is_folder_mode = tk.BooleanVar(value=False)
        self.progress = tk.DoubleVar()
        self.status = tk.StringVar(value="Ready")
        self._preview_images: list[ImageTk.PhotoImage] = []

        self._build_ui()

    def _build_ui(self) -> None:
        main = ttk.Frame(self.root, padding="10")
        main.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main.columnconfigure(1, weight=1)

        ttk.Label(main, text="Input:").grid(row=0, column=0, sticky=tk.W, pady=5)
        ttk.Entry(main, textvariable=self.input_path, width=50).grid(
            row=0, column=1, sticky=(tk.W, tk.E), padx=5
        )
        ttk.Button(main, text="Browse File", command=self.browse_file).grid(
            row=0, column=2, padx=5
        )
        ttk.Button(main, text="Browse Folder", command=self.browse_folder).grid(
            row=0, column=3, padx=5
        )

        ttk.Label(main, text="Output:").grid(row=1, column=0, sticky=tk.W, pady=5)
        ttk.Entry(main, textvariable=self.output_path, width=50).grid(
            row=1, column=1, sticky=(tk.W, tk.E), padx=5
        )
        ttk.Button(main, text="Browse", command=self.browse_output).grid(
            row=1, column=2, padx=5
        )

        self.mode_label = ttk.Label(main, text="Mode: Single File")
        self.mode_label.grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=10)

        self.process_btn = ttk.Button(
            main, text="Process Images", command=self.process_images
        )
        self.process_btn.grid(row=3, column=0, columnspan=4, pady=20)

        progress_frame = ttk.LabelFrame(main, text="Progress", padding="10")
        progress_frame.grid(row=4, column=0, columnspan=4, sticky=(tk.W, tk.E), pady=10)
        progress_frame.columnconfigure(0, weight=1)
        ttk.Progressbar(progress_frame, variable=self.progress, maximum=100).grid(
            row=0, column=0, sticky=(tk.W, tk.E), pady=5
        )
        ttk.Label(progress_frame, textvariable=self.status).grid(
            row=1, column=0, sticky=tk.W
        )

        preview_frame = ttk.LabelFrame(main, text="Preview (Last Processed)", padding="10")
        preview_frame.grid(
            row=5, column=0, columnspan=4, sticky=(tk.W, tk.E, tk.N, tk.S), pady=10
        )
        preview_frame.rowconfigure(0, weight=1)

        self.preview_labels: list[ttk.Label] = []
        for column, title in enumerate(PREVIEW_TITLES):
            preview_frame.columnconfigure(column, weight=1)
            cell = ttk.Frame(preview_frame)
            cell.grid(row=0, column=column, padx=5, pady=5, sticky=(tk.N, tk.S, tk.E, tk.W))
            ttk.Label(cell, text=title, font=("Arial", 10, "bold")).pack()
            label = ttk.Label(cell, text="No preview", relief="sunken", anchor="center")
            label.pack(expand=True, fill="both")
            self.preview_labels.append(label)

        main.rowconfigure(5, weight=1)

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

    def update_preview(self, output_prefix: str) -> None:
        images: list[ImageTk.PhotoImage] = []
        for label, path in zip(
            self.preview_labels, pipeline.output_paths(output_prefix), strict=True
        ):
            if not path.exists():
                label.config(image="", text="No preview")
                continue
            try:
                with Image.open(path) as img:
                    img.thumbnail((PREVIEW_MAX_PX, PREVIEW_MAX_PX), Image.Resampling.LANCZOS)
                    photo = ImageTk.PhotoImage(img)
            except OSError as error:
                label.config(image="", text=f"Error: {error}")
                continue
            images.append(photo)
            label.config(image=photo, text="")
        self._preview_images = images

    def _finish(self, message: str, prefix: str | None, error: str | None) -> None:
        """Runs on the main thread. All widget mutation happens here."""
        self.progress.set(100)
        self.status.set(message)
        if prefix is not None:
            self.update_preview(prefix)
        self.process_btn.config(state="normal")
        if error is not None:
            messagebox.showerror("Error", error)
        else:
            messagebox.showinfo("Success", message)

    def _finish_batch(self, result: pipeline.BatchResult) -> None:
        """Runs on the main thread. All widget mutation happens here."""
        self.progress.set(100)
        succeeded = result.succeeded_count
        total = result.total_count
        failed = result.failed
        if failed:
            names = ", ".join(path.name for path, _ in failed)
            message = f"Processed {succeeded} of {total}, {len(failed)} failed: {names}"
        else:
            message = f"Processed {succeeded} of {total}"
        self.status.set(message)
        if result.last_prefix is not None:
            self.update_preview(str(result.last_prefix))
        self.process_btn.config(state="normal")
        if failed:
            messagebox.showwarning("Completed with errors", message)
        else:
            messagebox.showinfo("Success", message)

    def _run_single(self, source: str, prefix: str) -> None:
        try:
            pipeline.process_image(source, prefix)
        except (OSError, ValueError) as error:
            self.root.after(0, self._finish, "Failed", None, str(error))
            return
        self.root.after(0, self._finish, "Complete", prefix, None)

    def _run_batch(self, source: str, destination: str) -> None:
        def report(done: int, total: int, path: Path) -> None:
            self.root.after(0, self._set_progress, done, total, path.name)

        try:
            result = pipeline.process_folder(source, destination, on_progress=report)
        except (OSError, ValueError) as error:
            self.root.after(0, self._finish, "Failed", None, str(error))
            return
        self.root.after(0, self._finish_batch, result)

    def _set_progress(self, done: int, total: int, name: str) -> None:
        self.progress.set((done + 1) / total * 100 if total else 0)
        self.status.set(f"Processing {done + 1}/{total}: {name}")

    def process_images(self) -> None:
        source = self.input_path.get()
        if not source or not Path(source).exists():
            messagebox.showerror("Error", "Please select a valid input")
            return
        destination = self.output_path.get()
        self.process_btn.config(state="disabled")
        self.progress.set(0)
        self.status.set("Working...")
        target = self._run_batch if self.is_folder_mode.get() else self._run_single
        threading.Thread(target=target, args=(source, destination), daemon=True).start()


def run() -> None:
    root = tk.Tk()
    PanoramaSplitterGUI(root)
    root.mainloop()
