# CEREBRO Dedup — Duplicate File Finder & Operations Shell

A production-grade duplicate file finder with a six-page CEREBRO operations shell: Mission, Scan, Review, History, Diagnostics, and Settings. The UI is store- and controller-driven with a clear separation between engine, orchestration, and shell.

## Philosophy

- **Engine first**: The engine is the product; the UI is a structured operations shell, not a thin one-off.
- **Truthful metrics**: Every number is based on real measured data.
- **Safe deletion**: Destructive actions require explicit review, preview, and audit.
- **Scalable**: Designed for large datasets with bounded UI and store-centric state.

## Features

- **Streaming discovery**: Memory-efficient file discovery using generators.
- **Layered hashing**: Fast partial hash first, full hash when needed.
- **Safe deletion**: Trash/recycle bin by default; permanent only with confirmation.
- **Six-page shell**: Mission (home), Scan (live), Review (decision studio), History, Diagnostics, Settings.
- **Store + controllers**: UIStateStore is the read authority; ScanController and ReviewController handle commands; no direct page/backend coupling in action paths.
- **Cross-platform**: Windows, macOS, Linux.

## Installation

```bash
cd dedup

# Optional: recommended dependencies (faster hashing, drag-drop, thumbnails)
pip install -e ".[recommended]"
# or: pip install xxhash send2trash tkinterdnd2 Pillow

# Run
python -m dedup
```

## Usage

### GUI

```bash
python -m dedup
```

### CLI

```bash
python -m dedup /path/to/scan
python -m dedup /path/to/scan --min-size 1M
python -m dedup /path/to/scan -v
```

### Python API

```python
from pathlib import Path
from dedup.engine import ScanConfig, ScanPipeline

config = ScanConfig(roots=[Path("/data")], min_size_bytes=1024)
pipeline = ScanPipeline(config)
result = pipeline.run()
plan = pipeline.create_deletion_plan(result)
# Execute via pipeline or coordinator as needed.
```

## Architecture

- **dedup/engine/** — Core duplicate detection (no UI deps).
- **dedup/orchestration/** — Scan lifecycle, coordinator, worker.
- **dedup/infrastructure/** — Config, persistence, trash, logging.
- **dedup/ui/** — CEREBRO shell: app, store, controllers, pages, components, viewmodels, projections, theme.
  - **Authority**: When store is attached, ScanPage reads from store only (hub feeds store). Review reads via selectors; commands go through ReviewController/ScanController.
  - **Pages**: Mission, Scan, Review, History, Diagnostics, Settings (six destinations in NavRail).

See `docs/CONTROLLER_CONTRACTS.md` and `docs/REPO_AUTHORITY.md` for single-authority and command-path details.

## Packaging

- **Core**: No required dependencies (standard library).
- **Optional**: `pip install -e ".[recommended]"` for xxhash, send2trash, tkinterdnd2, Pillow.
- **Tests**: Excluded from distribution via `setup.py` (packages exclude `dedup.tests`).

## License

MIT. See LICENSE.

## Acknowledgments

Derived from the Cerebro duplicate file finder project.
