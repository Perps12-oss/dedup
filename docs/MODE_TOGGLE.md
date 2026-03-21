# Simple vs Advanced UI mode

## Sources of truth

- **`AppSettings.advanced_mode`** (`ui/utils/ui_state.py`) — persisted in `ui_settings.json`.
- **`UIStateStore.state.ui_mode`** — `"simple"` or `"advanced"`, kept in sync for subscribers.

## User actions

- **Top bar:** “Advanced” label toggles mode and persists settings (`AppShell._do_advanced_toggle`).
- **Settings page:** Advanced checkbox updates the same field via preferences callback.

## App wiring

- On startup, after `ProjectionHubStoreAdapter.start()`, `CerebroApp` calls `store.set_ui_mode(...)` from `advanced_mode` (before diagnostics attaches to the store).
- **Top bar Advanced** and **Settings → Advanced** both end up in `_apply_preferences()`, which: `shell.apply_preferences()`, `store.set_ui_mode(...)`, `ReviewPage.set_ui_mode(...)`, and refreshes top-bar page actions + insight drawer for the active page.

## What changes visually in Simple mode

- **Top bar (contextual):** no **Export** on History / Diagnostics; no **Copy Diag** on Scan.
- **Insight drawer:** on Diagnostics, **Compat** section hidden (Live Phase only).
- **Diagnostics page:** notebook shows **Phases** only; Artifacts, Compatibility, Events, Integrity tabs hidden (`apply_ui_mode` via store subscription).
- **Review page:** **Compare** view radiobutton hidden; if the user was in Compare, mode falls back to Table; compare shortcuts (`C`, `[` / `]`, `X`) no-op.

## Advanced mode

- Full tabs, Export / Copy Diag actions, Compare UI, and drawer Compat block.

## Mission & Scan layout

- **Simple `ui_mode`:** Mission shows **Last Scan** only (full-width), hides **Engine** / **Trash Protection** cards, **Recent Sessions**, and **Watch Tour**. Scan hides the right column (**Live Metrics**, **Health & Compatibility**, **Activity Feed**) — target + timeline + phase detail only.
- **Advanced `ui_mode`:** Uses `AppSettings` flags (Settings → Behavior):
  - `mission_show_capabilities` — Engine card
  - `mission_show_warnings` — Trash Protection card
  - `scan_show_phase_metrics` — Live Metrics
  - `scan_show_saved_work` — Health & Compatibility
  - `scan_show_events` — Activity Feed (unchanged; default off)

`CerebroApp._apply_preferences()` calls `MissionPage.sync_chrome()` and `ScanPage.sync_chrome()` so toggles apply without restart.
