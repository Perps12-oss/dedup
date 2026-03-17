# Transitional paths (boundary hardening)

Paths that are intentional for now but may be removed or replaced once migration is complete. See [BOUNDARY_AUDIT.md](BOUNDARY_AUDIT.md) for full audit.

---

## Accepted for now (explicit contract)

| Path | Location | Note |
|------|----------|------|
| Mission/History refresh on show | App: `_refresh_mission_state`, `_refresh_history_state` called from page `on_show` | App builds slice from coordinator and pushes to store; page subscribes. Remove when: store is populated by a dedicated adapter on navigate or on scan complete. |
| ScanPage still receives coordinator | ScanPage __init__, fallback paths | Used when no ScanController; and for progress/complete/error callbacks. Remove when: ScanPage is store-only for display and all commands go through ScanController. |
| DiagnosticsPage coordinator for history/detail | DiagnosticsPage._refresh, load(session_id) | Session list and detail load from coordinator. Remove when: diagnostics slice in store or dedicated diagnostics refresh intent. |
| ReviewPage VM still source for _create_plan inputs when no store | ReviewPage._create_plan (legacy path) | When controller is present, plan is built in controller from store + get_current_result. VM remains for UI display. Keep. |
| App terminal handler navigates and loads review | App: hub.subscribe("terminal", _on_terminal) | Gets result from coordinator, calls _review.load_result, navigates. Remove when: terminal completion pushes to store and a dedicated handler triggers navigation/load. |

---

## Remove when (one-line notes)

- **ScanPage.attach_hub**: Remove when ScanPage subscribes to store only and hub→store adapter is the sole writer for scan state.
- **ScanPage.coordinator** (direct start_scan/start_resume/cancel_scan in fallback path): Remove when ScanController is always present and page never calls coordinator directly.
- **MissionPage/HistoryPage fallback _refresh() using coordinator**: Remove when store is always populated before page is shown (e.g. adapter on navigate).
- **ReviewController callbacks that reference _review (e.g. _safety_panel, _show_delete_confirmation)**: Already removed; controller uses store + callbacks only. Callbacks are still wired in app to page methods — acceptable; no page ref inside controller.

---

## Not transitional (target state)

- ReviewController: store + coordinator + callbacks only; no page reference.
- ScanController: store intent lifecycle + coordinator; callbacks passed at invoke time.
- Selectors: used by DiagnosticsPage (and can be extended to other pages).
- Store review selection: written by controller and page (group select, load_result); read by controller for plan.

---

## How to use this doc

When changing a listed path, add a "Remove when" or "Accepted until" note in code (e.g. `# Transitional: remove when ScanPage is store-only.`) and update this file. When a path is removed, delete or mark it completed here.
