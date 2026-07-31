"""A row of thumbnail panes that rebuilds as the count changes.

Shared by both tabs. This is the fiddliest widget code in the project: the
pane count varies between runs, so stale panes and stale grid weights both
have to be cleared, and PhotoImage references have to be held or Tk renders
blanks.
"""

import tkinter as tk
from collections.abc import Sequence
from pathlib import Path
from tkinter import ttk

from PIL import Image, ImageTk

from auto_border_pano.gui import theme

PREVIEW_MAX_PX = 150


class PreviewPanes:
    def __init__(self, parent: tk.Misc, title: str = "Preview") -> None:
        self.frame = ttk.LabelFrame(parent, text=title, padding=theme.SPACE_M)
        self.frame.rowconfigure(0, weight=1)
        self.labels: list[ttk.Label] = []
        self._images: list[ImageTk.PhotoImage] = []
        self._max_columns = 0
        # Reasons for any UNREADABLE frame in the last show_paths call.
        self.errors: list[str] = []

    def rebuild(self, titles: Sequence[str]) -> None:
        """Recreate the cells. Main thread only."""
        for child in self.frame.winfo_children():
            child.destroy()
        self.labels = []

        for column, title in enumerate(titles):
            self.frame.columnconfigure(column, weight=1)
            cell = ttk.Frame(self.frame)
            cell.grid(
                row=0,
                column=column,
                padx=theme.SPACE_S,
                pady=theme.SPACE_S,
                sticky=(tk.N, tk.S, tk.E, tk.W),
            )
            ttk.Label(cell, text=title, style="Stencil.TLabel").pack()
            label = ttk.Label(
                cell,
                text="NOTHING ON THE STRIP YET",
                style="Help.TLabel",
                background=theme.SLEEVE,
                relief="flat",
                anchor="center",
            )
            label.pack(expand=True, fill="both")
            self.labels.append(label)

        # Drop stale column weights from any previous, longer run, up to the
        # highest column count this instance has ever built.
        for column in range(len(titles), self._max_columns + 1):
            self.frame.columnconfigure(column, weight=0)
        self._max_columns = max(self._max_columns, len(titles))

    def show_paths(self, paths: Sequence[Path]) -> None:
        """Load thumbnails from files, one per existing pane."""
        images: list[ImageTk.PhotoImage] = []
        self.errors = []
        for label, path in zip(self.labels, paths, strict=True):
            if not path.exists():
                label.config(image="", text="NOTHING ON THE STRIP YET")
                continue
            try:
                with Image.open(path) as img:
                    img.thumbnail((PREVIEW_MAX_PX, PREVIEW_MAX_PX), Image.Resampling.LANCZOS)
                    photo = ImageTk.PhotoImage(img)
            except Exception as error:
                # The frame says UNREADABLE; the reason is kept here so a
                # caller can put it in the status line.
                label.config(image="", text="UNREADABLE")
                self.errors.append(f"{path.name}: {error}")
                continue
            images.append(photo)
            label.config(image=photo, text="")
        self._images = images

    def show_images(self, images: Sequence[Image.Image]) -> None:
        """Show already-loaded images, one per existing pane."""
        photos: list[ImageTk.PhotoImage] = []
        for label, image in zip(self.labels, images, strict=True):
            thumbnail = image.copy()
            thumbnail.thumbnail((PREVIEW_MAX_PX, PREVIEW_MAX_PX), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(thumbnail)
            photos.append(photo)
            label.config(image=photo, text="")
        self._images = photos
