"""The application shell.

Owns the root window, the rebate band and the notebook; the tabs own
everything inside themselves.
"""

import tkinter as tk
from tkinter import ttk

from auto_border_pano.gui import shell, theme
from auto_border_pano.gui.compose_tab import ComposeTab
from auto_border_pano.gui.split_tab import PanoramaSplitterGUI


def run() -> None:
    root = tk.Tk()
    # Before any widget is built: `theme.apply` switches ttk to `clam`, and a
    # theme change only reliably restyles widgets created after it.
    theme.apply(root)
    root.configure(background=theme.LIGHTBOX)
    # Not "Panorama Splitter": the second tab splits nothing.
    root.title("Auto Border Pano")
    root.geometry("1100x760")
    root.columnconfigure(0, weight=1)
    root.rowconfigure(1, weight=1)

    band = shell.RebateBand(root)
    band.canvas.grid(row=0, column=0, sticky=(tk.W, tk.E))

    notebook = ttk.Notebook(root)
    notebook.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

    split_page = ttk.Frame(notebook)
    split_page.columnconfigure(0, weight=1)
    split_page.rowconfigure(0, weight=1)
    split = PanoramaSplitterGUI(split_page)
    notebook.add(split_page, text="Split")

    compose = ComposeTab(notebook)
    # "Compose", not "Diptych / Triptych": the tab handles both and names
    # the result for you, so the slash was doing a single verb's work.
    notebook.add(compose.frame, text="Compose")

    # The band is the shell's, not either tab's: each tab states its own
    # subject in a StringVar and the shell stencils whichever tab is in
    # front. That keeps the tabs from having to know about each other, or
    # about the band.
    subjects = [split.subject, compose.subject]

    def show_current_subject(*_args: object) -> None:
        current = int(notebook.index("current"))  # type: ignore[no-untyped-call]
        band.set_subject(subjects[current].get(), strip_suffix=True)

    for subject in subjects:
        subject.trace_add("write", show_current_subject)
    notebook.bind("<<NotebookTabChanged>>", show_current_subject)
    show_current_subject()

    root.mainloop()
