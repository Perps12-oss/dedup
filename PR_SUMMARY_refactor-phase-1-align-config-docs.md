# Pull Request: Refactor loop (Phases 1–5)

**Branch:** `refactor/phase-1-align-config-docs`  
**Base:** `main`  
**Open PR:** https://github.com/Perps12-oss/dedup/pull/new/refactor/phase-1-align-config-docs

---

## Summary

Implements the full refactor loop (Audit → Plan → Implement → Review → Commit) for all five phases from [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) and [AUDIT_SUMMARY](AUDIT_SUMMARY.md) on a single branch. No behavior change to the engine’s duplicate logic; adds tests, doc/config alignment, option plumbing, truthful progress/ETA, and documents Phase 5 backlog.

---

## Changes by phase

### Phase 1: Align documentation & config
- **Coordinator:** Use `get_default_persistence()` so DB path is platform-correct (Windows AppData, macOS Library, Linux `.local/share`).
- **IMPLEMENTATION_SUMMARY.md:** Directory structure updated; “Implemented since summary” and Build/Run deps (tkinterdnd2, Pillow) aligned.
- **Added:** IMPLEMENTATION_PLAN.md, TODO-ENHANCEMENTS.md (from repo TO DO -ENHANCEMENTS).

**Commit:** `db7ec9c` — phase 1: align persistence defaults and docs

---

### Phase 2: Testing
- **New:** `dedup/tests/test_grouping.py` — size grouping, full-hash confirmation, cancel behavior.
- **New:** `dedup/tests/test_pipeline.py` — full-pipeline integration, cancel, checkpoint save/load and resume path, hash-cache callback wiring.
- **Extended:** `dedup/tests/test_discovery.py` — no-subfolders (only root-level files), symlink when `follow_symlinks=True`, permission-error does not crash.

**Commit:** `17b9b05` — phase 2: add grouping/pipeline/edge-case tests

---

### Phase 3: Refactors
- **Worker:** Typing for `checkpoint_dir` (Path) and hash_cache_setter (FileMetadata).
- **Coordinator:** Pass-through for `max_size_bytes`, `partial_hash_bytes`, `full_hash_workers`, `batch_size`, `progress_interval_ms`, `exclude_dirs`; media_category → allowed_extensions unchanged.
- **Config:** Removed unused `theme` field.
- **New:** `dedup/tests/test_coordinator.py` — option mapping and media_category → images extensions.

**Commit:** `34e9afc` — phase 3: refactor scan option plumbing and config

---

### Phase 4: Progress & UX enhancements
- **Grouping:** Progress includes `files_total`, measured `files_per_second`, and conservative `estimated_remaining_seconds` when throughput is stable (≥1s).
- **Pipeline:** Progress carries `files_total` and `files_per_second` where denominator is known.
- **Scan frame:** Throughput row (“X files/s”), ETA row (“Estimating…” until stable), progress bar determinate only when `percent_complete` is real.

**Commit:** `6bf38b7` — phase 4: improve truthful live progress and ETA behavior

---

### Phase 5: Document backlog
- **README.md:** “Future Work Backlog” — streaming grouping, results virtualization, cross-platform CI; optional deps line updated (tkinterdnd2, Pillow).

**Commit:** `1c510dd` — phase 5: document future-work backlog

---

## Testing

- All phases: `python -m pytest dedup/tests -q` → **36 passed, 1 skipped** (symlink test skipped where unsupported).
- No new linter errors.

## Checklist

- [x] Platform persistence path (Phase 1.2)
- [x] Tests for grouping, pipeline, discovery edge cases (Phase 2)
- [x] Coordinator option pass-through and config trim (Phase 3)
- [x] Truthful throughput/ETA and determinate bar only when valid (Phase 4)
- [x] Phase 5 backlog documented in README
- [x] Branch pushed; PR link above

## Merge notes

- Safe to merge into `main`; no breaking API or config file format changes.
- Existing `config.json` may still contain `theme`; `Config.from_dict` ignores unknown keys, so no migration needed.
