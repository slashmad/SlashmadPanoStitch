from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from panostitch.core.render_pipeline import render_corrected_rgb
from panostitch.domain.models import CorrectionPreset, FrameGeometry


@dataclass(slots=True)
class PreviewRenderRequest:
    request_id: int
    image_path: Path
    source_rgb: object
    source_width: int
    source_height: int
    preset: CorrectionPreset
    output_frame: FrameGeometry
    backend_api: str


class PreviewWorker(QObject):
    finished = Signal(object)
    failed = Signal(int, str)

    @Slot(object)
    def render(self, request: PreviewRenderRequest) -> None:
        try:
            rendered, metrics = render_corrected_rgb(
                request.source_rgb,
                request.preset,
                output_frame=request.output_frame,
                backend_api=request.backend_api,
            )
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(request.request_id, str(exc))
            return

        self.finished.emit(
            {
                "request_id": request.request_id,
                "image_path": request.image_path,
                "source_width": request.source_width,
                "source_height": request.source_height,
                "rendered": rendered,
                "metrics": metrics,
                "preset": request.preset,
            }
        )
