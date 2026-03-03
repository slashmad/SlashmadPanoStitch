from __future__ import annotations

from pathlib import Path
from typing import Callable

import cv2

from panostitch.core.batch_plan import derive_output_name
from panostitch.core.render_pipeline import render_corrected_rgb
from panostitch.domain.models import CorrectionPreset, ExportOptions
from panostitch.io.image_loader import (
    SUPPORTED_RASTER_EXTENSIONS,
    is_raw_image,
    load_image,
    save_rgb_image,
)


def export_batch(
    image_paths: list[Path],
    preset: CorrectionPreset,
    output_dir: Path,
    export: ExportOptions,
    render_backend_api: str = "cpu",
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> dict[str, object]:
    outputs: list[dict[str, str]] = []
    notes: list[str] = []
    total = len(image_paths)

    if export.mode == "linear-dng":
        raise NotImplementedError("Linear DNG export is not implemented in this build.")

    for image_path in image_paths:
        current_index = len(outputs) + 1
        if progress_callback is not None:
            progress_callback(current_index - 1, total, f"Processing {image_path.name} ({current_index}/{total})")

        loaded = load_image(image_path, max_edge=None)
        rendered, _ = render_corrected_rgb(
            loaded.rgb_data,
            preset,
            output_frame=preset.output_frame,
            interpolation=cv2.INTER_LANCZOS4,
            backend_api=render_backend_api,
        )
        output_format = resolve_export_format(image_path, export.mode)
        output_name = derive_output_name(image_path, export.suffix, output_format)
        output_path = output_dir / output_name
        save_rgb_image(rendered, output_path, output_format, jpeg_quality=export.jpeg_quality)
        outputs.append({"source": str(image_path), "output": str(output_path), "format": output_format})
        if progress_callback is not None:
            progress_callback(len(outputs), total, f"Exported {image_path.name} ({len(outputs)}/{total})")

        if export.mode == "preserve-raster" and is_raw_image(image_path):
            note = f"{image_path.name}: RAW input exported as TIFF in the current build."
            if note not in notes:
                notes.append(note)

    return {"count": len(outputs), "outputs": outputs, "notes": notes}


def resolve_export_format(image_path: Path, requested_mode: str) -> str:
    extension = image_path.suffix.lower()

    if requested_mode == "preserve-raster":
        if extension in SUPPORTED_RASTER_EXTENSIONS:
            return extension.lstrip(".")
        return "tiff"
    if requested_mode in {"jpeg", "tiff"}:
        return requested_mode
    if requested_mode == "linear-dng":
        raise NotImplementedError("Linear DNG export is not implemented in this build.")
    raise ValueError(f"Unsupported export mode: {requested_mode}")
