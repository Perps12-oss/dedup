# Backend/UI Boundary Audit

Audit of page/widget coupling to VM, coordinator, and UI internals. Classifications: **allowed** (intended contract), **transitional** (migrate in boundary hardening), **legacy** (remove when replaced).

---

## 1. ScanPage

| Coupling | Type | Location | Notes |
|----------|------|----------|--------|
| `self.coordinator` | **Transitional** | __init__, start_scan, start_resume, cancel_scan | Should become ScanController + intents; page emits only. |
| `attach_hub(hub)` | **Transitional** | app._wire_hub → ScanPage.attach_hub | Hub pushes to VM; target: store subscription, VM fed from store or hub→store only. |
| `self.vm.apply_session_projection` / `apply_phase_projection` / etc. | **Transitional** | _on_session, _on_phases, _on_metrics, _on_compat, _on_events_log, _on_terminal | VM is direct sink of hub; target: page reads from store via selectors, hub→store adapter owns updates. |
| `self.vm.is_scanning`, `self.vm._start_wall` | **Transitional** | _render_*, start_scan, cancel_scan | UI state in VM; could move to store or stay local until ScanController drives lifecycle. |
| `self.vm.session`, `self.vm.phases`, `self.vm.phase_metrics`, etc. | **Transitional** | _render_* throughout | Page reads VM for display; target: selectors(store). |
| `coordinator.start_scan`, `coordinator.cancel_scan` | **Transitional** | start_scan, start_resume, _on_cancel | Target: page emits intent → ScanController calls coordinator. |

**Summary:** ScanPage is hub- and coordinator-coupled. No store subscription yet. Full intent/controller pattern not applied.

---

## 2. ReviewPage

| Coupling | Type | Location | Notes |
|----------|------|----------|--------|
| `self.coordinator` | **Transitional** | _create_plan, execute_deletion (via controller or legacy path) | Controller already holds coordinator; page should not call coordinator directly when controller present. |
| `self.vm` (keep_selections, set_keep, clear_keep, delete_count, etc.) | **Transitional** | Throughout; also ReviewController uses page.vm | Target: review slice in store; controller reads/writes store + coordinator; page reads store via selectors. |
| `self._workspace`, `self._safety_panel` | **Legacy (controller)** | ReviewController._load_workspace, _update_safety_panel | Controller holds page ref and calls page._workspace.load_group, page._safety_panel.update_plan. Target: controller updates store; page subscribes and refreshes UI from store. |
| `ReviewController.attach_page(self._review)` | **Transitional** | app._build_pages | Controller should not hold page reference; should use store + coordinator only. |
| `self._review_controller.handle_*` | **Allowed** | _on_set_keep, _on_clear_keep, _on_preview_intent, _on_execute_intent | Page emits to controller; contract is correct. |
| `coordinator.create_deletion_plan`, `coordinator.execute_deletion` | **Allowed** (when via controller) | ReviewController | Coordinator calls belong in controller. |

**Summary:** Review intents and controller exist; controller is a half-step because it depends on page (VM, workspace, safety_panel) instead of store.

---

## 3. MissionPage

| Coupling | Type | Location | Notes |
|----------|------|----------|--------|
| `attach_store(store)` | **Allowed** | app._build_pages | Page subscribes to store; renders from state.mission. |
| `on_request_refresh` → `_refresh_mission_state` | **Transitional** | on_show | App pushes mission slice from coordinator to store; acceptable for now. Document as transitional. |
| `self.coordinator.get_resumable_scan_ids`, `add_recent_folder` | **Transitional** | _refresh (fallback), _update_recent_sessions, _on_folder_select, _on_resume | When store-driven, resumable_scan_ids come from state.mission; legacy path still uses coordinator. add_recent_folder is an action → could be intent. |
| `self.vm.refresh_from_mission_state(state)` | **Allowed** | attach_store subscriber | VM populated from store; OK. |
| `self.vm.refresh_from_coordinator` | **Transitional** | _refresh (no-controller path) | Fallback when no store; keep until store is sole source. |

**Summary:** Mission is store-fed when possible; coordinator used for refresh trigger and legacy path. Document as transitional.

---

## 4. HistoryPage

| Coupling | Type | Location | Notes |
|----------|------|----------|--------|
| `attach_store(store)` | **Allowed** | app._build_pages | Page subscribes; renders from state.history. |
| `on_request_refresh` → `_refresh_history_state` | **Transitional** | on_show | App builds HistoryProjection from coordinator and set_history; acceptable. |
| `self.coordinator.load_scan`, `delete_scan` | **Transitional** | _on_load, _on_delete | Actions; could be intents (LoadScan, DeleteScan) handled by app or controller. |
| `self.vm.refresh(self.coordinator)` | **Transitional** | _refresh (no store path) | Fallback. |
| `self.vm.refresh_from_history(history)` | **Allowed** | store subscriber | VM from store; OK. |

**Summary:** History is store-fed on show; coordinator used for load/delete and refresh. Document as transitional.

---

## 5. DiagnosticsPage

| Coupling | Type | Location | Notes |
|----------|------|----------|--------|
| `attach_store(store)` | **Allowed** | app._wire_hub (actually app._build_pages / _wire_hub) | Renders from store (scan slice). |
| `self.coordinator` | **Transitional** | get_history, load(session_id), persistence | Session list and detail load from coordinator; could be store slice or dedicated diagnostics refresh. |
| `self.vm.session/phases/compat/events_log` | **Allowed** | _on_state from store | VM updated from store; OK. |
| `self.vm.load(self.coordinator, session_id)` | **Transitional** | _on_session_select, _on_session_double_click | Coordinator used for detail; could be store or intent. |

**Summary:** Diagnostics reads scan from store; still uses coordinator for history/detail. Acceptable transitional.

---

## 6. SettingsPage

| Coupling | Type | Location | Notes |
|----------|------|----------|--------|
| `self._state` (UIState) | **Allowed** | Docstring defines state/action boundary | Settings read from UIState.settings; actions via callbacks. No store migration required. |

**Summary:** No change needed; boundary already documented.

---

## 7. ReviewController (implementation detail)

| Coupling | Type | Location | Notes |
|----------|------|----------|--------|
| `self._page` | **Transitional** | attach_page, handle_* | Controller should not hold page; should read review slice from store and coordinator; write plan/result back to store; page subscribes to store and updates workspace/safety panel from state. |
| `getattr(self._page, "vm", None)` | **Transitional** | handle_set_keep, handle_clear_keep, etc. | Replace with store.review.selection + store updates. |
| `_load_workspace(self._page, group_id)` | **Transitional** | Helper uses page._workspace, page._current_result, page.vm | Replace with store-driven refresh; page subscribes and calls _load_workspace from state. |
| `_update_safety_panel(self._page)` | **Transitional** | Same | Panel gets data from store (review.plan slice) or from VM that was updated from store. |
| `self._coordinator.execute_deletion`, `create_deletion_plan` | **Allowed** | handle_execute_deletion, handle_preview_deletion (plan from create_plan) | Coordinator calls in controller are correct. |

**Summary:** ReviewController cleanup = remove page ref; feed from store + coordinator; update store; let page react to store.

---

## 8. App-level

| Coupling | Type | Location | Notes |
|----------|------|----------|--------|
| `self.coordinator.get_last_result()`, `_review.load_result(result)` | **Transitional** | _on_terminal (hub subscriber) | Completion flow; could be store.terminal → app pushes result to review slice or triggers load_result via intent. |
| `_refresh_mission_state`, `_refresh_history_state` | **Transitional** | Called on Mission/History on_show | App builds slice from coordinator and store.set_mission/set_history. Document as explicit transitional path. |
| StatusStrip.subscribe_to_hub + subscribe_to_store | **Transitional** | _wire_hub | StatusStrip uses both; intent comes from store. Phase/session could come from store only once ScanPage is store-driven. |

---

## Allowed vs transitional vs legacy (summary)

- **Allowed:** Store subscribe/attach_store; VM updated from store; intents emitted to controller; coordinator called only from app or controller; Settings UIState + callbacks.
- **Transitional:** ScanPage hub + coordinator; ReviewController holding page ref and page.vm/_workspace/_safety_panel; Mission/History refresh-on-show building slice from coordinator; Diagnostics coordinator for history/detail; app terminal handler and refresh callbacks. Document and either accept temporarily or add "remove when …" note.
- **Legacy:** ReviewController’s use of page internals (_workspace, _safety_panel, vm) — to be removed in ReviewController cleanup.

---

## Next steps (boundary hardening)

1. **Selectors:** Add `dedup/ui/state/selectors.py`; have at least one page (Scan or Review) read via selectors.
2. **ReviewController cleanup:** Feed controller from store (review slices) + coordinator only; controller updates store; remove attach_page and page ref; ReviewPage subscribes to store and updates workspace/safety panel from state.
3. **Scan command flow:** Introduce ScanController (or equivalent); ScanPage emits intents; scan intent lifecycle driven by controller; ScanPage eventually subscribes to store instead of hub for display.
4. **Transitional paths:** This document serves as the explicit list; add one-line "remove when" notes in code where appropriate (e.g. "Transitional: remove when ScanController drives scan lifecycle").
