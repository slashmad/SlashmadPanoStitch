from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path

import numpy as np

from panostitch.core.exporter import resolve_export_format
from panostitch.core.render_pipeline import render_corrected_rgb, render_panorama_adjusted_rgb, scaled_frame_to_bounds
from panostitch.domain.models import FrameGeometry
from panostitch.io.profile_catalog import sony_a7r3_sigma_15mm_preset


class RenderPipelineTests(unittest.TestCase):
    def test_scaled_frame_respects_bounds(self) -> None:
        frame = scaled_frame_to_bounds(FrameGeometry(width=3840, height=2160), max_width=1280, max_height=720)
        self.assertEqual(frame.width, 1280)
        self.assertEqual(frame.height, 720)

    def test_render_corrected_rgb_returns_expected_shape(self) -> None:
        preset = sony_a7r3_sigma_15mm_preset()
        source = np.zeros((320, 640, 3), dtype=np.uint8)
        source[:, :, 0] = np.linspace(0, 255, 640, dtype=np.uint8)
        source[:, :, 1] = 64
        source[:, :, 2] = np.linspace(255, 0, 640, dtype=np.uint8)

        rendered, metrics = render_corrected_rgb(source, preset, output_frame=FrameGeometry(width=320, height=180))
        self.assertEqual(rendered.shape, (180, 320, 3))
        self.assertGreater(metrics["valid_fraction"], 0.30)

    def test_resolve_export_format_preserves_raster_and_falls_back_for_raw(self) -> None:
        self.assertEqual(resolve_export_format(Path("image.JPG"), "preserve-raster"), "jpg")
        self.assertEqual(resolve_export_format(Path("image.ARW"), "preserve-raster"), "tiff")

    def test_render_corrected_rgb_keeps_shape_with_post_rotation(self) -> None:
        preset = replace(sony_a7r3_sigma_15mm_preset(), post_rotate_deg=22.5, safe_margin=0.08)
        source = np.full((300, 500, 3), 127, dtype=np.uint8)
        rendered, metrics = render_corrected_rgb(source, preset, output_frame=FrameGeometry(width=250, height=150))
        self.assertEqual(rendered.shape, (150, 250, 3))
        self.assertGreater(metrics["valid_fraction"], 0.10)

    def test_render_corrected_rgb_keeps_shape_with_curve_straighten(self) -> None:
        preset = replace(sony_a7r3_sigma_15mm_preset(), curve_straighten=0.7, curve_anchor_y=-0.8, curve_span=0.4)
        source = np.full((300, 500, 3), 127, dtype=np.uint8)
        rendered, metrics = render_corrected_rgb(source, preset, output_frame=FrameGeometry(width=250, height=150))
        self.assertEqual(rendered.shape, (150, 250, 3))
        self.assertGreater(metrics["valid_fraction"], 0.05)

    def test_render_panorama_adjusted_rgb_returns_expected_shape(self) -> None:
        preset = replace(sony_a7r3_sigma_15mm_preset(), pitch_deg=0.0, roll_deg=0.0, yaw_deg=0.0, safe_margin=0.0)
        source = np.zeros((240, 480, 3), dtype=np.uint8)
        source[:, :, 1] = np.linspace(0, 255, 480, dtype=np.uint8)
        rendered, metrics = render_panorama_adjusted_rgb(source, preset, output_frame=FrameGeometry(width=320, height=160))
        self.assertEqual(rendered.shape, (160, 320, 3))
        self.assertGreater(metrics["valid_fraction"], 0.95)

    def test_render_panorama_adjusted_rgb_yaw_moves_content(self) -> None:
        base_preset = replace(sony_a7r3_sigma_15mm_preset(), pitch_deg=0.0, roll_deg=0.0, yaw_deg=0.0, safe_margin=0.0)
        source = np.zeros((200, 400, 3), dtype=np.uint8)
        source[:, :160, 0] = 255
        source[:, 160:, 2] = 255

        centered, _ = render_panorama_adjusted_rgb(source, base_preset, output_frame=FrameGeometry(width=200, height=100))
        shifted, _ = render_panorama_adjusted_rgb(
            source,
            replace(base_preset, yaw_deg=45.0),
            output_frame=FrameGeometry(width=200, height=100),
        )

        self.assertFalse(np.array_equal(centered, shifted))


if __name__ == "__main__":
    unittest.main()
