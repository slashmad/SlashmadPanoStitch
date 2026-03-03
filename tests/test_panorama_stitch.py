from __future__ import annotations

import unittest

import cv2
import numpy as np

from panostitch.core.panorama_stitch import PanoramaStitchSettings, scale_rgb_to_max_edge, stitch_rgb_images, stitch_status_name


class PanoramaStitchTests(unittest.TestCase):
    def test_scale_rgb_to_max_edge_downsizes_larger_input(self) -> None:
        rgb = np.zeros((1200, 2400, 3), dtype=np.uint8)
        scaled = scale_rgb_to_max_edge(rgb, 1200)
        self.assertEqual(scaled.shape[1], 1200)
        self.assertEqual(scaled.shape[0], 600)

    def test_scale_rgb_to_max_edge_keeps_smaller_input(self) -> None:
        rgb = np.zeros((400, 600, 3), dtype=np.uint8)
        scaled = scale_rgb_to_max_edge(rgb, 1200)
        self.assertEqual(scaled.shape, rgb.shape)

    def test_stitch_status_name_maps_known_opencv_codes(self) -> None:
        self.assertEqual(stitch_status_name(cv2.Stitcher_OK), "Stitch successful")
        self.assertEqual(stitch_status_name(cv2.Stitcher_ERR_NEED_MORE_IMGS), "Need more overlapping images")

    def test_stitch_rgb_images_rejects_single_input(self) -> None:
        settings = PanoramaStitchSettings()
        with self.assertRaisesRegex(ValueError, "Select at least two overlapping images"):
            stitch_rgb_images([np.zeros((120, 240, 3), dtype=np.uint8)], settings)


if __name__ == "__main__":
    unittest.main()
