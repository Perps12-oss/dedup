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

---

## Current state and remaining coupling

Accurate picture of what is done vs what is still coupled (for future cleanup).

**1. The store path exists and is live.**  
CerebroApp creates UIStateStore, creates ProjectionHubStoreAdapter, starts it, and wires ScanPage and DiagnosticsPage through `attach_store(...)`. The intended path **hub → store → page** is real in app wiring.

**2. Remaining coordinator injection (Mission, History, Diagnostics).**  
app.py still passes `coordinator=self.coordinator` into MissionPage, HistoryPage, and DiagnosticsPage. Those pages need it for get_resumable_scan_ids, load_scan, get_history, etc. Scan and Review no longer receive coordinator from app; they use controller only (and optional coordinator for test fallback).

**3. Review controller boundary is now pure.**  
The review action bar calls the controller. ReviewController takes a single `callbacks` object implementing `IReviewCallbacks` (get_current_result, set_preview_result, refresh_review_ui, confirm_deletion, on_execute_start, on_execute_done). ReviewPage implements that interface as public methods. App passes `callbacks=self._review`; no lambdas closing over page internals.

**4. History and Diagnostics public refresh hooks exist.**  
app.py routes History and Diagnostics actions to `self._history.refresh()` and `self._diagnostics.refresh()`. Shell no longer calls underscore methods directly for those actions.

**5. Scan page is decoupled from coordinator at app level.**  
app.py passes only `scan_controller` to ScanPage (no coordinator). Display is store-driven via `attach_store`. Commands go through ScanController. Coordinator is optional on ScanPage for fallback (e.g. tests) only.

## Blueprint authority

- Product-level UX/UI authority for the redesign lives in `docs/CEREBRO_BLUEPRINT_ADDENDUM.md`.
- Implementation remains phase-based; partial delivery is acceptable as long as
  each shipped slice preserves single-authority state and controller boundaries.
