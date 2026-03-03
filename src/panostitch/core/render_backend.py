from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import subprocess

import cv2


@dataclass(frozen=True, slots=True)
class RenderBackendStatus:
    api: str
    name: str
    detail: str
    preview_mode: str
    device: str | None = None


@lru_cache(maxsize=1)
def current_render_backend() -> RenderBackendStatus:
    gpu_name = _detect_gpu_name()

    cuda_backend = _detect_cuda_backend(gpu_name)
    if cuda_backend is not None:
        return cuda_backend

    opencl_backend = _detect_opencl_backend(gpu_name)
    if opencl_backend is not None:
        return opencl_backend

    detail = "OpenCL/GPU acceleration unavailable in current runtime"
    if gpu_name:
        detail = f"GPU detected ({gpu_name}), but current OpenCV runtime could not use it"
    return RenderBackendStatus(
        api="cpu",
        name="CPU",
        detail=detail,
        preview_mode="Fit-to-box preview with view zoom",
        device=gpu_name,
    )


def _detect_cuda_backend(gpu_name: str | None) -> RenderBackendStatus | None:
    if not hasattr(cv2, "cuda"):
        return None

    try:
        device_count = cv2.cuda.getCudaEnabledDeviceCount()
    except Exception:
        return None

    if device_count <= 0:
        return None

    detail = "OpenCV CUDA backend active"
    if gpu_name:
        detail = f"OpenCV CUDA backend active on {gpu_name}"
    return RenderBackendStatus(
        api="cuda",
        name="CUDA",
        detail=detail,
        preview_mode="Fit-to-box preview with view zoom",
        device=gpu_name,
    )


def _detect_opencl_backend(gpu_name: str | None) -> RenderBackendStatus | None:
    try:
        have_opencl = cv2.ocl.haveOpenCL()
    except Exception:
        return None

    if not have_opencl:
        return None

    try:
        cv2.ocl.setUseOpenCL(True)
        if not cv2.ocl.useOpenCL():
            return None
    except Exception:
        return None

    detail = "OpenCV OpenCL backend active"
    if gpu_name:
        detail = f"OpenCV OpenCL backend active on {gpu_name}"
    return RenderBackendStatus(
        api="opencl",
        name="OpenCL",
        detail=detail,
        preview_mode="Fit-to-box preview with view zoom",
        device=gpu_name,
    )


def _detect_gpu_name() -> str | None:
    for command in (
        ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
        ["lspci"],
    ):
        output = _run_command(command)
        if not output:
            continue

        if command[0] == "nvidia-smi":
            first_line = output.splitlines()[0].strip()
            if first_line:
                return first_line

        for line in output.splitlines():
            if "VGA compatible controller" in line or "3D controller" in line:
                parts = line.split(":", maxsplit=2)
                if len(parts) >= 3:
                    return parts[2].strip()
                return line.strip()
    return None


def _run_command(command: list[str]) -> str | None:
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=2)
    except Exception:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None
