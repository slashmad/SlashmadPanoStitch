from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from panostitch.core.exporter import export_batch
from panostitch.domain.models import CorrectionPreset, ExportOptions


class ExportWorker(QObject):
    progress = Signal(int, int, str)
    finished = Signal(dict)
    failed = Signal(str, str)

    def __init__(
        self,
        image_paths: list[Path],
        preset: CorrectionPreset,
        output_dir: Path,
        export_options: ExportOptions,
        render_backend_api: str,
    ) -> None:
        super().__init__()
        self.image_paths = image_paths
        self.preset = preset
        self.output_dir = output_dir
        self.export_options = export_options
        self.render_backend_api = render_backend_api

    @Slot()
    def run(self) -> None:
        try:
            result = export_batch(
                self.image_paths,
                self.preset,
                self.output_dir,
                self.export_options,
                render_backend_api=self.render_backend_api,
                progress_callback=self.progress.emit,
            )
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(type(exc).__name__, str(exc))
            return

        self.finished.emit(result)
