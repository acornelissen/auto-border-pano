"""The application shell.

Owns the root window and the notebook; the tabs own everything inside
themselves.
"""

import tkinter as tk
from tkinter import ttk

from auto_border_pano.gui import theme
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
    root.geometry("900x700")
    root.columnconfigure(0, weight=1)
    root.rowconfigure(0, weight=1)

    notebook = ttk.Notebook(root)
    notebook.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

    split_page = ttk.Frame(notebook)
    split_page.columnconfigure(0, weight=1)
    split_page.rowconfigure(0, weight=1)
    PanoramaSplitterGUI(split_page)
    notebook.add(split_page, text="Split")

    compose = ComposeTab(notebook)
    # "Compose", not "Diptych / Triptych": the tab handles both and names
    # the result for you, so the slash was doing a single verb's work.
    notebook.add(compose.frame, text="Compose")

    root.mainloop()
