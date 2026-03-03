from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def resolve_local_root(project_root: Path) -> Path:
    configured = os.environ.get("PANOSTITCH_LOCAL_ROOT")
    if configured:
        return Path(configured).expanduser()

    preferred = Path("/run/media/stolpee/localprog/panostitch")
    if preferred.exists():
        return preferred

    return project_root / ".panostitch-local"


def remove_stale_editable_metadata(site_packages_dir: Path) -> None:
    if not site_packages_dir.exists():
        return

    for pattern in ("panostitch-*.dist-info", "__editable__.panostitch-*.pth"):
        for entry in site_packages_dir.glob(pattern):
            if entry.is_dir():
                shutil.rmtree(entry, ignore_errors=True)
            else:
                entry.unlink(missing_ok=True)


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    local_root = resolve_local_root(project_root)
    venv_dir = local_root / "venvs" / "default"
    wheels_dir = local_root / "wheels"
    project_wheels_dir = project_root / "third_party" / "wheels"
    pip_cache_dir = local_root / "pip-cache"
    temp_dir = local_root / "tmp"
    requirements_file = project_root / "requirements" / "desktop.txt"

    local_root.mkdir(parents=True, exist_ok=True)
    venv_dir.parent.mkdir(parents=True, exist_ok=True)
    wheels_dir.mkdir(parents=True, exist_ok=True)
    pip_cache_dir.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)

    subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)

    python_bin = venv_dir / "bin" / "python"
    if os.name == "nt":
        python_bin = venv_dir / "Scripts" / "python.exe"

    environment = os.environ.copy()
    environment["TMPDIR"] = str(temp_dir)
    environment["PIP_CACHE_DIR"] = str(pip_cache_dir)

    site_packages_dir = Path(
        subprocess.check_output(
            [str(python_bin), "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"],
            text=True,
            env=environment,
        ).strip()
    )
    remove_stale_editable_metadata(site_packages_dir)

    subprocess.run([str(python_bin), "-m", "pip", "install", "--upgrade", "pip"], check=True, env=environment)

    if any(wheels_dir.iterdir()):
        subprocess.run(
            [
                str(python_bin),
                "-m",
                "pip",
                "install",
                "--no-index",
                "--find-links",
                str(wheels_dir),
                "-r",
                str(requirements_file),
            ],
            check=True,
            env=environment,
        )
    elif project_wheels_dir.exists() and any(project_wheels_dir.iterdir()):
        subprocess.run(
            [
                str(python_bin),
                "-m",
                "pip",
                "install",
                "--no-index",
                "--find-links",
                str(project_wheels_dir),
                "-r",
                str(requirements_file),
            ],
            check=True,
            env=environment,
        )
    else:
        subprocess.run(
            [str(python_bin), "-m", "pip", "install", "-r", str(requirements_file)],
            check=True,
            env=environment,
        )

    subprocess.run(
        [str(python_bin), "-m", "pip", "install", "--no-deps", "-e", str(project_root)],
        check=True,
        env=environment,
    )

    print(f"Bootstrap complete in {venv_dir}")
    print(f"Local root: {local_root}")
    print(f"TMPDIR: {temp_dir}")
    print(f"PIP_CACHE_DIR: {pip_cache_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
