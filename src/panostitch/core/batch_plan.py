from __future__ import annotations

from pathlib import Path

from panostitch.core.fisheye_math import estimate_valid_region
from panostitch.domain.models import CorrectionPreset, ExportOptions, ImageAsset

RAW_EXTENSIONS = {".arw", ".cr2", ".cr3", ".dng", ".nef", ".orf", ".raf", ".rw2"}
RASTER_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}


def suggested_export_mode(source_path: Path, requested_mode: str) -> str:
    extension = source_path.suffix.lower()
    if requested_mode != "preserve-raster":
        return requested_mode
    if extension in RASTER_EXTENSIONS:
        return extension.lstrip(".")
    if extension in RAW_EXTENSIONS:
        return "linear-dng"
    return "tiff"


def derive_output_name(source_path: Path, suffix: str, export_mode: str) -> str:
    base_name = source_path.stem + suffix
    if export_mode == "jpg":
        return f"{base_name}.jpg"
    if export_mode == "jpeg":
        return f"{base_name}.jpeg"
    if export_mode == "png":
        return f"{base_name}.png"
    if export_mode == "tif":
        return f"{base_name}.tif"
    if export_mode == "tiff":
        return f"{base_name}.tiff"
    if export_mode == "linear-dng":
        return f"{base_name}.dng"
    return f"{base_name}.{export_mode}"


def build_batch_job_summary(
    preset: CorrectionPreset,
    image_paths: list[Path],
    export: ExportOptions | None = None,
) -> dict:
    export = export or ExportOptions()
    assets = [ImageAsset(path=path) for path in image_paths]
    coverage = estimate_valid_region(preset)

    outputs = []
    for asset in assets:
        export_mode = suggested_export_mode(asset.path, export.mode)
        outputs.append(
            {
                "source": str(asset.path),
                "export_mode": export_mode,
                "output_name": derive_output_name(asset.path, export.suffix, export_mode),
            }
        )

    return {
        "preset_name": preset.name,
        "camera": preset.camera.model,
        "lens": preset.lens.model,
        "output_projection": preset.output_projection,
        "correction": {
            "yaw_deg": preset.yaw_deg,
            "pitch_deg": preset.pitch_deg,
            "roll_deg": preset.roll_deg,
            "zoom": preset.zoom,
            "vertical_shift": preset.vertical_shift,
        },
        "coverage_estimate": coverage,
        "outputs": outputs,
    }
