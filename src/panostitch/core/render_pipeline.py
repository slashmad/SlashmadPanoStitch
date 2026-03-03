from __future__ import annotations

import math

import cv2
import numpy as np

from panostitch.core.fisheye_math import rotation_matrix
from panostitch.domain.models import CorrectionPreset, FrameGeometry, LensProfile


def scaled_frame_to_bounds(frame: FrameGeometry, max_width: int, max_height: int) -> FrameGeometry:
    if frame.width <= 0 or frame.height <= 0:
        raise ValueError("Frame dimensions must be positive.")

    scale = min(max_width / frame.width, max_height / frame.height)
    scale = min(scale, 1.0)
    width = max(1, int(round(frame.width * scale)))
    height = max(1, int(round(frame.height * scale)))
    return FrameGeometry(width=width, height=height)


def render_corrected_rgb(
    source_rgb: np.ndarray,
    preset: CorrectionPreset,
    output_frame: FrameGeometry | None = None,
    interpolation: int = cv2.INTER_LINEAR,
    backend_api: str = "cpu",
) -> tuple[np.ndarray, dict[str, float | str]]:
    if source_rgb.ndim != 3 or source_rgb.shape[2] != 3:
        raise ValueError("Expected an RGB image with shape (height, width, 3).")

    output_frame = output_frame or preset.output_frame
    source_frame = FrameGeometry(width=int(source_rgb.shape[1]), height=int(source_rgb.shape[0]))

    map_x, map_y, valid_mask = build_remap_grid(
        preset=preset,
        source_frame=source_frame,
        output_frame=output_frame,
    )

    rendered = _remap_image(
        source_rgb,
        map_x,
        map_y,
        interpolation=interpolation,
        border_value=(10, 14, 18),
        backend_api=backend_api,
    )
    valid_mask_float = valid_mask.astype(np.float32)

    if abs(preset.curve_straighten) > 1e-6:
        rendered = _apply_curve_straighten(
            rendered,
            amount=preset.curve_straighten,
            anchor_y=preset.curve_anchor_y,
            span=preset.curve_span,
            interpolation=interpolation,
            border_value=(10, 14, 18),
            backend_api=backend_api,
        )
        valid_mask_float = _apply_curve_straighten(
            valid_mask_float,
            amount=preset.curve_straighten,
            anchor_y=preset.curve_anchor_y,
            span=preset.curve_span,
            interpolation=cv2.INTER_NEAREST,
            border_value=0.0,
            backend_api=backend_api,
        )

    if abs(preset.post_rotate_deg) > 1e-6:
        rendered = _rotate_in_frame(
            rendered,
            degrees=preset.post_rotate_deg,
            interpolation=interpolation,
            border_value=(10, 14, 18),
            backend_api=backend_api,
        )
        valid_mask_float = _rotate_in_frame(
            valid_mask_float,
            degrees=preset.post_rotate_deg,
            interpolation=cv2.INTER_NEAREST,
            border_value=0.0,
            backend_api=backend_api,
        )

    valid_fraction = float((valid_mask_float > 0.5).mean())
    metrics = {
        "valid_fraction": valid_fraction,
        "valid_pixel_count": float((valid_mask_float > 0.5).sum()),
        "output_width": float(output_frame.width),
        "output_height": float(output_frame.height),
        "backend_api": backend_api,
    }
    return rendered, metrics


def render_panorama_adjusted_rgb(
    source_rgb: np.ndarray,
    preset: CorrectionPreset,
    output_frame: FrameGeometry | None = None,
    interpolation: int = cv2.INTER_LINEAR,
    backend_api: str = "cpu",
) -> tuple[np.ndarray, dict[str, float | str]]:
    if source_rgb.ndim != 3 or source_rgb.shape[2] != 3:
        raise ValueError("Expected an RGB image with shape (height, width, 3).")

    source_frame = FrameGeometry(width=int(source_rgb.shape[1]), height=int(source_rgb.shape[0]))
    output_frame = output_frame or source_frame
    crop_scale = max(0.05, 1.0 - (preset.safe_margin * 2.0))
    fov_scale = 120.0 / max(20.0, float(preset.horizontal_fov_deg))
    zoom_scale = max(0.05, float(preset.zoom) * fov_scale / crop_scale)
    base_scale = min(
        output_frame.width / max(1, source_frame.width),
        output_frame.height / max(1, source_frame.height),
    )
    transform_scale = max(1e-6, base_scale * zoom_scale)

    center_src = (source_frame.width / 2.0, source_frame.height / 2.0)
    center_dst = (output_frame.width / 2.0, output_frame.height / 2.0)
    rotation_deg = float(preset.roll_deg) + float(preset.post_rotate_deg)
    matrix = cv2.getRotationMatrix2D(center_src, rotation_deg, transform_scale)

    mapped_center_x = (matrix[0, 0] * center_src[0]) + (matrix[0, 1] * center_src[1]) + matrix[0, 2]
    mapped_center_y = (matrix[1, 0] * center_src[0]) + (matrix[1, 1] * center_src[1]) + matrix[1, 2]
    x_offset = (float(preset.yaw_deg) / 180.0) * (output_frame.width * 0.85)
    y_offset = ((float(preset.vertical_shift) * 0.5) - (float(preset.pitch_deg) / 180.0)) * (output_frame.height * 0.85)
    matrix[0, 2] += center_dst[0] + x_offset - mapped_center_x
    matrix[1, 2] += center_dst[1] + y_offset - mapped_center_y

    rendered = _warp_affine_image(
        image=source_rgb,
        matrix=matrix,
        size=(output_frame.width, output_frame.height),
        interpolation=interpolation,
        border_value=(10, 14, 18),
        backend_api=backend_api,
    )
    valid_mask = _warp_affine_image(
        image=np.ones((source_frame.height, source_frame.width), dtype=np.float32),
        matrix=matrix,
        size=(output_frame.width, output_frame.height),
        interpolation=cv2.INTER_NEAREST,
        border_value=0.0,
        backend_api=backend_api,
    )
    metrics = {
        "valid_fraction": float((valid_mask > 0.5).mean()),
        "output_width": float(output_frame.width),
        "output_height": float(output_frame.height),
        "backend_api": backend_api,
        "view_scale": float(zoom_scale),
    }
    return rendered, metrics


def build_remap_grid(
    preset: CorrectionPreset,
    source_frame: FrameGeometry,
    output_frame: FrameGeometry,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    x_coords = np.linspace(-1.0, 1.0, output_frame.width, dtype=np.float32)
    y_coords = np.linspace(-1.0, 1.0, output_frame.height, dtype=np.float32)
    x_ndc, y_ndc = np.meshgrid(x_coords, y_coords)

    rays = _build_output_rays(
        x_ndc=x_ndc,
        y_ndc=y_ndc,
        output_frame=output_frame,
        projection=preset.output_projection,
        horizontal_fov_deg=preset.horizontal_fov_deg,
        zoom=preset.zoom,
        vertical_shift=preset.vertical_shift,
        safe_margin=preset.safe_margin,
    )

    rotation = np.array(rotation_matrix(preset.yaw_deg, preset.pitch_deg, preset.roll_deg), dtype=np.float32)
    rotated = np.einsum("ij,jhw->ihw", rotation, rays)

    x_rot = rotated[0]
    y_rot = rotated[1]
    z_rot = rotated[2]
    theta = np.arccos(np.clip(z_rot, -1.0, 1.0))
    phi = np.arctan2(y_rot, x_rot)
    radius = _fisheye_radius(theta, preset.lens)

    half_diagonal = math.sqrt((source_frame.width / 2.0) ** 2 + (source_frame.height / 2.0) ** 2)
    sensor_x = -np.cos(phi) * radius * half_diagonal
    sensor_y = np.sin(phi) * radius * half_diagonal

    u = 0.5 + (sensor_x / source_frame.width)
    v = 0.5 - (sensor_y / source_frame.height)

    valid = z_rot > 0.0
    valid &= u >= 0.0
    valid &= u <= 1.0
    valid &= v >= 0.0
    valid &= v <= 1.0

    map_x = (u * (source_frame.width - 1)).astype(np.float32)
    map_y = (v * (source_frame.height - 1)).astype(np.float32)
    map_x[~valid] = -1.0
    map_y[~valid] = -1.0
    return map_x, map_y, valid


def _build_output_rays(
    x_ndc: np.ndarray,
    y_ndc: np.ndarray,
    output_frame: FrameGeometry,
    projection: str,
    horizontal_fov_deg: float,
    zoom: float,
    vertical_shift: float,
    safe_margin: float,
) -> np.ndarray:
    aspect = output_frame.aspect_ratio
    fov = math.radians(horizontal_fov_deg)
    h_scale = math.tan(fov / 2.0) / max(zoom, 1e-6)
    v_scale = h_scale / aspect
    crop_scale = max(0.05, 1.0 - (safe_margin * 2.0))
    x_adjusted = x_ndc * crop_scale
    y_adjusted = (-y_ndc * crop_scale) + vertical_shift

    if projection == "rectilinear":
        rays = np.stack((x_adjusted * h_scale, y_adjusted * v_scale, np.ones_like(x_ndc)), axis=0)
    elif projection == "cylindrical":
        theta = x_adjusted * (fov / 2.0) / max(zoom, 1e-6)
        rays = np.stack((np.sin(theta), y_adjusted * v_scale, np.cos(theta)), axis=0)
    else:
        raise ValueError(f"Unsupported projection: {projection}")

    norms = np.linalg.norm(rays, axis=0)
    norms = np.maximum(norms, 1e-8)
    return rays / norms


def _fisheye_radius(theta: np.ndarray, lens: LensProfile) -> np.ndarray:
    theta_limit = math.radians(lens.diagonal_fov_deg) / 2.0
    clipped = np.clip(theta, 0.0, theta_limit)

    if lens.fisheye_mapping == "equidistant":
        return clipped / theta_limit
    if lens.fisheye_mapping == "equisolid":
        return np.sin(clipped / 2.0) / math.sin(theta_limit / 2.0)
    if lens.fisheye_mapping == "stereographic":
        return np.tan(clipped / 2.0) / math.tan(theta_limit / 2.0)
    if lens.fisheye_mapping == "orthographic":
        return np.sin(clipped) / math.sin(theta_limit)
    raise ValueError(f"Unsupported fisheye mapping: {lens.fisheye_mapping}")


def _rotate_in_frame(
    image: np.ndarray,
    degrees: float,
    interpolation: int,
    border_value,
    backend_api: str,
) -> np.ndarray:
    if abs(degrees) <= 1e-6:
        return image

    height, width = image.shape[:2]
    center = (width / 2.0, height / 2.0)
    matrix = cv2.getRotationMatrix2D(center, degrees, 1.0)
    return _warp_affine_image(
        image=image,
        matrix=matrix,
        size=(width, height),
        interpolation=interpolation,
        border_value=border_value,
        backend_api=backend_api,
    )


def _apply_curve_straighten(
    image: np.ndarray,
    amount: float,
    anchor_y: float,
    span: float,
    interpolation: int,
    border_value,
    backend_api: str,
) -> np.ndarray:
    if abs(amount) <= 1e-6:
        return image

    height, width = image.shape[:2]
    x_coords = np.linspace(-1.0, 1.0, width, dtype=np.float32)
    y_coords = np.linspace(-1.0, 1.0, height, dtype=np.float32)
    x_ndc, y_ndc = np.meshgrid(x_coords, y_coords)

    basis = 1.0 - np.square(x_ndc)
    local = np.clip(1.0 - (np.abs(y_ndc - anchor_y) / max(span, 0.05)), 0.0, 1.0)
    local = np.square(local)
    offset_y = -amount * basis * local * (height * 0.18)

    map_x, map_y = np.meshgrid(
        np.arange(width, dtype=np.float32),
        np.arange(height, dtype=np.float32),
    )
    map_y = map_y + offset_y.astype(np.float32)

    return _remap_image(
        image=image,
        map_x=map_x,
        map_y=map_y,
        interpolation=interpolation,
        border_value=border_value,
        backend_api=backend_api,
    )


def _remap_image(
    image: np.ndarray,
    map_x: np.ndarray,
    map_y: np.ndarray,
    interpolation: int,
    border_value,
    backend_api: str,
) -> np.ndarray:
    if backend_api == "cuda":
        try:
            src_gpu = cv2.cuda_GpuMat()
            src_gpu.upload(image)
            map_x_gpu = cv2.cuda_GpuMat()
            map_y_gpu = cv2.cuda_GpuMat()
            map_x_gpu.upload(map_x)
            map_y_gpu.upload(map_y)
            rendered_gpu = cv2.cuda.remap(
                src_gpu,
                map_x_gpu,
                map_y_gpu,
                interpolation,
                borderMode=cv2.BORDER_CONSTANT,
                borderValue=border_value,
            )
            return rendered_gpu.download()
        except Exception:
            backend_api = "cpu"

    if backend_api == "opencl" and cv2.ocl.useOpenCL():
        try:
            rendered = cv2.remap(
                cv2.UMat(image),
                cv2.UMat(map_x),
                cv2.UMat(map_y),
                interpolation=interpolation,
                borderMode=cv2.BORDER_CONSTANT,
                borderValue=border_value,
            )
            return rendered.get()
        except Exception:
            backend_api = "cpu"

    return cv2.remap(
        image,
        map_x,
        map_y,
        interpolation=interpolation,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=border_value,
    )


def _warp_affine_image(
    image: np.ndarray,
    matrix: np.ndarray,
    size: tuple[int, int],
    interpolation: int,
    border_value,
    backend_api: str,
) -> np.ndarray:
    if backend_api == "cuda":
        try:
            src_gpu = cv2.cuda_GpuMat()
            src_gpu.upload(image)
            rendered_gpu = cv2.cuda.warpAffine(
                src_gpu,
                matrix,
                size,
                flags=interpolation,
                borderMode=cv2.BORDER_CONSTANT,
                borderValue=border_value,
            )
            return rendered_gpu.download()
        except Exception:
            backend_api = "cpu"

    if backend_api == "opencl" and cv2.ocl.useOpenCL():
        try:
            rendered = cv2.warpAffine(
                cv2.UMat(image),
                matrix,
                size,
                flags=interpolation,
                borderMode=cv2.BORDER_CONSTANT,
                borderValue=border_value,
            )
            return rendered.get()
        except Exception:
            backend_api = "cpu"

    return cv2.warpAffine(
        image,
        matrix,
        size,
        flags=interpolation,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=border_value,
    )
