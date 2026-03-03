from __future__ import annotations

import json
from dataclasses import dataclass, replace
from functools import lru_cache
from importlib.resources import files
from typing import Any

import lensfunpy

from panostitch.domain.models import CorrectionPreset


@dataclass(slots=True)
class LensDatabaseMatch:
    entry_id: str
    lens_display: str
    entry: dict[str, Any]


@lru_cache(maxsize=1)
def load_lens_database() -> list[dict[str, Any]]:
    db_path = files("panostitch").joinpath("data/lens_db.json")
    with db_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


@lru_cache(maxsize=1)
def load_available_lens_database() -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for entry in load_lens_database():
        entry_id = str(entry["id"])
        seen_ids.add(entry_id)
        entries.append(entry)

    for entry in _load_lensfun_entries():
        entry_id = str(entry["id"])
        if entry_id in seen_ids:
            continue
        seen_ids.add(entry_id)
        entries.append(entry)

    return entries


@lru_cache(maxsize=1)
def load_available_camera_names() -> dict[str, str]:
    names: dict[str, str] = {}

    for entry in load_available_lens_database():
        camera_display = entry.get("camera_display")
        if not camera_display:
            continue

        for alias in entry.get("camera_aliases") or []:
            key = _normalize_key(alias)
            if key:
                names[key] = str(camera_display)

    for camera in lensfunpy.Database().cameras:
        maker = getattr(camera, "maker", None)
        model = getattr(camera, "model", None)
        display = _format_camera_display(maker, model)
        for alias in filter(None, [display, model]):
            key = _normalize_key(alias)
            if key and key not in names:
                names[key] = display

    return names


def find_lens_database_match(camera_model: str | None, lens_model: str | None) -> LensDatabaseMatch | None:
    lens_key = _normalize_key(lens_model)
    if lens_key is None:
        return None

    camera_key = _normalize_key(camera_model)
    best: tuple[int, int, dict[str, Any]] | None = None

    for entry in load_available_lens_database():
        aliases = [entry.get("lens_display", ""), *(entry.get("lens_aliases") or [])]
        matching_aliases = [alias for alias in aliases if _alias_matches(_normalize_key(alias), lens_key)]
        if not matching_aliases:
            continue

        camera_aliases = entry.get("camera_aliases") or []
        camera_match = False
        if camera_key is not None and camera_aliases:
            camera_match = any(_normalize_key(alias) == camera_key for alias in camera_aliases)

        source_bonus = 2 if entry.get("source") == "panostitch" else 0
        score = source_bonus + (2 if camera_match else 1)
        alias_length = max(len(alias) for alias in matching_aliases)
        candidate = (score, alias_length, entry)
        if best is None or candidate > best:
            best = candidate

    if best is None:
        return None

    entry = best[2]
    return LensDatabaseMatch(
        entry_id=str(entry["id"]),
        lens_display=str(entry["lens_display"]),
        entry=entry,
    )


def normalize_import_metadata(camera_model: str | None, lens_model: str | None) -> tuple[str | None, str | None]:
    match = find_lens_database_match(camera_model, lens_model)
    normalized_camera = normalize_camera_name(camera_model, match)
    if match is not None:
        return normalized_camera, match.lens_display

    if lens_model is None:
        return normalized_camera, None

    return normalized_camera, _normalize_generic_lens_name(lens_model)


def normalize_camera_name(camera_model: str | None, match: LensDatabaseMatch | None = None) -> str | None:
    if match is not None:
        camera_display = match.entry.get("camera_display")
        if camera_display:
            return str(camera_display)

    key = _normalize_key(camera_model)
    if key is None:
        return None

    return load_available_camera_names().get(key, _normalize_generic_camera_name(camera_model))


def build_seed_preset_from_match(base_preset: CorrectionPreset, match: LensDatabaseMatch | None) -> CorrectionPreset:
    if match is None:
        return base_preset

    entry = match.entry
    camera_display = str(entry.get("camera_display") or base_preset.camera.model)
    lens = replace(
        base_preset.lens,
        manufacturer=str(entry.get("manufacturer") or base_preset.lens.manufacturer),
        model=str(entry.get("lens_display") or base_preset.lens.model),
        mount=str(entry.get("mount") or base_preset.lens.mount),
        sensor_format=str(entry.get("sensor_format") or base_preset.lens.sensor_format),
        projection=str(entry.get("projection") or base_preset.lens.projection),
        fisheye_mapping=str(entry.get("fisheye_mapping") or base_preset.lens.fisheye_mapping),
        focal_length_mm=float(entry.get("focal_length_mm") or base_preset.lens.focal_length_mm),
        diagonal_fov_deg=float(entry.get("diagonal_fov_deg") or base_preset.lens.diagonal_fov_deg),
        lensfun_name=entry.get("lensfun_name") if "lensfun_name" in entry else base_preset.lens.lensfun_name,
        notes=str(entry.get("notes") or base_preset.lens.notes),
    )

    camera = replace(
        base_preset.camera,
        manufacturer=str(entry.get("camera_manufacturer") or base_preset.camera.manufacturer),
        model=camera_display,
        sensor_format=str(entry.get("sensor_format") or base_preset.camera.sensor_format),
    )

    preset = replace(base_preset, camera=camera, lens=lens)
    overrides = entry.get("preset_overrides") or {}
    allowed = {
        "output_projection",
        "horizontal_fov_deg",
        "yaw_deg",
        "pitch_deg",
        "roll_deg",
        "zoom",
        "vertical_shift",
        "post_rotate_deg",
        "curve_straighten",
        "curve_anchor_y",
        "curve_span",
        "safe_margin",
    }
    update_values = {key: value for key, value in overrides.items() if key in allowed}
    return replace(preset, **update_values)


def _normalize_key(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = "".join(character.lower() if character.isalnum() else " " for character in value.strip())
    normalized = " ".join(cleaned.split())
    return normalized or None


def _alias_matches(alias_key: str | None, lens_key: str) -> bool:
    if alias_key is None:
        return False
    return alias_key == lens_key or alias_key in lens_key or lens_key in alias_key


def _load_lensfun_entries() -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    db = lensfunpy.Database()
    cameras_by_mount: dict[str, list[Any]] = {}
    for camera in db.cameras:
        mount = getattr(camera, "mount", None)
        if mount:
            cameras_by_mount.setdefault(str(mount), []).append(camera)

    for lens in db.lenses:
        maker = getattr(lens, "maker", None) or ""
        model = getattr(lens, "model", None) or ""
        mounts = [str(mount) for mount in (getattr(lens, "mounts", None) or [])]
        camera_aliases = _build_camera_aliases_for_mounts(cameras_by_mount, mounts)
        projection, mapping = _map_lensfun_type(getattr(lens, "type", None))

        entries.append(
            {
                "id": _normalize_id(f"lensfun_{maker}_{model}_{'_'.join(mounts) or 'nomount'}"),
                "source": "lensfun",
                "manufacturer": str(maker) if maker else "Unknown",
                "camera_display": None,
                "camera_aliases": camera_aliases,
                "lens_display": _format_lens_display(maker, model),
                "lens_aliases": [str(model)] if model else [],
                "mount": mounts[0] if mounts else "",
                "sensor_format": _crop_factor_to_sensor_format(getattr(lens, "crop_factor", None)),
                "projection": projection,
                "fisheye_mapping": mapping,
                "focal_length_mm": float(getattr(lens, "min_focal", 15.0) or 15.0),
                "diagonal_fov_deg": _estimate_diagonal_fov(getattr(lens, "type", None)),
                "lensfun_name": str(model) if model else None,
                "notes": "Imported from local Lensfun database.",
            }
        )

    return entries


def _build_camera_aliases_for_mounts(cameras_by_mount: dict[str, list[Any]], mounts: list[str]) -> list[str]:
    aliases: list[str] = []
    seen: set[str] = set()
    for mount in mounts:
        for camera in cameras_by_mount.get(mount, []):
            display = _format_camera_display(getattr(camera, "maker", None), getattr(camera, "model", None))
            model = getattr(camera, "model", None)
            for value in filter(None, [display, model]):
                if value not in seen:
                    seen.add(value)
                    aliases.append(value)
    return aliases


def _format_lens_display(maker: str | None, model: str | None) -> str:
    if maker and model and str(model).lower().startswith(str(maker).lower()):
        return str(model)
    if maker and model:
        return f"{maker} {model}"
    return str(model or maker or "Unknown Lens")


def _format_camera_display(maker: str | None, model: str | None) -> str:
    if maker and model and str(model).lower().startswith(str(maker).lower()):
        return str(model)
    if maker and model:
        return f"{maker} {model}"
    return str(model or maker or "")


def _normalize_generic_lens_name(lens_model: str | None) -> str | None:
    if lens_model is None:
        return None

    lowered = lens_model.lower()
    if lowered.startswith("sigma "):
        return lens_model

    if any(token in lowered for token in (" dg dn", " dg ", "| art", "| sports", "| contemporary")):
        return f"Sigma {lens_model}"

    return lens_model


def _normalize_generic_camera_name(camera_model: str | None) -> str | None:
    if camera_model is None:
        return None

    words = camera_model.strip().split()
    if not words:
        return None

    first = words[0].capitalize() if words[0].isupper() else words[0]
    remainder = " ".join(words[1:])
    return f"{first} {remainder}".strip()


def _normalize_id(value: str) -> str:
    normalized = "".join(character.lower() if character.isalnum() else "_" for character in value)
    while "__" in normalized:
        normalized = normalized.replace("__", "_")
    return normalized.strip("_")


def _crop_factor_to_sensor_format(crop_factor: Any) -> str:
    try:
        factor = float(crop_factor)
    except (TypeError, ValueError):
        return "unknown"

    if factor <= 1.05:
        return "full-frame"
    if factor <= 1.35:
        return "aps-h"
    if factor <= 1.65:
        return "aps-c"
    if factor <= 2.1:
        return "micro-four-thirds"
    return "small-sensor"


def _map_lensfun_type(lens_type: Any) -> tuple[str, str]:
    type_name = getattr(lens_type, "name", str(lens_type))
    if type_name == "FISHEYE_EQUISOLID":
        return "diagonal_fisheye", "equisolid"
    if type_name == "FISHEYE_STEREOGRAPHIC":
        return "diagonal_fisheye", "stereographic"
    if type_name == "FISHEYE":
        return "diagonal_fisheye", "equidistant"
    return "rectilinear", "equisolid"


def _estimate_diagonal_fov(lens_type: Any) -> float:
    type_name = getattr(lens_type, "name", str(lens_type))
    if type_name.startswith("FISHEYE"):
        return 180.0
    return 110.0
