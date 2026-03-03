from __future__ import annotations

import os
from pathlib import Path


def resolve_local_root(project_root: Path | None = None) -> Path:
    configured = os.environ.get("PANOSTITCH_LOCAL_ROOT")
    if configured:
        return Path(configured).expanduser()

    preferred = Path("/run/media/stolpee/localprog/panostitch")
    if preferred.exists():
        return preferred

    if project_root is not None:
        return project_root / ".panostitch-local"

    return Path.cwd() / ".panostitch-local"


def panorama_preview_cache_dir(project_root: Path | None = None) -> Path:
    preferred = resolve_local_root(project_root) / "tmp" / "panorama-preview-cache"
    try:
        preferred.mkdir(parents=True, exist_ok=True)
        return preferred
    except PermissionError:
        fallback_root = project_root if project_root is not None else Path.cwd()
        fallback = fallback_root / ".panostitch-local" / "tmp" / "panorama-preview-cache"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback
