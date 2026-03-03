from __future__ import annotations

import unittest

from panostitch.io.lens_db import (
    find_lens_database_match,
    load_available_lens_database,
    normalize_camera_name,
    normalize_import_metadata,
)


class LensDatabaseTests(unittest.TestCase):
    def test_normalize_import_metadata_uses_custom_sigma_entry(self) -> None:
        camera_model, lens_model = normalize_import_metadata(
            "SONY ILCE-7RM3",
            "15mm F1.4 DG DN DIAGONAL FISHEYE | Art 024",
        )
        self.assertEqual(camera_model, "Sony A7R III")
        self.assertEqual(lens_model, "Sigma 15mm F1.4 DG DN Diagonal Fisheye | Art")

    def test_normalize_camera_name_maps_known_sony_body(self) -> None:
        self.assertEqual(normalize_camera_name("SONY ILCE-7RM3"), "Sony A7R III")

    def test_available_lens_database_contains_bundled_and_lensfun_entries(self) -> None:
        entries = load_available_lens_database()
        self.assertTrue(any(entry.get("source") == "panostitch" for entry in entries))
        self.assertTrue(any(entry.get("source") == "lensfun" for entry in entries))

    def test_find_lens_database_match_prefers_custom_entry(self) -> None:
        match = find_lens_database_match("SONY ILCE-7RM3", "15mm F1.4 DG DN DIAGONAL FISHEYE | Art 024")
        self.assertIsNotNone(match)
        assert match is not None
        self.assertEqual(match.entry_id, "sigma_15mm_f14_dg_dn_diagonal_fisheye_art_sony_e")


if __name__ == "__main__":
    unittest.main()
