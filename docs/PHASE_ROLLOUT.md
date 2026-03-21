# Multi-phase rollout log

This document tracks what was implemented vs deferred across the seven-phase specification.

---

## Phase 1 — Repository audit & analysis

### Done

- `pyproject.toml` tooling (`pytest`, `ruff`, `mypy`).
- `requirements-dev.txt`.
- Generated: `docs/ruff_issues.txt`, `docs/mypy_issues.txt`, `docs/vulture_report.txt`, `docs/pip_outdated.txt`.
- Written: `AUDIT_REPORT_PHASE1.md`, `DEPENDENCY_AUDIT.md`, `dead_code_inventory.md`, `ARCHITECTURE_REVIEW.md`, `button_functionality_audit.md` (starter table + stubs), `runtime_warnings.md` (template).

### Skipped / why

- **Pylint export:** overlaps Ruff; enable later on `engine/` only.
- **pip-audit JSON:** network-dependent; run locally and save as `docs/pip_audit_report.json`.
- **pydeps SVG:** needs Graphviz; run when available.
- **Manual GUI soak:** capture stderr into `runtime_warnings.md` during QA.
- **Per-button exhaustive inventory:** time-intensive; extend `button_functionality_audit.md` in Phase 3 sub-pass.

### When to implement skipped items

- After Ruff auto-fix pass: add `pre-commit` with `ruff check` + `ruff format`.
- Before release: `pip-audit`, refresh `pip_outdated`, complete button table, one GUI soak.

---

## Phase 2 — Theme page & color system

### Done

- `dedup/ui/theme/contrast.py` (WCAG luminance / ratio).
- `dedup/ui/theme/theme_config.py` (`ThemeConfig` dataclass).
- `dedup/ui/pages/theme_page.py` — preset swatches + contrast snapshot; subscribes to `ThemeManager`.
- **Nav + app:** `themes` route, `ThemePage` registered, **Ctrl+7** global shortcut.
- Doc: `docs/THEME_SYSTEM.md`.

### Skipped / why

- **Gradient editor** (multi-stop, draggable): large Canvas UX project.
- **ThemeConfig persistence** / system light-dark auto-detect: depends on editor + product decision.
- **Real-time colour interpolation** (`lerp_color` transitions): optional polish; respect `reduced_motion` first.
- **Token usage audit** (every key in `theme_tokens.py`): defer to avoid churn during UI refactors.

### Sub-phase before Phase 3 deep UX

- Implement JSON import/export for `ThemeConfig` + “recent 5 customs” list.
- Add minimal gradient preview (read-only multi-stop from preset tokens only).

---

## Phase 3 — Frontend UX

### Done

- `dedup/ui/shell/shortcut_registry.py` + `CerebroApp` refactored to use it; help dialog lists registered shortcuts.
- `dedup/ui/components/toast_manager.py` (stub API; no call sites yet).
- Button audit doc started (known Export stubs called out).

### Skipped / why

- **Breadcrumbs**, **validators.py**, full **ToastManager** wiring, **hover style maps** for every ttk style: scope too large for one pass.
- **Micro-interactions / Canvas ripple:** optional.

### Sub-phase

- Wire `ToastManager` after scan complete / theme apply.
- Replace `lambda: None` Export buttons or hide in Simple mode.
- Finish button inventory rows for each page.

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

- Gate “Export”, diagnostics tiles, and compare mode entry points when `ui_mode == "simple"`.

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

1. Phase 1 follow-up: Ruff `--fix`, pip-audit, button table completion.  
2. Phase 2 follow-up: JSON theme export/import (no draggable editor yet).  
3. Phase 3 follow-up: Toast wiring + remove/hide Export stubs.  
4. Phase 4 follow-up: VirtualTree spike + benchmark refresh.  
5. Phase 5 follow-up: page-level `ui_mode` gates.  
6. Phase 7: contrast remediation for failing presets.
