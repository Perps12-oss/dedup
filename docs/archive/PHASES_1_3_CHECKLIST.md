# Phases 1–3 migration checklist (CEREBRO DEDUP)

Living checklist aligned with the **UI migration plan** (authority, store-first, services, reliability, legacy demotion).

## Phase 1 — Authority, boundaries, engine-facing contracts

| Item | Status |
|------|--------|
| Primary UI = **CTK**; legacy **ttk** non-default | Done (`dedup/main.py`, `README.md`, `docs/UI_AUTHORITY.md`) |
| **`ApplicationRuntime`** + application services | Done (`dedup/application/`) |
| **Controllers** use services, not raw coordinator | Done (`ScanController`, `ReviewController`) |
| **Path policy** `canonical_scan_root` | Done (`dedup/infrastructure/path_policy.py`, used in `ScanController`) |
| **Metrics scope selectors** (session / phase / result) | Done (`dedup/ui/state/selectors.py`) |
| **`UiDegradedFlags`** + theme failure → store | Done (`UiDegradedFlags`, `CerebroCTKApp._apply_theme_from_settings`) |
| Critical **logging** (CTK shell, theme manager, deletion touchpoints) | Done (prior commits + ongoing) |
| **Silent** subscriber loops in store | Avoided (subscribers still log-only; no recursive state on failure) |

## Phase 2 — Parity, stabilization, legacy demotion

| Item | Status |
|------|--------|
| Default entry **CTK** | Done |
| **Hub → store** extra metrics coalescing | Done (`ProjectionHubStoreAdapter` 100ms last-wins) |
| Feature parity matrix | Documented (`docs/UI_PARITY_MATRIX.md`) |
| Legacy UI documented | Done (`dedup/ui/legacy/README.md`) |

## Phase 3 — Cleanup, tests, documentation

| Item | Status |
|------|--------|
| **Post-Phase 3 TODO** queue | Done (`docs/TODO_POST_PHASE3.md`) |
| Tests: path policy + selectors | Added (`dedup/tests/test_path_policy.py`, `test_selectors_metrics_scopes.py`) |
| **Engineering status** pointer | Update in same PR as checklist |

## Follow-up

See **`docs/TODO_POST_PHASE3.md`** for the next sprint (Review widget decoupling, degraded banner, expanded tests).
