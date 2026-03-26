# Post–Phase 3 backlog (action immediately after Phase 3 closure)

Work items deferred from the UI migration plan or explicitly left for **after** Phases 1–3 are complete.  
Treat this as the next sprint queue; link PRs to items here.

---

## P0 — Review / controller boundaries

- [ ] Remove **ReviewController** dependency on **page-private** widgets (`_workspace`, `_safety_panel`, `_workspace_delete_btn`) in legacy `ReviewPage`; drive review chrome only via **store slices** + **IReviewCallbacks** (or a narrow `ReviewViewPort` protocol with no widget types).
- [x] Migrate **CTK Review** to populate **review.index / review.plan / review.preview** store slices from projections or controller (not only `review.selection`). *(Store setters + `_push_review_slices_to_store` on load/selection.)*
- [x] Ensure **execute deletion** never uses silent `preview_deletion` fallback without user-visible notice (toast or inline error). *(Controller + legacy fallback use warning + return.)*

## P0 — Store-first pages (remaining surfaces)

- [x] **Legacy ScanPage**: remove direct `coordinator` — use **`ScanApplicationService`** (`scan_service`) for fallback paths; shell passes `self._runtime.scan`.
- [x] **History / Diagnostics (ttk)**: **`HistoryApplicationService`** / **`ApplicationRuntime`** from shell (`CerebroApp`).
- [ ] **Settings**: route persisted engine prefs through `SettingsApplicationService` only in shells (already partially available).

## P1 — UI degraded mode visibility

- [x] Surface **`UiDegradedFlags`** in primary shell (banner or status line when `theme_apply_failed`). **CTK:** banner in `CerebroCTKApp`. **ttk:** `AppShell.set_degraded_banner` + store subscription in `CerebroApp`.
- [x] Wire **legacy `CerebroApp`** theme failures to same **`UiDegradedFlags`** path as CTK (`_apply_scene_theme` try/except + `clear_theme_degraded` on success).

## P1 — Performance / virtualization

- [ ] Review **large file lists** on Review (virtualized navigator already optional via env); validate no callbacks target destroyed widgets after navigation.
- [ ] Tune **`THROTTLE_MS`** / `_METRICS_COALESCE_MS` under benchmark (`docs/BOTTLENECK_ANALYSIS.md`).

## P1 — Engine / deletion (beyond Phase 3 scope)

- [x] **`deletion.py` audit (incremental):** progress callback `except Exception` now **logs** instead of silent pass; remaining handlers are narrow OS/import paths or return error tuples.
- [ ] **Pipeline** progress emission: align event frequency with hub throttle matrix (document in `ProjectionHub`).

## P2 — Tests

- [x] **Integration:** `ProjectionHubStoreAdapter` — `dedup/tests/test_hub_adapter.py` (session, terminal+metrics flush, compat/events, stop).
- [ ] **Controller intents:** `ScanController` / `ReviewController` with mocked `ScanApplicationService`.
- [ ] **Regression:** destroyed-widget / thumbnail callbacks (per engineering review).

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
