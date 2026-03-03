from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from panostitch.core.panorama_stitch import PanoramaStitchSettings, scale_rgb_to_max_edge, stitch_rgb_images
from panostitch.core.render_pipeline import render_corrected_rgb, scaled_frame_to_bounds
from panostitch.domain.models import CorrectionPreset
from panostitch.io.image_loader import load_image


@dataclass(slots=True)
class PanoramaRenderRequest:
    request_id: int
    cache_key: str
    image_paths: list[Path]
    settings: PanoramaStitchSettings
    use_fisheye_precorrection: bool
    fisheye_preset: CorrectionPreset
    backend_api: str


class PanoramaWorker(QObject):
    progress = Signal(int, int, int, str)
    finished = Signal(object)
    failed = Signal(int, str)

    @Slot(object)
    def render(self, request: PanoramaRenderRequest) -> None:
        try:
            prepared_images = []
            input_names = []
            total_steps = len(request.image_paths) + 1
            self.progress.emit(request.request_id, 0, total_steps, "Preparing panorama inputs...")
            for index, path in enumerate(request.image_paths, start=1):
                if request.use_fisheye_precorrection:
                    message = f"Preparing image {index}/{len(request.image_paths)} with fisheye correction: {path.name}"
                else:
                    message = f"Loading image {index}/{len(request.image_paths)}: {path.name}"
                self.progress.emit(request.request_id, index - 1, total_steps, message)
                loaded = load_image(path, max_edge=max(request.settings.max_input_edge, 2200))
                if request.use_fisheye_precorrection:
                    output_frame = scaled_frame_to_bounds(
                        request.fisheye_preset.output_frame,
                        request.settings.max_input_edge,
                        request.settings.max_input_edge,
                    )
                    corrected_preset = replace(request.fisheye_preset, output_frame=output_frame)
                    corrected_rgb, _metrics = render_corrected_rgb(
                        loaded.rgb_data,
                        corrected_preset,
                        output_frame=output_frame,
                        backend_api=request.backend_api,
                    )
                    prepared_images.append(corrected_rgb)
                else:
                    prepared_images.append(scale_rgb_to_max_edge(loaded.rgb_data, request.settings.max_input_edge))
                input_names.append(path.name)
                self.progress.emit(request.request_id, index, total_steps, message)

            self.progress.emit(
                request.request_id,
                len(request.image_paths),
                total_steps,
                "Running feature matching, camera solve and panorama stitch...",
            )
            panorama_rgb, metrics = stitch_rgb_images(prepared_images, request.settings)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(request.request_id, str(exc))
            return

        self.progress.emit(
            request.request_id,
            total_steps,
            total_steps,
            "Panorama preview ready.",
        )
        self.finished.emit(
            {
                "request_id": request.request_id,
                "cache_key": request.cache_key,
                "rendered": panorama_rgb,
                "metrics": metrics,
                "input_names": input_names,
                "used_precorrection": request.use_fisheye_precorrection,
                "backend_api": request.backend_api,
                "max_input_edge": request.settings.max_input_edge,
            }
        )
