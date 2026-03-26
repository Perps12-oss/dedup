# CEREBRO Dedup — Duplicate File Finder & Operations Shell

A production-grade duplicate file finder with a seven-destination CEREBRO operations shell: Mission, Scan, Review, History, Diagnostics, Themes, and Settings. The UI is store- and controller-driven with a clear separation between engine, orchestration, and shell.

## Philosophy

- **Engine first**: The engine is the product; the UI is a structured operations shell, not a thin one-off.
- **Truthful metrics**: Every number is based on real measured data.
- **Safe deletion**: Destructive actions require explicit review, preview, and audit.
- **Scalable**: Designed for large datasets with bounded UI and store-centric state.

## Features

- **Streaming discovery**: Memory-efficient file discovery using generators.
- **Layered hashing**: Fast partial hash first, full hash when needed.
- **Safe deletion**: Trash/recycle bin by default; permanent only with confirmation.
- **Shell pages**: Mission (home), Scan (live), Review (decision studio), History, Diagnostics, Themes (presets, contrast snapshot, **custom top-bar accent gradient** editor, JSON import/export), Settings.
- **Theming runtime**: Token-based themes (see `docs/THEME_SYSTEM.md`) applied to the CustomTkinter shell and shared Tk defaults.
- **Decision Studio (Review):** destructive actions and preview flows use **ReviewController** + **toasts**; CTK Review layout is in `dedup/ui/ctk_pages/review_page.py`.
- **Store + controllers**: UIStateStore is the read authority; ScanController and ReviewController handle commands; no direct page/backend coupling in action paths.
- **Thread-safe UI updates**: UI mutations are marshaled through the Tk main thread (`UIStateStore.call_on_ui_thread`) to avoid cross-thread Tk crashes.
- **Cross-platform**: Windows, macOS, Linux.

## Installation

```bash
cd dedup

# Optional: recommended dependencies (faster hashing, drag-drop, thumbnails)
pip install -e ".[recommended]"

# Optional: modern shell (Sun Valley ttk, Windows Mica, CustomTkinter preview)
pip install -e ".[modern-ui]"
# or: pip install xxhash send2trash tkinterdnd2 Pillow

# Run (CustomTkinter — pip install -r requirements-ctk.txt)
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
- **dedup/application/** — Application facades (`ApplicationRuntime`, scan/review/history services) — UI uses these via controllers.
- **dedup/ui/** — CEREBRO shell: CustomTkinter (`ctk_app`, `ctk_pages/`), store, controllers, projections, theme; MVVM experiments under `dedup/core/`, `dedup/models/`, `dedup/services/`, `dedup/ui/viewmodels/`.
  - **Authority**: `docs/UI_AUTHORITY.md`. Hub → store → selectors; commands via ScanController/ReviewController + application services.
  - **Pages**: Mission, Scan, Review, History, Diagnostics, Themes, Settings (NavRail).

See `docs/CONTROLLER_CONTRACTS.md`, `docs/REPO_AUTHORITY.md`, and **`docs/TODO_POST_PHASE3.md`** (next sprint after Phase 3).

## Project docs index

| Doc | Role |
|-----|------|
| `docs/CTK_V3_ROADMAP.md` | **CTK → v3.0** — end goal, phases, parity checklist |
| `docs/ENGINEERING_STATUS.md` | **Living status** — update as features/phases land |
| `docs/UI_AUTHORITY.md` | Primary shell, boundaries, migration snapshot |
| `docs/TODO_POST_PHASE3.md` | **Queued work** after Phase 3 (Review decoupling, banners, tests) |
| `docs/PHASES_1_3_CHECKLIST.md` | Phase 1–3 completion checklist |
| `docs/PHASE_ROLLOUT.md` | Phase-by-phase history and what was skipped |
| `docs/AUDIT_REPORT_PHASE1.md` | Phase 1 static audit completion |
| `CONTRIBUTING.md` | Dev setup, Ruff, pre-commit, tests |

## Packaging

- **Core**: No required dependencies (standard library).
- **Optional**: `pip install -e ".[recommended]"` for xxhash, send2trash, tkinterdnd2, Pillow.
- **Tests**: Excluded from distribution via `setup.py` (packages exclude `dedup.tests`).

## License

MIT. See LICENSE.

## Acknowledgments

Derived from the Cerebro duplicate file finder project.
