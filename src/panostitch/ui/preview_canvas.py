from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QMouseEvent, QPixmap, QResizeEvent, QWheelEvent
from PySide6.QtWidgets import QLabel, QSizePolicy


class PreviewCanvas(QLabel):
    drag_delta = Signal(float, float, float, float, int, int)
    zoom_delta = Signal(float, float, float, int)
    reset_requested = Signal()
    viewport_resized = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("PreviewCanvas")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWordWrap(True)
        self.setMinimumHeight(360)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setContentsMargins(0, 0, 0, 0)

        self._drag_origin: QPoint | None = None
        self._drag_anchor = (0.0, 0.0)
        self._active_button = Qt.MouseButton.NoButton
        self._source_pixmap: QPixmap | None = None
        self._placeholder_text = ""
        self._display_rect = QRect()
        self._view_zoom = 1.0

    def set_preview_pixmap(self, pixmap: QPixmap) -> None:
        self._source_pixmap = pixmap
        self._update_scaled_pixmap()

    def clear_preview(self, text: str) -> None:
        self._source_pixmap = None
        self._placeholder_text = text
        self._display_rect = QRect()
        self._view_zoom = 1.0
        self.clear()
        self.setText(text)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if event.button() in {Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton, Qt.MouseButton.MiddleButton}:
            self._drag_origin = event.position().toPoint()
            self._active_button = event.button()
            self._drag_anchor = self._normalized_position(self._drag_origin)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if self._drag_origin is not None:
            current = event.position().toPoint()
            delta = current - self._drag_origin
            self._drag_origin = current
            self.drag_delta.emit(
                float(delta.x()),
                float(delta.y()),
                float(self._drag_anchor[0]),
                float(self._drag_anchor[1]),
                _enum_value(self._active_button),
                _enum_value(event.modifiers()),
            )
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if event.button() == self._active_button:
            self._drag_origin = None
            self._active_button = Qt.MouseButton.NoButton
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.MiddleButton:
            self.reset_requested.emit()
        super().mouseDoubleClickEvent(event)

    def enterEvent(self, event) -> None:  # type: ignore[override]
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # type: ignore[override]
        if self._drag_origin is None:
            self.unsetCursor()
        super().leaveEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:  # type: ignore[override]
        angle = event.angleDelta().y()
        if angle:
            modifiers = _enum_value(event.modifiers())
            if modifiers == _enum_value(Qt.KeyboardModifier.NoModifier):
                self._adjust_view_zoom(float(angle) / 120.0)
            else:
                normalized = self._normalized_position(event.position().toPoint())
                self.zoom_delta.emit(
                    float(angle) / 120.0,
                    float(normalized[0]),
                    float(normalized[1]),
                    modifiers,
                )
            event.accept()
            return
        super().wheelEvent(event)

    def resizeEvent(self, event: QResizeEvent) -> None:  # type: ignore[override]
        self._update_scaled_pixmap()
        self.viewport_resized.emit()
        super().resizeEvent(event)

    def reset_view_zoom(self) -> None:
        self._view_zoom = 1.0
        self._update_scaled_pixmap()

    def _adjust_view_zoom(self, steps: float) -> None:
        self._view_zoom = max(0.20, min(6.0, self._view_zoom * (1.12 ** steps)))
        self._update_scaled_pixmap()

    def _update_scaled_pixmap(self) -> None:
        if self._source_pixmap is None:
            if self._placeholder_text:
                self.setText(self._placeholder_text)
            return

        available_width = max(1, self.width())
        available_height = max(1, self.height())
        base_scale = min(
            available_width / max(1, self._source_pixmap.width()),
            available_height / max(1, self._source_pixmap.height()),
        )
        scaled_width = max(1, int(round(self._source_pixmap.width() * base_scale * self._view_zoom)))
        scaled_height = max(1, int(round(self._source_pixmap.height() * base_scale * self._view_zoom)))
        scaled = self._source_pixmap.scaled(
            scaled_width,
            scaled_height,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = (self.width() - scaled.width()) // 2
        y = (self.height() - scaled.height()) // 2
        self._display_rect = QRect(x, y, scaled.width(), scaled.height())
        self.setText("")
        self.setPixmap(scaled)

    def _normalized_position(self, point: QPoint) -> tuple[float, float]:
        rect = self._display_rect if self._display_rect.isValid() else self.rect()
        if rect.width() <= 1 or rect.height() <= 1:
            return (0.0, 0.0)

        clamped_x = max(rect.left(), min(rect.right(), point.x()))
        clamped_y = max(rect.top(), min(rect.bottom(), point.y()))
        x_ratio = (clamped_x - rect.left()) / max(1, rect.width())
        y_ratio = (clamped_y - rect.top()) / max(1, rect.height())
        return ((x_ratio * 2.0) - 1.0, (y_ratio * 2.0) - 1.0)


def _enum_value(value) -> int:
    return int(getattr(value, "value", value))
