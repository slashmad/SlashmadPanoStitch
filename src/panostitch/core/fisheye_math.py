from __future__ import annotations

import math
from typing import Iterable

from panostitch.domain.models import CorrectionPreset, FrameGeometry, LensProfile


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def normalize(vector: Iterable[float]) -> tuple[float, float, float]:
    x, y, z = vector
    length = math.sqrt((x * x) + (y * y) + (z * z))
    if length == 0.0:
        raise ValueError("Cannot normalize a zero-length vector.")
    return (x / length, y / length, z / length)


def matmul3(left: list[list[float]], right: list[list[float]]) -> list[list[float]]:
    result: list[list[float]] = []
    for row in left:
        result.append(
            [
                (row[0] * right[0][column]) + (row[1] * right[1][column]) + (row[2] * right[2][column])
                for column in range(3)
            ]
        )
    return result


def apply_matrix(matrix: list[list[float]], vector: tuple[float, float, float]) -> tuple[float, float, float]:
    x, y, z = vector
    return (
        (matrix[0][0] * x) + (matrix[0][1] * y) + (matrix[0][2] * z),
        (matrix[1][0] * x) + (matrix[1][1] * y) + (matrix[1][2] * z),
        (matrix[2][0] * x) + (matrix[2][1] * y) + (matrix[2][2] * z),
    )


def rotation_matrix(yaw_deg: float, pitch_deg: float, roll_deg: float) -> list[list[float]]:
    yaw = math.radians(yaw_deg)
    pitch = math.radians(pitch_deg)
    roll = math.radians(roll_deg)

    cy = math.cos(yaw)
    sy = math.sin(yaw)
    cp = math.cos(pitch)
    sp = math.sin(pitch)
    cr = math.cos(roll)
    sr = math.sin(roll)

    rotate_yaw = [
        [cy, 0.0, sy],
        [0.0, 1.0, 0.0],
        [-sy, 0.0, cy],
    ]
    rotate_pitch = [
        [1.0, 0.0, 0.0],
        [0.0, cp, -sp],
        [0.0, sp, cp],
    ]
    rotate_roll = [
        [cr, -sr, 0.0],
        [sr, cr, 0.0],
        [0.0, 0.0, 1.0],
    ]
    return matmul3(rotate_roll, matmul3(rotate_pitch, rotate_yaw))


def ray_from_output(
    x_ndc: float,
    y_ndc: float,
    frame: FrameGeometry,
    projection: str,
    horizontal_fov_deg: float,
    zoom: float,
    vertical_shift: float,
) -> tuple[float, float, float]:
    aspect = frame.aspect_ratio
    h_scale = math.tan(math.radians(horizontal_fov_deg) / 2.0) / zoom
    v_scale = h_scale / aspect
    y_adjusted = (-y_ndc) + vertical_shift

    if projection == "rectilinear":
        return normalize((x_ndc * h_scale, y_adjusted * v_scale, 1.0))

    if projection == "cylindrical":
        theta = x_ndc * (math.radians(horizontal_fov_deg) / 2.0) / zoom
        return normalize((math.sin(theta), y_adjusted * v_scale, math.cos(theta)))

    raise ValueError(f"Unsupported projection: {projection}")


def fisheye_radius(theta: float, lens: LensProfile) -> float:
    theta_limit = math.radians(lens.diagonal_fov_deg) / 2.0
    theta = clamp(theta, 0.0, theta_limit)

    if lens.fisheye_mapping == "equidistant":
        return theta / theta_limit
    if lens.fisheye_mapping == "equisolid":
        return math.sin(theta / 2.0) / math.sin(theta_limit / 2.0)
    if lens.fisheye_mapping == "stereographic":
        return math.tan(theta / 2.0) / math.tan(theta_limit / 2.0)
    if lens.fisheye_mapping == "orthographic":
        return math.sin(theta) / math.sin(theta_limit)
    raise ValueError(f"Unsupported fisheye mapping: {lens.fisheye_mapping}")


def ray_to_source_uv(
    ray: tuple[float, float, float],
    lens: LensProfile,
    source_frame: FrameGeometry,
) -> tuple[float, float] | None:
    x, y, z = normalize(ray)
    if z <= 0.0:
        return None

    theta = math.acos(clamp(z, -1.0, 1.0))
    phi = math.atan2(y, x)
    radius = fisheye_radius(theta, lens)

    half_diagonal = math.sqrt((source_frame.width / 2.0) ** 2 + (source_frame.height / 2.0) ** 2)
    sensor_x = -math.cos(phi) * radius * half_diagonal
    sensor_y = math.sin(phi) * radius * half_diagonal

    u = 0.5 + (sensor_x / source_frame.width)
    v = 0.5 - (sensor_y / source_frame.height)

    if not (0.0 <= u <= 1.0 and 0.0 <= v <= 1.0):
        return None
    return (u, v)


def sample_source_uv(
    preset: CorrectionPreset,
    x_ndc: float,
    y_ndc: float,
    source_frame: FrameGeometry | None = None,
) -> tuple[float, float] | None:
    output_ray = ray_from_output(
        x_ndc=x_ndc,
        y_ndc=y_ndc,
        frame=preset.output_frame,
        projection=preset.output_projection,
        horizontal_fov_deg=preset.horizontal_fov_deg,
        zoom=preset.zoom,
        vertical_shift=preset.vertical_shift,
    )
    matrix = rotation_matrix(preset.yaw_deg, preset.pitch_deg, preset.roll_deg)
    source_ray = apply_matrix(matrix, output_ray)
    return ray_to_source_uv(source_ray, preset.lens, source_frame or preset.output_frame)


def estimate_valid_region(
    preset: CorrectionPreset,
    samples: int = 11,
    source_frame: FrameGeometry | None = None,
) -> dict[str, float]:
    valid = 0
    total = 0

    for y_index in range(samples):
        for x_index in range(samples):
            total += 1
            x_ndc = -1.0 + (2.0 * x_index / (samples - 1))
            y_ndc = -1.0 + (2.0 * y_index / (samples - 1))
            if sample_source_uv(preset, x_ndc, y_ndc, source_frame=source_frame) is not None:
                valid += 1

    return {
        "sample_count": float(total),
        "valid_sample_count": float(valid),
        "valid_fraction": valid / total,
    }
