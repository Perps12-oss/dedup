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
- **Nav + app:** `themes` route, `ThemePage` registered, **Ctrl+7** global shortcut.
- Doc: `docs/THEME_SYSTEM.md`.

### Skipped / why

- **Gradient editor** (multi-stop, draggable): large Canvas UX project.
- **ThemeConfig persistence** in app settings beyond export bundle / system light-dark auto-detect: depends on editor + product decision.
- **Real-time colour interpolation** (`lerp_color` transitions): optional polish; respect `reduced_motion` first.
- **Token usage audit** (every key in `theme_tokens.py`): defer to avoid churn during UI refactors.

### Sub-phase before Phase 3 deep UX

- “Recent 5 customs” list (still open).
- Add minimal gradient preview (read-only multi-stop from preset tokens only).

---

## Phase 3 — Frontend UX

### Done

- `dedup/ui/shell/shortcut_registry.py` + `CerebroApp` refactored to use it; help dialog lists registered shortcuts.
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

### Skipped / why

- **VirtualTree**, **debounced filters**, **optimistic deletion UI**, **ProcessPoolExecutor** hashing changes: need design + benchmarks.
- **Global ErrorBoundary** wrapping every Tk command: high touch; use `safe_ui_call` selectively first.

### Sub-phase

- Prototype `VirtualTree` for Review navigator behind feature flag.
- Profile discovery/hashing with `engine/bench.py`; append results to `BENCHMARK_BASELINE.md`.

---

## Phase 5 — Dual-mode UI

### Done

- `UIAppState.ui_mode` + `UIStateStore.set_ui_mode`.
- Startup sync from `AppSettings.advanced_mode`.
- `_on_advanced_mode` updates store; advanced toggle **persists** via `UIState.save()` in `AppShell`.

### Skipped / why

- **Per-page conditional layouts** driven only by `ui_mode` (vs existing granular `AppSettings` flags): requires coordinated page edits.

### Sub-phase

- Gate **Export** (optional), diagnostics tiles, and compare mode entry points when `ui_mode == "simple"`.

---

## Phase 6 — Feature evaluation

### Done

- Documented stub buttons and deferral in `button_functionality_audit.md` + this file.

### Skipped / why

- No telemetry in app — usage-based pruning is manual/product decision.

### Sub-phase

- Review `UI_CONSISTENCY_AUDIT.md` + `BACKLOG.md`; move low-value items to Advanced-only or remove.

---

## Phase 7 — Standards & DX

### Done

- `docs/CONTRIBUTING.md` (this repo).
- Pointers in `THEME_SYSTEM.md`, `MODE_TOGGLE.md`, `PHASE_ROLLOUT.md`.

### Skipped / why

- Full WCAG AA verification across all themes.
- Root `README.md` (repo currently uses `docs/README.md`); add symlink or root stub if publishing to GitHub.

### Sub-phase

- Contrast fixes for any preset failing AA for body text.
- Expand type hints on `ui/` after mypy clean on `engine/`.

---

## Sub-phase ordering (recommended)

1. ~~Phase 1 follow-up~~ **Done:** Ruff clean, format, pre-commit, pip-audit JSON, vulture, button audit doc, runtime notes. *Remaining optional:* pylint, pydeps, GUI soak, mypy green.  
2. Phase 2 follow-up: JSON theme export/import (no draggable editor yet).  
3. Phase 3 follow-up: Toast wiring + remove/hide Export stubs.  
4. Phase 4 follow-up: VirtualTree spike + benchmark refresh.  
5. Phase 5 follow-up: page-level `ui_mode` gates.  
6. Phase 7: contrast remediation for failing presets.
