from __future__ import annotations

from dataclasses import dataclass
import locale

import cv2
import numpy as np


@dataclass(slots=True)
class PanoramaStitchSettings:
    mode: str = "panorama"
    max_input_edge: int = 1800
    registration_resol_mpx: float = 0.6
    seam_resol_mpx: float = 0.3
    compositing_resol_mpx: float = 1.2
    confidence_threshold: float = 1.0
    wave_correction: bool = True


def scale_rgb_to_max_edge(rgb: np.ndarray, max_edge: int) -> np.ndarray:
    if max_edge <= 0:
        raise ValueError("max_edge must be positive.")

    height, width = rgb.shape[:2]
    largest_edge = max(height, width)
    if largest_edge <= max_edge:
        return rgb

    scale = max_edge / largest_edge
    resized_width = max(1, int(round(width * scale)))
    resized_height = max(1, int(round(height * scale)))
    return cv2.resize(rgb, (resized_width, resized_height), interpolation=cv2.INTER_AREA)


def stitch_status_name(status_code: int) -> str:
    names = {
        getattr(cv2, "Stitcher_OK", 0): "Stitch successful",
        getattr(cv2, "Stitcher_ERR_NEED_MORE_IMGS", 1): "Need more overlapping images",
        getattr(cv2, "Stitcher_ERR_HOMOGRAPHY_EST_FAIL", 2): "Could not estimate image homography",
        getattr(cv2, "Stitcher_ERR_CAMERA_PARAMS_ADJUST_FAIL", 3): "Could not adjust camera parameters",
    }
    return names.get(status_code, f"Unknown stitch error ({status_code})")


def stitch_rgb_images(
    images_rgb: list[np.ndarray],
    settings: PanoramaStitchSettings,
) -> tuple[np.ndarray, dict[str, float | int | str]]:
    if len(images_rgb) < 2:
        raise ValueError("Select at least two overlapping images to stitch.")

    stitcher = cv2.Stitcher_create(_cv_stitch_mode(settings.mode))
    stitcher.setRegistrationResol(float(settings.registration_resol_mpx))
    stitcher.setSeamEstimationResol(float(settings.seam_resol_mpx))
    stitcher.setCompositingResol(float(settings.compositing_resol_mpx))
    stitcher.setPanoConfidenceThresh(float(settings.confidence_threshold))
    stitcher.setWaveCorrection(bool(settings.wave_correction))

    bgr_images = [cv2.cvtColor(image, cv2.COLOR_RGB2BGR) for image in images_rgb]
    previous_locale = locale.setlocale(locale.LC_NUMERIC)
    try:
        locale.setlocale(locale.LC_NUMERIC, "C")
        status_code, panorama_bgr = stitcher.stitch(bgr_images)
    finally:
        locale.setlocale(locale.LC_NUMERIC, previous_locale)
    if status_code != getattr(cv2, "Stitcher_OK", 0):
        raise ValueError(stitch_status_name(int(status_code)))

    panorama_rgb = cv2.cvtColor(panorama_bgr, cv2.COLOR_BGR2RGB)
    metrics: dict[str, float | int | str] = {
        "status_code": int(status_code),
        "status_name": stitch_status_name(int(status_code)),
        "image_count": len(images_rgb),
        "output_width": int(panorama_rgb.shape[1]),
        "output_height": int(panorama_rgb.shape[0]),
        "mode": settings.mode,
    }
    return panorama_rgb, metrics


def _cv_stitch_mode(mode: str) -> int:
    if mode == "panorama":
        return int(getattr(cv2, "Stitcher_PANORAMA", 0))
    if mode == "scans":
        return int(getattr(cv2, "Stitcher_SCANS", 1))
    raise ValueError(f"Unsupported stitch mode: {mode}")
