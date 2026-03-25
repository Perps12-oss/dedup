# UI authority and migration rules

## Authoritative shell

- **Primary (long-term):** CustomTkinter shell — `python -m dedup` with default backend **`ctk`** (see `dedup/main.py`).
- **Legacy:** ttk / ttkbootstrap shell (`DedupApp` in `dedup/ui/app.py`) remains for compatibility and parity testing; it is **not** the default entry path.

## Mandatory boundaries

```
UI (primary shell)
  → Controllers / intent adapters
    → Application services (`dedup.application.*`)
      → Orchestration (`ScanCoordinator`) / persistence / engine
ProjectionHub → UIStateStore → selectors → pages render from store-backed state
```

### Pages may

- Subscribe to `UIStateStore` / selectors.
- Render widgets from selected state.
- Emit intents via controllers (or thin shell callbacks that delegate to controllers).
- Hold **ephemeral** visual-only state (focus, scroll position where not in store).

### Pages may not

- Call `ScanCoordinator` directly (use `ApplicationRuntime` services via shell or controllers).
- Mutate other pages’ widgets.
- Own business workflow or source-of-truth scan/review state.
- Implement deletion policy or deletion logic.

### Controllers may

- Translate UI actions into intents.
- Call application services (`ScanApplicationService`, `ReviewApplicationService`, …).
- Write results into the store or trigger domain operations through services.

### Controllers may not

- Reach into page-private widget fields (`_workspace`, `_safety_panel`, etc.).
- Contain rendering logic.

### Application services may

- Wrap coordinator/persistence operations.
- Normalize errors for UI/logging.

### Application services may not

- Import UI widgets, CTK, or ttk.

## Composition root

`ApplicationRuntime` (`dedup/application/runtime.py`) owns one `ScanCoordinator` and exposes:

- `scan`, `review`, `history`, `settings` — thin facades for UI and controllers.

The shell keeps `coordinator` only where required for **ProjectionHub** (`event_bus`) and transitional helpers (e.g. `build_history_from_coordinator`).

## Related docs

- `docs/UI_PARITY_MATRIX.md` — feature parity between primary and legacy shells.
- `dedup/ui/legacy/README.md` — legacy UI status.
- `docs/PHASES_1_3_CHECKLIST.md` — what landed for Phases 1–3.
- `docs/TODO_POST_PHASE3.md` — **next sprint** items (action immediately after Phase 3).

## Phase 1–3 snapshot (2026-03)

- **Application services** + **`ApplicationRuntime`** are the UI boundary to orchestration.
- **Store** exposes **`UiDegradedFlags`** (theme failures); **hub adapter** coalesces **metrics** before `set_metrics`.
- **Selectors** expose **`scan_metrics_session_totals`**, **`scan_metrics_phase_local`**, **`scan_metrics_result_assembly`** for truthful UI reads.
- **Path policy** **`canonical_scan_root`** is used when starting scans from **`ScanController`**.
