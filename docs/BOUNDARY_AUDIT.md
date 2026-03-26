# Backend/UI Boundary Audit

Audit of page/widget coupling to VM, coordinator, and UI internals. Classifications: **allowed** (intended contract), **transitional** (migrate in boundary hardening), **legacy** (remove when replaced).

**Last updated:** 2025-03 — reflects `ApplicationRuntime` services, `ScanApplicationService` on legacy ScanPage fallbacks, hub→store adapter, and degraded UI banners.

---

## 1. ScanPage

| Coupling | Type | Location | Notes |
|----------|------|----------|--------|
| `scan_service` (`ScanApplicationService`) | **Allowed** | __init__ | Fallback start/cancel when controller path is not used; no direct `ScanCoordinator` field. |
| `scan_controller` | **Allowed** | primary start/resume | `ScanController` owns coordinator calls for normal operation. |
| `attach_hub(hub)` / `attach_store(store)` | **Transitional** | app._wire_hub | Hub can still feed VM; primary path is ProjectionHub → `ProjectionHubStoreAdapter` → store → `attach_store`. |
| `self.vm.apply_*_projection` | **Transitional** | subscribers | VM is display sink; target: selectors(store) only. |
| `self.vm` lifecycle / `is_scanning` | **Transitional** | _render_*, start_scan | Local VM state; align with store scan slice over time. |

**Summary:** ScanPage uses **ScanController + ScanApplicationService** (no raw coordinator on the page). Hub/VM coupling remains transitional until display reads go through selectors + store only.

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
| `runtime` (`ApplicationRuntime`) | **Allowed** | __init__ | Uses `runtime.scan` / `runtime.history` for actions (no `ScanCoordinator` import). |
| `attach_store(store)` | **Allowed** | app._build_pages | Page subscribes to store; renders from state.mission. |
| `on_request_refresh` → `_refresh_mission_state` | **Transitional** | on_show | App pushes mission slice via `HistoryApplicationService` + `ScanApplicationService` into `set_mission`. |
| `add_recent_folder` | **Transitional** | folder pick | Action on runtime history service. |
| `self.vm.refresh_from_mission_state(state)` | **Allowed** | attach_store subscriber | VM populated from store; OK. |
| `self.vm.refresh_from_coordinator` | **Transitional** | _refresh fallback | Name legacy; implementation accepts coordinator or service duck-type. |

**Summary:** Mission receives **`ApplicationRuntime`**; refresh uses **application services**, not raw coordinator wiring from the shell.

---

## 4. HistoryPage

| Coupling | Type | Location | Notes |
|----------|------|----------|--------|
| `history` (`HistoryApplicationService`) | **Allowed** | __init__ | Load/delete/resume use the service API. |
| `attach_store(store)` | **Allowed** | app._build_pages | Page subscribes; renders from state.history. |
| `on_request_refresh` → `_refresh_history_state` | **Transitional** | on_show | App builds `HistoryProjection` via `build_history_from_coordinator(history_service)` and `set_history`. |
| `self.vm.refresh(source)` | **Transitional** | _refresh | Accepts coordinator or service (`getattr(..., "coordinator", source)`). Prefer service. |
| `self.vm.refresh_from_history(history)` | **Allowed** | store subscriber | VM from store; OK. |

**Summary:** History is **service-backed** and store-fed on show; no direct coordinator field on the page.

---

## 5. DiagnosticsPage

| Coupling | Type | Location | Notes |
|----------|------|----------|--------|
| `runtime` (`ApplicationRuntime`) | **Allowed** | __init__ | Exposes `runtime.coordinator` for persistence/history/detail until a diagnostics service exists. |
| `attach_store(store)` | **Allowed** | app._wire_hub | Renders live scan slice from store. |
| `self.vm.session/phases/compat/events_log` | **Allowed** | _on_state from store | VM updated from store; OK. |
| `self.vm.load(self.coordinator, session_id)` | **Transitional** | session detail | Uses coordinator from runtime; could become a dedicated read model. |

**Summary:** Diagnostics takes **`ApplicationRuntime`**; primary scan telemetry is **store-driven**; coordinator remains for session DB/detail **transitional** paths.

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
| `self.coordinator` | **Allowed** | hub `event_bus`, `ProjectionHub` | Single orchestration root; feature code should prefer `self._runtime.scan` / `history` / `review`. |
| `self._runtime.scan.get_last_result()`, `_review.load_result` | **Transitional** | _on_terminal (hub subscriber) | Completion flow; could become review slice / intent only. |
| `_refresh_mission_state`, `_refresh_history_state` | **Transitional** | Mission/History on_show | App builds slices via **application services** + `set_mission` / `set_history`. |
| `UiDegradedFlags` + `AppShell.set_degraded_banner` | **Allowed** | theme apply failure | User-visible banner when theme apply fails; store is source of truth. |
| StatusStrip.subscribe_to_hub + subscribe_to_store | **Transitional** | _wire_hub | StatusStrip uses both; could converge on store-only. |

---

## Allowed vs transitional vs legacy (summary)

- **Allowed:** Store subscribe/attach_store; VM updated from store; intents emitted to controller; coordinator owned at app for hub/event bus; application services for scan/history/review; Settings UIState + callbacks; degraded UI flags + banner.
- **Transitional:** ScanPage hub + VM projections; ReviewController holding page ref and page.vm/_workspace/_safety_panel; Mission/History refresh-on-show (service-based); Diagnostics coordinator for session detail; app terminal handler.
- **Legacy:** ReviewController’s use of page internals (_workspace, _safety_panel, vm) — to be removed in ReviewController cleanup.

---

## Next steps (boundary hardening)

1. **Selectors:** Have Scan/Review read via `dedup/ui/state/selectors.py` everywhere (partially started).
2. **ReviewController cleanup:** Feed controller from store (review slices) + coordinator only; remove page ref; ReviewPage reacts to store for workspace/safety panel.
3. **Scan display path:** Drop redundant hub→VM path once ScanPage reads only from store projections.
4. **Transitional paths:** Keep one-line "remove when" notes in code at seam points.

---

## 9. Reference diagram

See [ARCHITECTURE_UI.md](ARCHITECTURE_UI.md) for a UI → services → orchestration → engine diagram (Mermaid).
