from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
from PIL import Image

from panostitch.io.image_loader import load_image, read_image_asset_metadata
from panostitch.io.lens_db import normalize_import_metadata


class ImageLoaderTests(unittest.TestCase):
    def test_read_image_asset_metadata_extracts_camera_and_lens_from_exif(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "sample.jpg"
            image = Image.new("RGB", (64, 32), color=(12, 34, 56))
            exif = Image.Exif()
            exif[271] = "Sony"
            exif[272] = "ILCE-7RM3"
            exif[42036] = "Sigma 15mm F1.4 DG DN Diagonal Fisheye | Art"
            image.save(image_path, exif=exif)

            asset = read_image_asset_metadata(image_path)

        self.assertEqual(asset.path, image_path)
        self.assertEqual(asset.camera_model, "Sony A7R III")
        self.assertEqual(asset.lens_model, "Sigma 15mm F1.4 DG DN Diagonal Fisheye | Art")
        self.assertEqual(asset.width, 64)
        self.assertEqual(asset.height, 32)

    def test_read_image_asset_metadata_extracts_fields_from_tiff_based_raw(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "sample.dng"
            image_path.write_bytes(
                self._build_test_tiff_bytes(
                    make="Sony",
                    model="ILCE-7RM3",
                    lens="Sigma 15mm F1.4 DG DN Diagonal Fisheye | Art",
                    width=2600,
                    height=3900,
                )
            )

            asset = read_image_asset_metadata(image_path)

        self.assertEqual(asset.camera_model, "Sony A7R III")
        self.assertEqual(asset.lens_model, "Sigma 15mm F1.4 DG DN Diagonal Fisheye | Art")
        self.assertEqual(asset.width, 2600)
        self.assertEqual(asset.height, 3900)

    def test_normalize_lens_display_name_prefixes_sigma_when_make_is_missing(self) -> None:
        _camera_model, lens_model = normalize_import_metadata("SONY ILCE-7RM3", "15mm F1.4 DG DN DIAGONAL FISHEYE | Art 024")
        self.assertEqual(lens_model, "Sigma 15mm F1.4 DG DN Diagonal Fisheye | Art")

    def test_load_raw_image_respects_original_orientation_metadata(self) -> None:
        raw_handle = mock.MagicMock()
        raw_handle.sizes.width = 7952
        raw_handle.sizes.height = 5304
        raw_handle.postprocess.return_value = np.zeros((20, 10, 3), dtype=np.uint8)

        context_manager = mock.MagicMock()
        context_manager.__enter__.return_value = raw_handle
        context_manager.__exit__.return_value = None

        with mock.patch("panostitch.io.image_loader.rawpy.imread", return_value=context_manager):
            with mock.patch("panostitch.io.image_loader._read_tiff_metadata", return_value=("Sony A7R III", "Sigma 15mm F1.4", 7952, 5304)):
                loaded = load_image(Path("sample.ARW"), max_edge=2200)

        self.assertEqual(loaded.width, 10)
        self.assertEqual(loaded.height, 20)
        _args, kwargs = raw_handle.postprocess.call_args
        self.assertNotIn("user_flip", kwargs)

    def _build_test_tiff_bytes(self, make: str, model: str, lens: str, width: int, height: int) -> bytes:
        endian = "<"
        ifd0_offset = 8
        ifd0_entry_count = 5
        ifd0_size = 2 + (ifd0_entry_count * 12) + 4
        make_bytes = make.encode() + b"\x00"
        model_bytes = model.encode() + b"\x00"
        lens_bytes = lens.encode() + b"\x00"

        make_offset = ifd0_offset + ifd0_size
        model_offset = make_offset + len(make_bytes)
        exif_ifd_offset = model_offset + len(model_bytes)
        exif_ifd_entry_count = 3
        exif_ifd_size = 2 + (exif_ifd_entry_count * 12) + 4
        lens_offset = exif_ifd_offset + exif_ifd_size

        payload = bytearray()
        payload.extend(b"II")
        payload.extend(struct.pack(f"{endian}H", 42))
        payload.extend(struct.pack(f"{endian}I", ifd0_offset))

        payload.extend(struct.pack(f"{endian}H", ifd0_entry_count))
        payload.extend(struct.pack(f"{endian}HHII", 256, 4, 1, width))
        payload.extend(struct.pack(f"{endian}HHII", 257, 4, 1, height))
        payload.extend(struct.pack(f"{endian}HHII", 271, 2, len(make_bytes), make_offset))
        payload.extend(struct.pack(f"{endian}HHII", 272, 2, len(model_bytes), model_offset))
        payload.extend(struct.pack(f"{endian}HHII", 34665, 4, 1, exif_ifd_offset))
        payload.extend(struct.pack(f"{endian}I", 0))

        payload.extend(make_bytes)
        payload.extend(model_bytes)

        payload.extend(struct.pack(f"{endian}H", exif_ifd_entry_count))
        payload.extend(struct.pack(f"{endian}HHII", 42036, 2, len(lens_bytes), lens_offset))
        payload.extend(struct.pack(f"{endian}HHII", 40962, 4, 1, width))
        payload.extend(struct.pack(f"{endian}HHII", 40963, 4, 1, height))
        payload.extend(struct.pack(f"{endian}I", 0))
        payload.extend(lens_bytes)

        return bytes(payload)


if __name__ == "__main__":
    unittest.main()
