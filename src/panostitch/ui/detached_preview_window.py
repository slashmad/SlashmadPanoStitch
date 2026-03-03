from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QMainWindow, QTextEdit, QVBoxLayout, QWidget

from panostitch.ui.preview_canvas import PreviewCanvas


class DetachedPreviewWindow(QMainWindow):
    closed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("PanoStitch Preview")
        self.resize(980, 860)
        self.setMinimumSize(640, 520)

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        self.preview_canvas = PreviewCanvas()
        self.preview_canvas.clear_preview("Preview window")

        self.metrics_text = QTextEdit()
        self.metrics_text.setReadOnly(True)
        self.metrics_text.setMinimumHeight(140)
        self.metrics_text.setMaximumHeight(220)

        layout.addWidget(self.preview_canvas, 1)
        layout.addWidget(self.metrics_text)
        self.setCentralWidget(root)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self.closed.emit()
        super().closeEvent(event)
