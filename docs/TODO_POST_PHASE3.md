# Post–Phase 3 backlog (action immediately after Phase 3 closure)

Work items deferred from the UI migration plan or explicitly left for **after** Phases 1–3 are complete.  
Treat this as the next sprint queue; link PRs to items here.

---

## P0 — Review / controller boundaries

- [x] Remove **ReviewController** dependency on **page-private** widgets (`_workspace`, `_safety_panel`, …) where still referenced; drive review chrome only via **store slices** + **IReviewCallbacks** (or a narrow `ReviewViewPort` protocol with no widget types). *(Implemented: `ReviewController` uses `IReviewCallbacks` only; CTK Review implements the protocol.)*
- [x] Migrate **CTK Review** to populate **review.index / review.plan / review.preview** store slices from projections or controller (not only `review.selection`). *(Store setters + `_push_review_slices_to_store` on load/selection.)*
- [x] Ensure **execute deletion** never uses silent `preview_deletion` fallback without user-visible notice (toast or inline error). *(Controller + legacy fallback use warning + return.)*

## P0 — Store-first pages (remaining surfaces)

- [x] **Legacy ScanPage**: remove direct `coordinator` — use **`ScanApplicationService`** (`scan_service`) for fallback paths; shell passes `self._runtime.scan`. *(Superseded: legacy pages removed; CTK-only.)*
- [x] **History / Diagnostics (ttk)**: **`HistoryApplicationService`** / **`ApplicationRuntime`** from shell. *(Superseded: `CerebroCTKApp` + services.)*
- [x] **Settings**: route persisted UI prefs through **`SettingsApplicationService.persist_ui_preferences`** / `load_ui_preferences` (`dedup/infrastructure/ui_settings.py`); `UIState.attach_settings_service` wires the CTK shell. Engine `Config` remains `SettingsApplicationService.load` / `save`.

## P1 — UI degraded mode visibility

- [x] Surface **`UiDegradedFlags`** in **CTK** shell (banner when `theme_apply_failed`).
- [x] Legacy **`CerebroApp`** / ttk **`AppShell`** path removed — no separate wire-up.

## P1 — Performance / virtualization

- [x] Review **large file lists** on Review (virtualized navigator already optional via env); validate no callbacks target destroyed widgets after navigation. *(Guards: `ReviewPageCTK._ui_alive()` + tests.)*
- [x] Tune **`THROTTLE_MS`** / `_METRICS_COALESCE_MS` under benchmark (`docs/BOTTLENECK_ANALYSIS.md`). *(`hub_adapter._METRICS_COALESCE_MS` derived from `THROTTLE_MS["metrics"]`.)*

## P1 — Engine / deletion (beyond Phase 3 scope)

- [x] **`deletion.py` audit (incremental):** progress callback `except Exception` now **logs** instead of silent pass; remaining handlers are narrow OS/import paths or return error tuples.
- [x] **Pipeline** progress emission: align event frequency with hub throttle matrix (document in `ProjectionHub`). *(Doc rules + comment in `pipeline.py` discovery path.)*

## P2 — Tests

- [x] **Integration:** `ProjectionHubStoreAdapter` — `dedup/tests/test_hub_adapter.py` (session, terminal+metrics flush, compat/events, stop).
- [x] **Controller intents:** `ScanController` / `ReviewController` with mocked `ScanApplicationService` / `ReviewApplicationService` — `dedup/tests/test_controller_application_services.py`.
- [x] **Regression:** destroyed-widget / thumbnail callbacks (per engineering review) — `test_review_refresh_heroes_noop_after_host_destroyed`.

## P2 — Docs / hygiene

- [x] **Architecture diagram (Mermaid):** `docs/ARCHITECTURE_UI.md`.
- [x] Update **`BOUNDARY_AUDIT.md`** when Review page loses coordinator coupling *(refreshed for services + Scan + banners + diagram link)*.
- [ ] **`pipeline.py` / `models.py` split** — only if product needs it (explicitly deferred).

## Explicit non-goals (do not start from this list without a new ADR)

- Asyncio / async file I/O for discovery.
- Full **`pipeline.py`** decomposition in one PR.
- Large repository schema redesign.

---

*Generated to track follow-up after Phases 1–3 migration work; trim or re-prioritize as the product evolves.*
