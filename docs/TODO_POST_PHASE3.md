# Post–Phase 3 backlog (action immediately after Phase 3 closure)

Work items deferred from the UI migration plan or explicitly left for **after** Phases 1–3 are complete.  
Treat this as the next sprint queue; link PRs to items here.

---

## P0 — Review / controller boundaries

- [ ] Remove **ReviewController** dependency on **page-private** widgets (`_workspace`, `_safety_panel`, `_workspace_delete_btn`) in legacy `ReviewPage`; drive review chrome only via **store slices** + **IReviewCallbacks** (or a narrow `ReviewViewPort` protocol with no widget types).
- [ ] Migrate **CTK Review** to populate **review.index / review.plan / review.preview** store slices from projections or controller (not only `review.selection`).
- [ ] Ensure **execute deletion** never uses silent `preview_deletion` fallback without user-visible notice (toast or inline error).

## P0 — Store-first pages (remaining surfaces)

- [ ] **Legacy ScanPage**: remove direct `coordinator` / `attach_hub` where store+selectors can suffice; align with CTK scan page contract.
- [ ] **History / Diagnostics (ttk)**: replace remaining `coordinator` calls with `HistoryApplicationService` / `ApplicationRuntime` passed from shell.
- [ ] **Settings**: route persisted engine prefs through `SettingsApplicationService` only in shells (already partially available).

## P1 — UI degraded mode visibility

- [ ] Surface **`UiDegradedFlags`** in primary shell (banner or status line when `theme_apply_failed`).
- [ ] Wire **legacy `CerebroApp`** theme failures to same `UiDegradedFlags` path as CTK.

## P1 — Performance / virtualization

- [ ] Review **large file lists** on Review (virtualized navigator already optional via env); validate no callbacks target destroyed widgets after navigation.
- [ ] Tune **`THROTTLE_MS`** / `_METRICS_COALESCE_MS` under benchmark (`docs/BOTTLENECK_ANALYSIS.md`).

## P1 — Engine / deletion (beyond Phase 3 scope)

- [ ] Full **`deletion.py`** audit: replace remaining broad `except` with logged outcomes on every destructive branch.
- [ ] **Pipeline** progress emission: align event frequency with hub throttle matrix (document in `ProjectionHub`).

## P2 — Tests

- [ ] **Integration**: `ProjectionHubStoreAdapter` metrics coalescing with a real `tk.Tk` (or headless) — assert order terminal vs metrics.
- [ ] **Controller intents**: `ScanController` / `ReviewController` with mocked `ScanApplicationService`.
- [ ] **Regression**: destroyed-widget / thumbnail callbacks (per engineering review).

## P2 — Docs / hygiene

- [ ] Single **architecture diagram** (Mermaid) in `docs/` linking UI → services → orchestration → engine.
- [ ] Update **`BOUNDARY_AUDIT.md`** when Review page loses coordinator coupling.
- [ ] **`pipeline.py` / `models.py` split** — only if product needs it (explicitly deferred).

## Explicit non-goals (do not start from this list without a new ADR)

- Asyncio / async file I/O for discovery.
- Full **`pipeline.py`** decomposition in one PR.
- Large repository schema redesign.

---

*Generated to track follow-up after Phases 1–3 migration work; trim or re-prioritize as the product evolves.*
