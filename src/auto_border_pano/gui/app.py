"""The application shell.

Owns the root window and the notebook; the tabs own everything inside
themselves.
"""

import tkinter as tk

from auto_border_pano.gui.split_tab import PanoramaSplitterGUI


def run() -> None:
    root = tk.Tk()
    root.title("Panorama Splitter")
    root.geometry("900x700")
    PanoramaSplitterGUI(root)
    root.mainloop()
