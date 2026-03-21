# Multi-phase rollout log

This document tracks what was implemented vs deferred across the seven-phase specification.

**For the latest “what works today” summary**, see **`docs/ENGINEERING_STATUS.md`** (update that file as you continue; use this file for phase boundaries and historical deferrals).

---

## Phase 1 — Repository audit & analysis

### Done (completion pass)

- **Ruff:** `ruff check dedup` clean; `ruff format` applied; `docs/ruff_issues.txt` refreshed.
- **Pre-commit:** `.pre-commit-config.yaml`; `pre-commit` in `requirements-dev.txt`.
- **pip-audit / outdated:** `docs/pip_audit_report.json`, `docs/pip_outdated.txt` refreshed.
- **Vulture:** clean (`docs/vulture_report.txt`); unused-arg fixes in `review_workspace` / `status_strip`.
- **Mypy snapshot:** `docs/mypy_issues.txt` refreshed (typing backlog remains).
- **Buttons / runtime:** `button_functionality_audit.md` expanded; `runtime_warnings.md` has pytest + thread-note.
- **AUDIT_REPORT_PHASE1.md** marked complete.

### Optional later

- Pylint on `dedup/engine` only; pydeps + Graphviz; interactive GUI soak log; drive mypy to green.

---

## Phase 2 — Theme page & color system

### Done

- `dedup/ui/theme/contrast.py` (WCAG luminance / ratio).
- `dedup/ui/theme/theme_config.py` (`ThemeConfig` dataclass; `from_dict` normalizes JSON gradient stops and clamps `appearance_mode`).
- `dedup/ui/pages/theme_page.py` — preset swatches + contrast snapshot; subscribes to `ThemeManager`; **JSON import/export** (`cerebro_theme_config_v1` bundle: `theme_key`, `theme_config`, `ui` flags).
- **Accent bar gradient tooling:** `AppSettings.custom_gradient_stops` persisted in `ui_settings.json`; `ThemeManager.apply(..., gradient_stops=...)` merges stops into token copy; `gradients.py` multi-stop drawing; **Themes** page editor (stops, preview, Apply / Reset); export/import includes `ThemeConfig.custom_gradient_stops`.
- **Nav + app:** `themes` route, `ThemePage` registered, **Ctrl+7** global shortcut.
- Doc: `docs/THEME_SYSTEM.md`.

### Skipped / why

- **Draggable** gradient stops (Canvas drag UX): not implemented; numeric positions + color picker only.
- **Real-time colour interpolation** (`lerp_color` transitions) between theme switches: optional polish; respect `reduced_motion` first.
- **Token usage audit** (every key in `theme_tokens.py`): defer to avoid churn during UI refactors.

### Sub-phase before Phase 3 deep UX

- “Recent 5 customs” list (still open).

---

## Phase 3 — Frontend UX

### Done

- `dedup/ui/shell/shortcut_registry.py` + `CerebroApp` refactored to use it; help dialog lists registered shortcuts.
- **Global shortcuts (shell):** Ctrl+1–3 Mission / Scan / Review; **Ctrl+4** History; **Ctrl+5** Diagnostics; **Ctrl+7** Themes; **Ctrl+,** Settings; **Ctrl+\\** toggle Insights drawer; **?** shortcut help.
- **Shell alignment:** Nav rail **⇔** cycles density (same as top bar); top bar **Insights** control + drawer **×** call `toggle_drawer` with persisted `show_insight_drawer`; scan bar **Stop for later** vs **Cancel** semantics.
- **Window geometry:** `AppSettings.window_x` / `window_y` (with width/height) persisted on exit when not maximized; restored on launch when set.
- `dedup/ui/components/toast_manager.py` — wired in `CerebroApp`: scan complete (once per `scan_id`), theme change (human-readable name), Themes page export toast.
- Button audit doc (`button_functionality_audit.md`) maintained with shell + page actions.
- **History / Diagnostics Export:** `HistoryPage.export_sessions_json`, `DiagnosticsPage.export_report_json` wired from TopBar (JSON save-as).

### Skipped / why

- **Breadcrumbs**, **validators.py**, **hover style maps** for every ttk style: scope too large for one pass.
- **Micro-interactions / Canvas ripple:** optional.

### Sub-phase

- Optionally hide Export in **Simple** `ui_mode` if product wants a leaner bar.
- Finish deeper per-widget button inventory if needed.

---

## Phase 4 — Engine & core

### Done

- `functools.lru_cache` on `is_image_extension` (`engine/media_types.py`).
- `dedup/ui/utils/error_boundary.py` — `safe_ui_call` helper (opt-in at call sites).
- **Review navigator virtualization (spike):** `dedup/ui/components/virtual_navigator.py` + Review **Group Navigator** windowed rows when `CEREBRO_VIRTUAL_NAV=1` and group count > visible table height; legacy path (2000-row cap) unchanged when flag off.
- **Benchmark log:** `docs/BENCHMARK_BASELINE.md` snapshot table; sample `bench_discovery` run recorded (2026-03-21).

### Skipped / why

- **Full VirtualTree** (hierarchical), **debounced filters**, **optimistic deletion UI**, **ProcessPoolExecutor** hashing changes: need design + benchmarks.
- **Global ErrorBoundary** wrapping every Tk command: high touch; use `safe_ui_call` selectively first.

### Sub-phase

- Extend virtualization to other heavy Treeviews (e.g. workspace file table) if profiling warrants.
- ~~Profile discovery/hashing with `bench_incremental_scan`; append rows to `BENCHMARK_BASELINE.md`.~~ **Done (sample):** `unchanged` scenario row logged 2026-03-21.

---

## Phase 5 — Dual-mode UI

### Done

- `UIAppState.ui_mode` + `UIStateStore.set_ui_mode`.
- Startup sync from `AppSettings.advanced_mode`.
- `_on_advanced_mode` updates store; advanced toggle **persists** via `UIState.save()` in `AppShell`.
- **Simple-mode gates:** contextual **Export** / **Copy Diag**; Diagnostics notebook (Phases-only) + drawer **Compat** row; Review **Compare** control + shortcuts; `_apply_preferences()` keeps Settings ↔ TopBar ↔ store in sync.
- **Mission / Scan:** Simple = compact Mission + Scan left rail; Advanced = `mission_show_*` / `scan_show_*` + new Settings checkboxes; `sync_chrome()` on preference apply.

### Skipped / why

- Deeper per-page reflows beyond Mission/Scan (e.g. History column sets) — only if product asks.

### Sub-phase

- ~~Gate **Export**, diagnostics notebook tabs, insight-drawer Compat, **Copy Diag**, and Review **Compare** when `ui_mode == "simple"`.~~ **Done** — see `docs/MODE_TOGGLE.md`.

---

## Phase 6 — Feature evaluation

### Done

- Documented stub buttons and deferral in `button_functionality_audit.md` + this file.
- **Triage pass:** `docs/UI_CONSISTENCY_AUDIT.md` — Phase 6 table (Simple vs Advanced scope, deferred typography/decision-state/empty-state work). `BACKLOG.md` items are closed or tracked in-repo.

### Skipped / why

- No telemetry in app — usage-based pruning is manual/product decision.

### Sub-phase

- ~~Review `UI_CONSISTENCY_AUDIT.md` + `BACKLOG.md`~~ **Done** (2026-03); remaining rows are explicit **deferred** backlog, not scheduled.

---

## Phase 7 — Standards & DX

### Done

- `docs/CONTRIBUTING.md` (this repo).
- Pointers in `THEME_SYSTEM.md`, `MODE_TOGGLE.md`, `PHASE_ROLLOUT.md`.
- Root `README.md` stub linking into `docs/`.
- **`dedup/scripts/audit_theme_contrast.py`:** programmatic WCAG AA (4.5:1) check for preset text/accent vs base/panel/sidebar; `--strict` for CI; **`docs/THEME_CONTRAST_REPORT.md`** generated via `--md-out`.
- **Token remediation:** `theme_tokens.py` tuned `text_muted` / accent (and related UI tokens where needed) so strict audit passes for all registered presets.

### Skipped / why

- Full manual WCAG pass (focus order, non-text contrast, every widget state) — not automated here.

### Sub-phase

- ~~Root `README.md`~~ **Done:** repo root stub links to `docs/README.md`, `CONTRIBUTING`, `ENGINEERING_STATUS`.
- ~~Contrast fixes for presets failing AA on audited pairs~~ **Done** (see `THEME_CONTRAST_REPORT.md`).
- Expand type hints on `ui/` after mypy clean on `engine/`.

---

## Sub-phase ordering (recommended)

1. ~~Phase 1 follow-up~~ **Done:** Ruff clean, format, pre-commit, pip-audit JSON, vulture, button audit doc, runtime notes. *Remaining optional:* pylint, pydeps, GUI soak, mypy green.  
2. Phase 2 follow-up: JSON theme export/import (no draggable editor yet).  
3. Phase 3 follow-up: Toast wiring + remove/hide Export stubs.  
4. ~~Phase 4 follow-up~~ **Done (spike):** Virtual windowed navigator + `BENCHMARK_BASELINE` discovery + incremental `unchanged` rows. *Remaining:* broader VirtualTree, more scenario rows as needed.  
5. ~~Phase 5 follow-up~~ **Done:** `ui_mode` gates + Mission/Scan layout (`sync_chrome`, Settings toggles for mission/scan panels).  
6. ~~Phase 6 documentation triage~~ **Done.** ~~Phase 7: contrast audit + token remediation~~ **Done** (2026-03-21).
