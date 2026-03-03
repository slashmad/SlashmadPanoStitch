from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import struct

import numpy as np
import rawpy
from PIL import Image, ImageOps

from panostitch.domain.models import ImageAsset
from panostitch.io.lens_db import normalize_import_metadata

SUPPORTED_RAW_EXTENSIONS = {".arw", ".cr2", ".cr3", ".dng", ".nef", ".orf", ".raf", ".rw2"}
SUPPORTED_RASTER_EXTENSIONS = {".bmp", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp"}
SUPPORTED_IMAGE_EXTENSIONS = SUPPORTED_RAW_EXTENSIONS | SUPPORTED_RASTER_EXTENSIONS

MAKE_TAG = 271
MODEL_TAG = 272
IMAGE_WIDTH_TAG = 256
IMAGE_HEIGHT_TAG = 257
EXIF_IFD_TAG = 34665
LENS_MAKE_TAG = 42035
LENS_MODEL_TAG = 42036
EXIF_IMAGE_WIDTH_TAG = 40962
EXIF_IMAGE_HEIGHT_TAG = 40963

TIFF_TYPE_SIZES = {
    1: 1,
    2: 1,
    3: 2,
    4: 4,
    5: 8,
    7: 1,
    9: 4,
    10: 8,
}


@dataclass(slots=True)
class LoadedImage:
    path: Path
    rgb_data: np.ndarray
    width: int
    height: int
    camera_model: str | None = None
    lens_model: str | None = None
    is_raw: bool = False


def is_supported_image(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS


def is_raw_image(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_RAW_EXTENSIONS


def list_images_in_directory(directory: Path) -> list[Path]:
    if not directory.exists() or not directory.is_dir():
        return []
    return sorted((path for path in directory.iterdir() if is_supported_image(path)), key=lambda path: path.name.lower())


def scan_directory_assets(directory: Path) -> list[ImageAsset]:
    return [ImageAsset(path=path) for path in list_images_in_directory(directory)]


def read_image_asset_metadata(path: Path) -> ImageAsset:
    camera_model: str | None = None
    lens_model: str | None = None
    width: int | None = None
    height: int | None = None

    if is_raw_image(path):
        camera_model, lens_model, width, height = _read_tiff_metadata(path)
    else:
        try:
            with Image.open(path) as image:
                camera_model, lens_model = _extract_exif_fields(image)
                width, height = image.size
        except Exception:
            camera_model = None
            lens_model = None

    camera_model, lens_model = normalize_import_metadata(camera_model, lens_model)

    if is_raw_image(path) and (width is None or height is None):
        try:
            with rawpy.imread(str(path)) as raw:
                width = int(raw.sizes.width)
                height = int(raw.sizes.height)
        except Exception:
            width = None
            height = None

    return ImageAsset(
        path=path,
        camera_model=camera_model,
        lens_model=lens_model,
        width=width,
        height=height,
    )


def load_image(path: Path, max_edge: int | None = None) -> LoadedImage:
    if is_raw_image(path):
        return _load_raw_image(path, max_edge=max_edge)
    return _load_raster_image(path, max_edge=max_edge)


def save_rgb_image(
    rgb_data: np.ndarray,
    output_path: Path,
    output_format: str,
    jpeg_quality: int = 95,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    image = Image.fromarray(rgb_data, mode="RGB")
    normalized = output_format.lower()

    if normalized in {"jpg", "jpeg"}:
        image.save(output_path, format="JPEG", quality=jpeg_quality, subsampling=0)
        return
    if normalized == "png":
        image.save(output_path, format="PNG")
        return
    if normalized in {"tif", "tiff"}:
        image.save(output_path, format="TIFF", compression="tiff_deflate")
        return
    raise ValueError(f"Unsupported output format: {output_format}")


def _load_raster_image(path: Path, max_edge: int | None) -> LoadedImage:
    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image)
        camera_model, lens_model = _extract_exif_fields(image)
        image = image.convert("RGB")
        if max_edge is not None:
            image.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
        rgb_data = np.array(image, dtype=np.uint8)

    camera_model, lens_model = normalize_import_metadata(camera_model, lens_model)

    return LoadedImage(
        path=path,
        rgb_data=rgb_data,
        width=int(rgb_data.shape[1]),
        height=int(rgb_data.shape[0]),
        camera_model=camera_model,
        lens_model=lens_model,
        is_raw=False,
    )


def _load_raw_image(path: Path, max_edge: int | None) -> LoadedImage:
    camera_model, lens_model, _meta_width, _meta_height = _read_tiff_metadata(path)
    with rawpy.imread(str(path)) as raw:
        use_half_size = False
        if max_edge is not None:
            largest_edge = max(raw.sizes.width, raw.sizes.height)
            use_half_size = largest_edge > (max_edge * 1.5)

        rgb_data = raw.postprocess(
            use_camera_wb=True,
            no_auto_bright=True,
            half_size=use_half_size,
            output_bps=8,
        )

    rgb_data = np.ascontiguousarray(rgb_data, dtype=np.uint8)
    camera_model, lens_model = normalize_import_metadata(camera_model, lens_model)
    return LoadedImage(
        path=path,
        rgb_data=rgb_data,
        width=int(rgb_data.shape[1]),
        height=int(rgb_data.shape[0]),
        camera_model=camera_model,
        lens_model=lens_model,
        is_raw=True,
    )


def _extract_exif_fields(image: Image.Image) -> tuple[str | None, str | None]:
    exif = image.getexif()
    if not exif:
        return None, None

    make = _normalize_exif_value(exif.get(MAKE_TAG))
    model = _normalize_exif_value(exif.get(MODEL_TAG))
    lens_make = _normalize_exif_value(exif.get(LENS_MAKE_TAG))
    lens_model = _normalize_exif_value(exif.get(LENS_MODEL_TAG))
    return _combine_make_and_model(make, model), _combine_make_and_model(lens_make, lens_model)


def _normalize_exif_value(value: object) -> str | None:
    if isinstance(value, bytes):
        value = value.decode(errors="ignore")
    if isinstance(value, str):
        cleaned = value.strip().strip("\x00")
        return cleaned or None
    return None


def _read_tiff_metadata(path: Path) -> tuple[str | None, str | None, int | None, int | None]:
    try:
        with path.open("rb") as handle:
            header = handle.read(8)
            if len(header) < 8:
                return None, None, None, None

            endian_bytes = header[:2]
            if endian_bytes == b"II":
                endian = "<"
            elif endian_bytes == b"MM":
                endian = ">"
            else:
                return None, None, None, None

            version = struct.unpack(f"{endian}H", header[2:4])[0]
            if version != 42:
                return None, None, None, None

            first_ifd_offset = struct.unpack(f"{endian}I", header[4:8])[0]
            ifd0 = _read_tiff_ifd(handle, endian, first_ifd_offset)
            if ifd0 is None:
                return None, None, None, None

            make = _normalize_exif_value(_read_tiff_entry_value(handle, endian, *ifd0.get(MAKE_TAG, (0, 0, 0))))
            model = _normalize_exif_value(_read_tiff_entry_value(handle, endian, *ifd0.get(MODEL_TAG, (0, 0, 0))))
            width = _coerce_int(_read_tiff_entry_value(handle, endian, *ifd0.get(IMAGE_WIDTH_TAG, (0, 0, 0))))
            height = _coerce_int(_read_tiff_entry_value(handle, endian, *ifd0.get(IMAGE_HEIGHT_TAG, (0, 0, 0))))

            lens_make: str | None = None
            lens_model: str | None = None
            exif_ifd_offset = _coerce_int(_read_tiff_entry_value(handle, endian, *ifd0.get(EXIF_IFD_TAG, (0, 0, 0))))
            if exif_ifd_offset:
                exif_ifd = _read_tiff_ifd(handle, endian, exif_ifd_offset)
                if exif_ifd is not None:
                    lens_make = _normalize_exif_value(
                        _read_tiff_entry_value(handle, endian, *exif_ifd.get(LENS_MAKE_TAG, (0, 0, 0)))
                    )
                    lens_model = _normalize_exif_value(
                        _read_tiff_entry_value(handle, endian, *exif_ifd.get(LENS_MODEL_TAG, (0, 0, 0)))
                    )
                    width = width or _coerce_int(
                        _read_tiff_entry_value(handle, endian, *exif_ifd.get(EXIF_IMAGE_WIDTH_TAG, (0, 0, 0)))
                    )
                    height = height or _coerce_int(
                        _read_tiff_entry_value(handle, endian, *exif_ifd.get(EXIF_IMAGE_HEIGHT_TAG, (0, 0, 0)))
                    )

            camera_model = _combine_make_and_model(make, model)
            return camera_model, _combine_make_and_model(lens_make, lens_model), width, height
    except Exception:
        return None, None, None, None


def _read_tiff_ifd(handle, endian: str, ifd_offset: int) -> dict[int, tuple[int, int, int]] | None:
    if ifd_offset <= 0:
        return None

    handle.seek(ifd_offset)
    raw_count = handle.read(2)
    if len(raw_count) != 2:
        return None

    entry_count = struct.unpack(f"{endian}H", raw_count)[0]
    entries: dict[int, tuple[int, int, int]] = {}
    for _ in range(entry_count):
        raw_entry = handle.read(12)
        if len(raw_entry) != 12:
            return None
        tag, field_type, count, value_or_offset = struct.unpack(f"{endian}HHII", raw_entry)
        entries[tag] = (field_type, count, value_or_offset)
    return entries


def _read_tiff_entry_value(handle, endian: str, field_type: int, count: int, value_or_offset: int):
    if field_type == 0 or count == 0:
        return None

    item_size = TIFF_TYPE_SIZES.get(field_type)
    if item_size is None:
        return None

    total_size = item_size * count
    if total_size <= 4:
        raw_data = struct.pack(f"{endian}I", value_or_offset)[:total_size]
    else:
        current_position = handle.tell()
        handle.seek(value_or_offset)
        raw_data = handle.read(total_size)
        handle.seek(current_position)

    if len(raw_data) != total_size:
        return None

    if field_type == 2:
        return raw_data.decode(errors="ignore").rstrip("\x00")
    if field_type == 3:
        values = struct.unpack(f"{endian}{count}H", raw_data)
        return values[0] if count == 1 else values
    if field_type == 4:
        values = struct.unpack(f"{endian}{count}I", raw_data)
        return values[0] if count == 1 else values
    if field_type == 9:
        values = struct.unpack(f"{endian}{count}i", raw_data)
        return values[0] if count == 1 else values
    return raw_data


def _coerce_int(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, tuple) and len(value) == 1 and isinstance(value[0], int):
        return value[0]
    return None


def _combine_make_and_model(make: str | None, model: str | None) -> str | None:
    if make and model and model.lower().startswith(make.lower()):
        return model
    if make and model:
        return f"{make} {model}"
    return model or make
