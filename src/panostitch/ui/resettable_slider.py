from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QSlider, QStyle, QStyleOptionSlider


class ResettableSlider(QSlider):
    reset_to_default = Signal()

    def __init__(self, orientation: Qt.Orientation, parent=None) -> None:
        super().__init__(orientation, parent)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton and self._handle_rect().contains(event.position().toPoint()):
            self.reset_to_default.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def _handle_rect(self):
        option = QStyleOptionSlider()
        self.initStyleOption(option)
        return self.style().subControlRect(
            QStyle.ComplexControl.CC_Slider,
            option,
            QStyle.SubControl.SC_SliderHandle,
            self,
        )
