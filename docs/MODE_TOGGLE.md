# Simple vs Advanced UI mode

## Sources of truth

- **`AppSettings.advanced_mode`** (`ui/utils/ui_state.py`) — persisted in `ui_settings.json`.
- **`UIStateStore.state.ui_mode`** — `"simple"` or `"advanced"`, kept in sync for subscribers.

## User actions

- **Top bar:** “Advanced” label toggles mode and persists settings (`AppShell._do_advanced_toggle`).
- **Settings page:** Advanced checkbox updates the same field via preferences callback.

## App wiring

- On startup, after `ProjectionHubStoreAdapter.start()`, `CerebroApp` calls `store.set_ui_mode(...)` from `advanced_mode`.
- On toggle, `_on_advanced_mode` updates the store then `shell.apply_preferences()`.

## What changes visually today

- Top bar shows advanced state; per-page section visibility is **not** fully gated yet on `store.state.ui_mode` (many toggles already exist as `AppSettings` flags like `scan_show_phase_metrics`).

## Planned (Phase 5 sub-pass)

- Hide dense diagnostics / compare / export stubs behind `ui_mode == "simple"` or dedicated `AppSettings` flags.
- Subscribe Mission / Scan / Review pages to `UIStateStore` for `ui_mode` and reflow sections without restart.
