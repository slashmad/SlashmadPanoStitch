from __future__ import annotations

import argparse
import json
from pathlib import Path

from panostitch.core.batch_plan import build_batch_job_summary
from panostitch.core.preset_store import load_preset


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="panostitch")
    subparsers = parser.add_subparsers(dest="command")

    validate = subparsers.add_parser("validate-preset", help="Validate a correction preset JSON file.")
    validate.add_argument("preset", type=Path)

    demo = subparsers.add_parser("demo-batch", help="Print a batch plan for the given preset and image files.")
    demo.add_argument("preset", type=Path)
    demo.add_argument("images", nargs="+", type=Path)

    return parser


def run_validate_preset(preset_path: Path) -> int:
    preset = load_preset(preset_path)
    print(json.dumps(preset.to_dict(), indent=2))
    return 0


def run_demo_batch(preset_path: Path, images: list[Path]) -> int:
    preset = load_preset(preset_path)
    summary = build_batch_job_summary(preset, images)
    print(json.dumps(summary, indent=2))
    return 0


def run_ui() -> int:
    try:
        from panostitch.ui.app import run_desktop_app
    except ImportError as exc:
        print("Desktop dependencies are not installed.")
        print("Install them with `python -m pip install -r requirements/desktop.txt`.")
        print(f"Import error: {exc}")
        return 1

    return run_desktop_app()


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "validate-preset":
        return run_validate_preset(args.preset)
    if args.command == "demo-batch":
        return run_demo_batch(args.preset, args.images)
    return run_ui()


if __name__ == "__main__":
    raise SystemExit(main())
