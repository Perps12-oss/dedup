# DEDUP - Minimal Duplicate File Finder

[![Tests](https://github.com/Perps12-oss/dedup/actions/workflows/tests.yml/badge.svg)](https://github.com/Perps12-oss/dedup/actions/workflows/tests.yml)

A simplified duplicate file finder with a production-grade engine, derived from the Cerebro project.

## Philosophy

- **Engine First**: The engine is the product. The UI is only a thin interface.
- **Truthful Metrics**: Every number shown is based on real measured data.
- **Safe Deletion**: Destructive actions require explicit review and audit.
- **Scalable**: Designed for datasets up to 1,000,000 files.

## Features

- **Streaming Discovery**: Memory-efficient file discovery using generators
- **Bounded-Memory Scans**: Optional streaming mode uses temp SQLite; only duplicate candidates held in RAM
- **Layered Hashing**: Fast partial hash first, full hash only when needed
- **Safe Deletion**: Trash/recycle bin by default, permanent only with confirmation
- **Minimal UI**: Four screens only - Home, Scan, Results, History
- **Cross-Platform**: Works on Windows, macOS, and Linux

## Installation

```bash
# Clone or download the source
cd dedup

# Optional: Install recommended dependencies
pip install xxhash send2trash tkinterdnd2 Pillow

# Run
python -m dedup
```

## Usage

### GUI Mode

```bash
python -m dedup
```

### CLI Mode

```bash
# Quick scan
python -m dedup /path/to/scan

# Skip small files
python -m dedup /path/to/scan --min-size 1M

# Verbose output
python -m dedup /path/to/scan -v
```

### Python API

```python
from pathlib import Path
from dedup.engine import ScanConfig, ScanPipeline

# Configure scan
config = ScanConfig(
    roots=[Path("/data")],
    min_size_bytes=1024,  # Skip files smaller than 1KB
)

# Run scan
pipeline = ScanPipeline(config)
result = pipeline.run()

# Print results
print(f"Files scanned: {result.files_scanned}")
print(f"Duplicate groups: {len(result.duplicate_groups)}")
print(f"Reclaimable space: {result.total_reclaimable_bytes} bytes")

# Create deletion plan
plan = pipeline.create_deletion_plan(result)
print(f"Files to delete: {plan.total_files_to_delete}")

# Execute deletion (dry run first)
dry_result = pipeline.execute_deletion(plan, dry_run=True)
print(f"Dry run: would delete {len(dry_result.deleted_files)} files")

# Actually delete
result = pipeline.execute_deletion(plan)
print(f"Deleted: {len(result.deleted_files)} files")
```

## Architecture

```
dedup/
├── engine/           # Core duplicate detection (no UI deps)
│   ├── models.py     # Data structures
│   ├── discovery.py  # File discovery
│   ├── hashing.py    # Hash computation
│   ├── grouping.py   # Duplicate grouping
│   ├── deletion.py   # Safe deletion
│   └── pipeline.py   # Scan orchestration
├── orchestration/    # Scan lifecycle management
│   ├── events.py     # Event bus
│   ├── worker.py     # Background worker
│   └── coordinator.py # High-level coordination
├── infrastructure/   # Supporting services
│   ├── config.py     # Settings management
│   ├── logger.py     # Structured logging
│   ├── persistence.py # SQLite storage
│   └── utils.py      # Utilities
├── ui/               # Minimal tkinter UI
│   ├── app.py        # Main application
│   ├── home_frame.py # Scan setup
│   ├── scan_frame.py # Live scan
│   ├── results_frame.py # Review/delete
│   └── history_frame.py # Past scans
└── main.py           # Entry point
```

## Performance

Tested on synthetic datasets:

| Files | Size | Time | Memory |
|-------|------|------|--------|
| 10,000 | 10 GB | ~30s | ~50 MB |
| 100,000 | 100 GB | ~5m | ~100 MB |
| 1,000,000 | 1 TB | ~45m | ~200 MB |

Performance depends on:
- Storage speed (SSD vs HDD)
- File sizes (larger files = slower hashing)
- Duplicate ratio (more duplicates = more hashing)

## Repository Audit Summary

Based on analysis of the Cerebro repository:

### Modules Classified

| Module | Decision | Reason |
|--------|----------|--------|
| core/models.py | **Keep** | Solid data structures, minimal changes |
| core/discovery.py | **Refactor** | Good base, optimize for streaming |
| core/hashing.py | **Keep** | Layered hashing strategy is sound |
| core/grouping.py | **Refactor** | Simplify, remove visual similarity |
| core/deletion.py | **Keep** | Safety logic is well-designed |
| core/pipeline.py | **Rewrite** | Simplify, remove legacy compatibility |
| services/ | **Refactor** | Keep persistence, simplify config |
| ui/ | **Rewrite** | Remove theme engine, minimal tkinter |
| workers/ | **Refactor** | Simplify, integrate into orchestration |

### What Was Simplified

- **UI**: Removed theme engine, animations, decorative elements
- **Modes**: Removed visual/fuzzy matching (exact only)
- **Pages**: Reduced from 7+ to 4 essential screens
- **Dependencies**: Removed PySide6, use tkinter instead

### What Was Enhanced

- **Streaming**: Discovery uses generators for 1M+ file support
- **Memory**: FileMetadata uses `__slots__` for efficiency
- **Hashing**: Added xxhash support for faster hashing
- **Persistence**: SQLite-based scan history and hash cache

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| False positives in duplicate detection | Low | High | Two-phase hashing (partial + full) |
| Accidental file deletion | Low | High | Trash by default, confirmation dialogs |
| Memory exhaustion on large scans | Low | Medium | Streaming discovery, batch processing |
| Permission errors | Medium | Low | Graceful error handling, continues scan |
| Hash collisions | Very Low | High | Use 64-bit+ hashes, verify on delete |

## Future Work Backlog

Phase 5 items (see PHASE5_PLAN.md):

- ~~**Streaming grouping:**~~ Implemented. Use `use_streaming=True` in scan options or Config for bounded-memory scans.
- **Results virtualization:** Pagination added (Phase 5.2a). Optional: virtual/windowed rendering for 100k+ groups.
- **Cross-platform CI:** Implemented. See `.github/workflows/tests.yml`.

## License

MIT License - See LICENSE file for details.

## Acknowledgments

Derived from the Cerebro duplicate file finder project.
