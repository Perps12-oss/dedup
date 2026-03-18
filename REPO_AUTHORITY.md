# Single-authority matrix

One place that states **who is the authority** for reads and commands. Avoid duplicate update paths and mixed-mode state.

## Scan

| Concern | Live read path | Command path | Notes |
|--------|-----------------|--------------|--------|
| **ScanPage** | UIStateStore (when attached). Selectors: scan_session, scan_phases, scan_metrics, scan_compat, scan_events_log, scan_terminal, degraded_state. | ScanController (handle_start_scan, handle_start_resume, handle_cancel). Coordinator used only inside controller. | When store is attached, hub is detached on ScanPage so store is the single source. Hub feeds store via adapter. |
| **App** | Store + hub (for drawer content). Prefer store where available. | Controllers; never direct page-private methods for scan. | ScanPage gets store in _wire_hub; coordinator is not the UI read path. |

## Review

| Concern | Live read path | Command path | Notes |
|--------|-----------------|--------------|--------|
| **ReviewPage** | VM (fed by load_result and _sync_review_from_store_and_refresh). Store read via review_selection(state) only. | ReviewController (handle_set_keep, handle_clear_keep, handle_preview_deletion, handle_execute_deletion). App action map calls controller, not page. | No direct app → page._on_dry_run / _on_execute. |
| **App** | Store for sync; page VM for drawer stats. | ReviewController for Preview/DELETE actions. | get_current_result and other callbacks are controller→page wiring; that is intended. |

## Other pages

| Page | Read path | Command path |
|------|-----------|--------------|
| **Mission** | Store (mission slice) where used; coordinator for history/resumable. | App / coordinator (start scan, resume). |
| **History** | VM + coordinator (load sessions, load_scan). | Coordinator; page calls coordinator, app does not call page-private methods for actions. |
| **Diagnostics** | UIStateStore (documented as store-rendered with hub upstream). | Page refresh; coordinator/hub for data. |
| **Settings** | Theme/settings state. | Page + theme manager. |

## Rules

- **No app → page-private methods** for actions. Use controller or public page API.
- **ScanPage**: When store is attached, only store drives display; hub is detached.
- **Review**: All review state reads via selectors; writes via store.set_review_selection. Commands via ReviewController only.
- **Packaging**: Tests excluded from distribution. Optional deps in setup.py extras_require and requirements.txt.
