from __future__ import annotations

from panostitch.domain.models import CameraProfile, CorrectionPreset, FrameGeometry, LensProfile


def sony_a7r3_sigma_15mm_preset() -> CorrectionPreset:
    camera = CameraProfile(
        manufacturer="Sony",
        model="Sony A7R III",
        sensor_format="full-frame",
    )
    lens = LensProfile(
        manufacturer="Sigma",
        model="Sigma 15mm F1.4 DG DN Diagonal Fisheye | Art",
        mount="Sony E",
        sensor_format="full-frame",
        projection="diagonal_fisheye",
        fisheye_mapping="equisolid",
        focal_length_mm=15.0,
        diagonal_fov_deg=180.0,
        lensfun_name=None,
        notes="Manual bootstrap profile. Start point until measured calibration data is available.",
    )
    return CorrectionPreset(
        name="Sigma 15mm A7R III horizontal edge",
        camera=camera,
        lens=lens,
        output_frame=FrameGeometry(width=3840, height=2160),
        output_projection="cylindrical",
        horizontal_fov_deg=118.0,
        yaw_deg=0.0,
        pitch_deg=-7.5,
        roll_deg=0.0,
        zoom=1.04,
        vertical_shift=-0.02,
        post_rotate_deg=0.0,
        curve_straighten=0.0,
        curve_anchor_y=-0.75,
        curve_span=0.55,
        safe_margin=0.02,
        notes="Start preset for lifting a slightly upward-tilted fisheye capture into a flatter lower edge.",
    )
