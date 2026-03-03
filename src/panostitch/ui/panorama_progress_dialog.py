from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFrame, QLabel, QProgressBar, QVBoxLayout


class PanoramaProgressDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("PanoramaProgressDialog")
        self.setWindowTitle("Building panorama preview")
        self.setModal(True)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setMinimumWidth(500)
        self.setMinimumHeight(240)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        card = QFrame()
        card.setObjectName("DialogCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 20, 20, 20)
        card_layout.setSpacing(12)

        self.title_label = QLabel("Building panorama preview")
        self.title_label.setObjectName("DialogTitle")

        self.message_label = QLabel("Preparing panorama build...")
        self.message_label.setObjectName("AppSubtitle")
        self.message_label.setWordWrap(True)

        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)

        self.details_label = QLabel(
            "High-quality stitch settings can take a while. The preview is being prepared in the background."
        )
        self.details_label.setObjectName("AppSubtitle")
        self.details_label.setWordWrap(True)

        card_layout.addWidget(self.title_label)
        card_layout.addWidget(self.message_label)
        card_layout.addWidget(self.progress_bar)
        card_layout.addWidget(self.details_label)
        root_layout.addWidget(card)

    def start(self, total_steps: int) -> None:
        self.progress_bar.setRange(0, max(total_steps, 1))
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%v / %m")
        self.message_label.setText("Preparing panorama build...")

    def update_progress(self, completed: int, total: int, message: str) -> None:
        self.progress_bar.setRange(0, max(total, 1))
        self.progress_bar.setValue(max(0, min(completed, max(total, 1))))
        self.message_label.setText(message)
