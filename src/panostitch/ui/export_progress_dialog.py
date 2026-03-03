from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFrame, QLabel, QProgressBar, QVBoxLayout


class ExportProgressDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("ExportProgressDialog")
        self.setWindowTitle("Exporting")
        self.setModal(True)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setMinimumWidth(460)
        self.setMinimumHeight(220)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        card = QFrame()
        card.setObjectName("DialogCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 20, 20, 20)
        card_layout.setSpacing(12)

        self.title_label = QLabel("Export in progress")
        self.title_label.setObjectName("DialogTitle")
        self.message_label = QLabel("Preparing export...")
        self.message_label.setObjectName("AppSubtitle")
        self.message_label.setWordWrap(True)

        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)

        self.details_label = QLabel("Do not close the app while files are being written.")
        self.details_label.setObjectName("AppSubtitle")
        self.details_label.setWordWrap(True)

        card_layout.addWidget(self.title_label)
        card_layout.addWidget(self.message_label)
        card_layout.addWidget(self.progress_bar)
        card_layout.addWidget(self.details_label)
        root_layout.addWidget(card)

    def set_export_scope(self, scope_label: str, total: int) -> None:
        self.title_label.setText(f"Exporting {scope_label}")
        self.progress_bar.setRange(0, max(total, 1))
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%v / %m")

    def update_progress(self, completed: int, total: int, message: str) -> None:
        self.progress_bar.setRange(0, max(total, 1))
        self.progress_bar.setValue(max(0, min(completed, max(total, 1))))
        self.message_label.setText(message)
