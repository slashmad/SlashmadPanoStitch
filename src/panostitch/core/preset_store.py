from __future__ import annotations

import json
from pathlib import Path

from panostitch.domain.models import CorrectionPreset


def load_preset(path: Path) -> CorrectionPreset:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return CorrectionPreset.from_dict(data)


def save_preset(preset: CorrectionPreset, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(preset.to_dict(), handle, indent=2)
        handle.write("\n")
