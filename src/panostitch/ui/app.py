from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from panostitch.ui.main_window import MainWindow
from panostitch.ui.theme import DARK_THEME_QSS


def run_desktop_app() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(DARK_THEME_QSS)

    window = MainWindow()
    window.show()
    return app.exec()
