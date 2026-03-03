from __future__ import annotations

import unittest
from pathlib import Path

from panostitch.core.batch_plan import build_batch_job_summary
from panostitch.core.fisheye_math import estimate_valid_region, normalize, rotation_matrix, sample_source_uv
from panostitch.io.profile_catalog import sony_a7r3_sigma_15mm_preset


class FisheyeMathTests(unittest.TestCase):
    def test_normalize_returns_unit_vector(self) -> None:
        x, y, z = normalize((3.0, 4.0, 12.0))
        self.assertAlmostEqual((x * x) + (y * y) + (z * z), 1.0)

    def test_rotation_matrix_is_identity_at_zero(self) -> None:
        matrix = rotation_matrix(0.0, 0.0, 0.0)
        self.assertEqual(matrix, [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])

    def test_center_preview_maps_to_source(self) -> None:
        preset = sony_a7r3_sigma_15mm_preset()
        uv = sample_source_uv(preset, 0.0, 0.0)
        self.assertIsNotNone(uv)
        assert uv is not None
        self.assertTrue(0.0 <= uv[0] <= 1.0)
        self.assertTrue(0.0 <= uv[1] <= 1.0)

    def test_output_horizontal_direction_matches_expected_orientation(self) -> None:
        preset = sony_a7r3_sigma_15mm_preset()
        uv_left = sample_source_uv(preset, -0.5, 0.0)
        uv_right = sample_source_uv(preset, 0.5, 0.0)
        self.assertIsNotNone(uv_left)
        self.assertIsNotNone(uv_right)
        assert uv_left is not None and uv_right is not None
        self.assertGreater(uv_left[0], 0.5)
        self.assertLess(uv_right[0], 0.5)

    def test_output_vertical_direction_matches_expected_orientation(self) -> None:
        preset = sony_a7r3_sigma_15mm_preset()
        uv_top = sample_source_uv(preset, 0.0, -0.5)
        uv_bottom = sample_source_uv(preset, 0.0, 0.5)
        self.assertIsNotNone(uv_top)
        self.assertIsNotNone(uv_bottom)
        assert uv_top is not None and uv_bottom is not None
        self.assertLess(uv_top[1], 0.5)
        self.assertGreater(uv_bottom[1], 0.5)

    def test_valid_region_fraction_is_reasonable(self) -> None:
        preset = sony_a7r3_sigma_15mm_preset()
        coverage = estimate_valid_region(preset)
        self.assertGreater(coverage["valid_fraction"], 0.50)

    def test_raw_inputs_default_to_linear_dng_in_batch_summary(self) -> None:
        preset = sony_a7r3_sigma_15mm_preset()
        summary = build_batch_job_summary(
            preset,
            [
                Path("DSC0001.ARW"),
                Path("DSC0002.JPG"),
            ],
        )
        self.assertEqual(summary["outputs"][0]["export_mode"], "linear-dng")
        self.assertEqual(summary["outputs"][1]["export_mode"], "jpg")


if __name__ == "__main__":
    unittest.main()
