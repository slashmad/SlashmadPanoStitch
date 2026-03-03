from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from panostitch.core.panorama_stitch import PanoramaStitchSettings
from panostitch.core.runtime_paths import panorama_preview_cache_dir
from panostitch.domain.models import CorrectionPreset


@dataclass(slots=True)
class PanoramaPreviewCacheEntry:
    rgb_data: np.ndarray
    metadata: dict[str, Any]


def build_panorama_cache_key(
    image_paths: list[Path],
    settings: PanoramaStitchSettings,
    use_fisheye_precorrection: bool,
    fisheye_preset: CorrectionPreset,
) -> str:
    payload = {
        "images": [
            {
                "path": str(path),
                "mtime_ns": path.stat().st_mtime_ns,
                "size": path.stat().st_size,
            }
            for path in image_paths
        ],
        "settings": asdict(settings),
        "use_fisheye_precorrection": use_fisheye_precorrection,
        "fisheye_preset": fisheye_preset.to_dict() if use_fisheye_precorrection else None,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_panorama_preview_cache(cache_key: str, project_root: Path | None = None) -> PanoramaPreviewCacheEntry | None:
    cache_dir = panorama_preview_cache_dir(project_root)
    image_path = cache_dir / f"{cache_key}.npz"
    metadata_path = cache_dir / f"{cache_key}.json"
    if not image_path.exists() or not metadata_path.exists():
        return None

    with metadata_path.open("r", encoding="utf-8") as handle:
        metadata = json.load(handle)
    with np.load(image_path) as archive:
        rgb_data = archive["rgb"]
    return PanoramaPreviewCacheEntry(rgb_data=rgb_data, metadata=metadata)


def save_panorama_preview_cache(
    cache_key: str,
    rgb_data: np.ndarray,
    metadata: dict[str, Any],
    project_root: Path | None = None,
) -> None:
    cache_dir = panorama_preview_cache_dir(project_root)
    image_path = cache_dir / f"{cache_key}.npz"
    metadata_path = cache_dir / f"{cache_key}.json"

    np.savez_compressed(image_path, rgb=np.ascontiguousarray(rgb_data))
    with metadata_path.open("w", encoding="utf-8") as handle:
        json.dump(metadata, handle, indent=2, sort_keys=True)


def clear_panorama_preview_cache(project_root: Path | None = None) -> None:
    cache_dir = panorama_preview_cache_dir(project_root)
    for path in cache_dir.glob("*"):
        if path.is_file():
            path.unlink(missing_ok=True)
