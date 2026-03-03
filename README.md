# PanoStitch

<p align="center">
  <img src="./slashmadpanostitchicon.png" alt="PanoStitch icon" width="160">
</p>

<p align="center">
  Linux-first desktop software for fast fisheye correction and panorama stitching.
</p>

## Overview

PanoStitch is a compact desktop application focused on two workflows:

- correcting fisheye images with reusable presets
- building and refining panorama previews from overlapping image sets

The project started from a very specific real-world need: correcting images shot with a Sigma 15mm diagonal fisheye on a Sony A7R III without destroying framing, overcropping, or forcing the user through a heavy multi-window workflow.

The long-term goal is a Linux-first tool in the space between Hugin's power and PTGui's speed: direct, visual, interactive, and able to handle both single-image fisheye correction and multi-image panorama work.

## Current Features

### Fisheye Correct

- import folders of `ARW`, `DNG`, `JPEG`, `TIFF`, `PNG`, `WebP`, `BMP`
- read and normalize camera/lens metadata from the first image in the folder
- seed correction defaults from Lensfun plus local lens overrides
- compact dark UI with direct preview interaction
- reusable correction controls for:
  - projection
  - fisheye mapping
  - pitch / roll / yaw
  - rotation
  - zoom
  - vertical shift
  - horizontal FOV
  - lens diagonal FOV
  - crop margin
- mouse-driven preview adjustment
- export selected image or batch export the whole folder
- session-safe local runtime and temp storage on fast local media when available

### Panorama Stitch

- import overlapping image sets from a dedicated folder or reuse the current fisheye folder
- optional fisheye precorrection before stitching
- stitch preview settings for:
  - mode
  - max input edge
  - registration resolution
  - seam resolution
  - compose resolution
  - confidence threshold
  - wave correction
- progress modal during panorama preview generation
- session cache for built panorama previews
- fast reuse of already-built stitch variants, including switching back to a previously built `wave correction` state
- post-stitch panorama correction preview with interactive mouse manipulation
- panorama export from the current stitched preview

## Design Goals

- fast iteration on Linux, with Windows support as a first-class secondary target
- compact, dark, low-noise UI
- direct manipulation before deep menus
- quality-first defaults
- cache and scratch data on fast local storage such as NVMe
- clear separation between:
  - expensive stitch/build operations
  - lightweight interactive preview correction

## Technology Stack

- `Python 3.13+`
- `PySide6` for the desktop UI
- `rawpy` / `LibRaw` for RAW loading
- `lensfunpy` / `Lensfun` for lens metadata and profile seeding
- `OpenCV` for remapping, stitching, and preview operations
- optional `pyvips` support later for additional batch performance work

## Performance Strategy

PanoStitch is being built around the idea that heavy panorama work and interactive preview work should not be treated as the same problem.

The intended model is:

- the initial stitch preview may be expensive
- once a preview exists, refinement should feel immediate
- repeated variants should come from cache whenever possible
- GPU acceleration should be used where it is actually beneficial and reliable

Current work already includes:

- OpenCL-aware preview and render paths where available
- a panorama preview progress modal
- session-only panorama preview caching
- automatic cleanup of session cache on startup/shutdown

## Local Runtime and Cache

By default, PanoStitch prefers a fast local runtime root at:

```bash
/run/media/stolpee/localprog/panostitch
```

That location is used for the local virtual environment, pip cache, temporary files, and panorama preview cache when writable.

You can override it with:

```bash
PANOSTITCH_LOCAL_ROOT=/path/to/fast/storage
```

For best results, use a fast local SSD or NVMe volume.

## Getting Started

### Start the app

```bash
cd /mnt/p3-raidz2/linux-projects/panostitch
./run-panostitch.sh
```

### Bootstrap the local environment

```bash
cd /mnt/p3-raidz2/linux-projects/panostitch
python3 scripts/bootstrap_local_env.py
```

### Manual installation

Use the project-local interpreter, not whichever `python` happens to be active in the shell:

```bash
/run/media/stolpee/localprog/panostitch/venvs/default/bin/python -m pip install -r requirements/desktop.txt
/run/media/stolpee/localprog/panostitch/venvs/default/bin/python -m pip install --no-deps -e .
```

## Testing

```bash
cd /mnt/p3-raidz2/linux-projects/panostitch
/run/media/stolpee/localprog/panostitch/venvs/default/bin/python -m unittest discover -s tests
```

## Repository Layout

- [src/panostitch](./src/panostitch)
  Main application package
- [docs/architecture.md](./docs/architecture.md)
  Project architecture notes
- [docs/competitive-analysis.md](./docs/competitive-analysis.md)
  Product and market notes
- [docs/lens-data.md](./docs/lens-data.md)
  Lens metadata and calibration notes
- [examples/presets/sigma-15mm-a7r3-horizontal-edge.json](./examples/presets/sigma-15mm-a7r3-horizontal-edge.json)
  Example preset for the Sigma 15mm / Sony A7R III workflow

## Status

This is active prototype software, not a finished public release.

What already works well:

- fisheye correction workflow
- metadata normalization
- lens seeding
- direct preview manipulation
- batch export
- panorama preview generation
- post-stitch preview refinement
- session panorama cache

What is still evolving:

- more accurate panorama straighten / level tools
- cache controls in the UI
- deeper GPU acceleration
- higher-end stitch export pipeline
- stronger manual panorama alignment tools

## Inspiration

PanoStitch is strongly informed by:

- PTGui
- Hugin
- the gap between open-source panorama engines and polished desktop workflow tools

The goal is not to clone those tools UI-for-UI, but to build a fast, modern, Linux-first workflow that learns from the strongest parts of both.
