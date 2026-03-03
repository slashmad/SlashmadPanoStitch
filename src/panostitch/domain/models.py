from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

FisheyeMapping = Literal["equidistant", "equisolid", "stereographic", "orthographic"]
ProjectionMode = Literal["rectilinear", "cylindrical"]
ExportMode = Literal["preserve-raster", "linear-dng", "tiff", "jpeg"]


@dataclass(slots=True)
class CameraProfile:
    manufacturer: str
    model: str
    sensor_format: str


@dataclass(slots=True)
class LensProfile:
    manufacturer: str
    model: str
    mount: str
    sensor_format: str
    projection: str = "diagonal_fisheye"
    fisheye_mapping: FisheyeMapping = "equisolid"
    focal_length_mm: float = 15.0
    diagonal_fov_deg: float = 180.0
    lensfun_name: str | None = None
    notes: str = ""


@dataclass(slots=True)
class FrameGeometry:
    width: int
    height: int

    @property
    def aspect_ratio(self) -> float:
        return self.width / self.height


@dataclass(slots=True)
class CorrectionPreset:
    name: str
    camera: CameraProfile
    lens: LensProfile
    output_frame: FrameGeometry
    output_projection: ProjectionMode = "cylindrical"
    horizontal_fov_deg: float = 120.0
    yaw_deg: float = 0.0
    pitch_deg: float = -8.0
    roll_deg: float = 0.0
    zoom: float = 1.0
    vertical_shift: float = 0.0
    post_rotate_deg: float = 0.0
    curve_straighten: float = 0.0
    curve_anchor_y: float = -0.75
    curve_span: float = 0.55
    safe_margin: float = 0.02
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "CorrectionPreset":
        camera = CameraProfile(**data["camera"])
        lens = LensProfile(**data["lens"])
        output_frame = FrameGeometry(**data["output_frame"])
        return cls(
            name=data["name"],
            camera=camera,
            lens=lens,
            output_frame=output_frame,
            output_projection=data.get("output_projection", "cylindrical"),
            horizontal_fov_deg=data.get("horizontal_fov_deg", 120.0),
            yaw_deg=data.get("yaw_deg", 0.0),
            pitch_deg=data.get("pitch_deg", -8.0),
            roll_deg=data.get("roll_deg", 0.0),
            zoom=data.get("zoom", 1.0),
            vertical_shift=data.get("vertical_shift", 0.0),
            post_rotate_deg=data.get("post_rotate_deg", 0.0),
            curve_straighten=data.get("curve_straighten", 0.0),
            curve_anchor_y=data.get("curve_anchor_y", -0.75),
            curve_span=data.get("curve_span", 0.55),
            safe_margin=data.get("safe_margin", 0.02),
            notes=data.get("notes", ""),
        )


@dataclass(slots=True)
class ExportOptions:
    mode: ExportMode = "preserve-raster"
    suffix: str = "_corrected"
    jpeg_quality: int = 95
    keep_metadata: bool = True
    overwrite: bool = False


@dataclass(slots=True)
class ImageAsset:
    path: Path
    camera_model: str | None = None
    lens_model: str | None = None
    width: int | None = None
    height: int | None = None


@dataclass(slots=True)
class BatchCorrectionJob:
    preset: CorrectionPreset
    export: ExportOptions
    output_dir: Path
    assets: list[ImageAsset] = field(default_factory=list)
