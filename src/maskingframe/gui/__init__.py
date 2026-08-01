"""Qt front end.

Importing this package raises ImportError when PySide6 is missing; the
friendly message lives in `cli.gui_main`.
"""

from maskingframe.gui.app import MainWindow, run

__all__ = ["MainWindow", "run"]
