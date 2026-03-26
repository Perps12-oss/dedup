# Simple vs Advanced UI mode

## Sources of truth

- **`AppSettings.advanced_mode`** (`ui/utils/ui_state.py`) — persisted in `ui_settings.json`.
- **`UIStateStore.state.ui_mode`** — `"simple"` or `"advanced"`, kept in sync for subscribers.

## User actions

- **CTK Themes / Settings:** Advanced and related toggles update the same persisted fields and trigger store refresh via `CerebroCTKApp._on_settings_changed` / theme callbacks.
- **Simple vs Advanced** gates **export**, **diagnostics depth**, **Review compare**, etc., according to `store.state.ui_mode` (see `ctk_app._show_page` and individual `ctk_pages/*`).

## App wiring

- On startup, `CerebroCTKApp` sets `store.set_ui_mode(...)` from `advanced_mode` after the hub store adapter starts.
- Preference changes re-apply theme tokens and `store.set_ui_mode`.

## What changes visually in Simple mode

- **Export** actions hidden on History / Diagnostics where gated.
- **Diagnostics** shows fewer tabs / detail in simple mode (see `DiagnosticsPageCTK` + store subscription).
- **Review:** compare-only affordances may be hidden (see `ReviewPageCTK` + `ui_mode`).

## Advanced mode

- Full controls, exports, and diagnostics surfaces as implemented per page.

## Mission & Scan layout

- **CTK** `MissionPageCTK` / `ScanPageCTK` read **`AppSettings`** flags and **`store`** (mission slice, scan projections) to show or hide dashboard cards and scan side panels — see `sync_chrome` / `attach_store` patterns on each page.

Historical note: **ttk** `AppShell` / `MissionPage` / `ScanPage` described older layout rules; those modules are **removed**.
