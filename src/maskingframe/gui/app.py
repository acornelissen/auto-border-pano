"""The application shell.

Owns the window, the rebate band and the tabs; the tabs own everything
inside themselves.
"""

import sys

from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget, QVBoxLayout, QWidget

from maskingframe.gui import shell, theme
from maskingframe.gui.compose_tab import ComposeTab
from maskingframe.gui.split_tab import SplitTab


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        # Not "Panorama Splitter": the second tab splits nothing.
        self.setWindowTitle("Masking Frame")
        self.resize(1180, 820)
        self.setMinimumSize(940, 720)

        central = QWidget()
        column = QVBoxLayout(central)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)

        self.band = shell.RebateBand()
        column.addWidget(self.band)

        self.tabs = QTabWidget()
        self.tabs.setTabBar(shell.TabBand())
        self.tabs.setDocumentMode(True)

        self.split = SplitTab()
        self.compose = ComposeTab()
        self.tabs.addTab(self.split, "Split")
        self.tabs.addTab(self.compose, "Compose")
        column.addWidget(self.tabs, 1)

        self.setCentralWidget(central)

        # The band belongs to the shell, not to either tab: each tab states
        # what it is working on and what it will make of it, and the shell
        # stencils whichever tab is in front. Neither tab knows about the
        # band, or about the other tab.
        for tab in (self.split, self.compose):
            tab.band_changed.connect(self._show_current)
        self.tabs.currentChanged.connect(self._show_current)
        self._show_current()

    def _show_current(self, *_args: object) -> None:
        current = self.tabs.currentWidget()
        subject = getattr(current, "subject", "")
        detail = getattr(current, "detail", "")
        self.band.set_subject(subject)
        self.band.set_detail(detail)


def run() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    assert isinstance(app, QApplication)
    app.setApplicationName("Masking Frame")
    app.setStyleSheet(theme.stylesheet())
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
