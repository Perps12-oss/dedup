# Exception Hygiene Inventory

## Stage 1: Broad exception sites

| File | Location | Current reason | Bucket | Likely expected types | Severity if swallowed |
|------|----------|----------------|--------|----------------------|------------------------|
| engine/deletion.py | audit log write | "should not break operation" | B | OSError, IOError | Medium – audit gap |
| engine/deletion.py | trash send2trash fallback | nested | B | OSError, ImportError | Medium |
| engine/deletion.py | revalidation loop | nested | B | OSError, FileNotFoundError | High – safety |
| orchestration/events.py | publish callback | "Don't let subscriber errors break bus" | B | any | High – silent UI drift |
| ui/utils/ui_state.py | load_settings | fallback default | A | IOError, ValueError, json.JSONDecodeError | Low |
| ui/utils/ui_state.py | save | silent fail | A | IOError, OSError | Low |
| ui/utils/ui_state.py | emit callback | optional | B | any | Low |
| orchestration/coordinator.py | save_scan | silent | B | persistence/DB errors | **High** – history loss |
| orchestration/coordinator.py | get_history, get_resumable_scan_ids, load_scan, delete_scan | return []/None/False | B | persistence | Medium |
| engine/discovery.py | _scan_directory worker | _stats["errors"] += 1 | A | OSError, PermissionError | Low |
| engine/discovery.py | progress_cb | don't break yield | B | any | Medium |
| engine/discovery.py | outer _scan_directory | _stats["errors"] += 1 | A | OSError | Low |
| engine/pipeline.py | event emit (2 places) | pass | B | any | Medium |
| engine/pipeline.py | checkpoint write | "should not stop scan" | B | OSError, IOError | **High** – resume truth |
| engine/pipeline.py | _load_checkpoint, load_checkpoint_config | return None | A | IOError, json.JSONDecodeError | Low |
| engine/pipeline.py | _clear_checkpoint unlink | pass | A | OSError | Low |
| engine/thumbnails.py | cache lookup | return None | A | any | Low |
| engine/bench.py | log_bench_summary | pass | A | any | Low |
| ui/pages/diagnostics_page.py | detach unsub, get_history, export | cleanup/fallback | A | any | Low |
| infrastructure/persistence.py | list (e.g. list_scans) | return [] | B | sqlite3.Error, OSError | Medium |
| engine/hashing.py | cache get/set, worker yield | return None / pass / yield with error | A/B | OSError, TypeError | Low–Medium |
| orchestration/worker.py | on_progress, on_cancel, on_complete, on_error | don't kill worker | B | any | **High** – scan completion |
| ui/projections/hub.py | _schedule_poll, _flush, callback delivery | don't kill poll loop | B | any, TclError | **High** – UI state |
| ui/theme/theme_manager.py | observer callback | don't break apply | B | any | Low |
| ui/app.py | get_resumable_scan_ids, clipboard, hub.shutdown, state.save | best-effort | A | OSError, TclError | Low |
| ui/viewmodels/*, ui/pages/* | various optional/fallback | fallback empty/None | A | various | Low |

**Bucket A**: Expected operational (file not found, permission denied, optional missing). Catch explicitly; log; continue.  
**Bucket B**: Resilience guards (checkpoint, repository, callbacks). Catch narrowly; log warning; emit diagnostics; degrade visibly.  
**Bucket C**: Programming errors (TypeError, KeyError, wrong AttributeError). Do not swallow; fail operation; surface.

## Stage 2: High-risk zones (priority order)

1. **Checkpoint writes** (pipeline) – log warning; record diagnostics event.
2. **Repository / coordinator** (save_scan, list/get/delete) – log warning; record diagnostics.
3. **Hub callback delivery** – log warning; increment delivery failure counter.
4. **Event bus publish** – log warning; optional diagnostics.
5. **Worker callbacks** (on_complete, on_error, etc.) – log warning.
6. **Deletion** (audit log, revalidation) – log; do not silently proceed on revalidation failure.

## Stage 3–5

- Replace broad catches in high-risk zones with narrow exceptions + logging + diagnostics.
- Add tests: checkpoint failure logged and does not stop scan; callback failure logged; save_scan failure logged.
- Diagnostics summary: expose callback delivery warnings, checkpoint failures, repository write issues, degraded indicator.
