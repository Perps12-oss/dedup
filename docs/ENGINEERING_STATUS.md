# Engineering status (living document)

**Purpose:** Single place to record **what is implemented now** as the project evolves. Update this file whenever you ship a phase, close an audit item, or change tooling.

**Detailed phase history:** `docs/PHASE_ROLLOUT.md`  
**Phase 1 report:** `docs/AUDIT_REPORT_PHASE1.md`  
**MVVM / next steps (tick in git):** `docs/MVVM_AND_NEXT_CHECKLIST.md`

---

## Current snapshot

| Area | Status | Notes |
|------|--------|--------|
| **Ruff** | Clean | `python -m ruff check dedup`; `ruff format` applied repo-wide |
| **Pre-commit** | Config present | `.pre-commit-config.yaml` → ruff + ruff-format; run `pre-commit install` |
| **Tests** | Passing | `python -m pytest dedup/tests/` |
| **Vulture** (≥80%) | Run locally | `python -m vulture dedup --exclude=__pycache__,tests --min-confidence=70` |
| **pip-audit** (optional deps) | No CVEs in last scan | `docs/pip_audit_report.json` |
| **Mypy** | Not clean | Run per `CONTRIBUTING.md`; backlog tracked in issues / PRs |
| **UI shell** | 7 nav destinations | Mission, Scan, Review, History, Diagnostics, **Themes**, Settings |
| **Store `ui_mode`** | Wired | `simple` / `advanced` synced with `AppSettings.advanced_mode` |
| **Shortcuts** | Registry | `dedup/ui/ctk_shortcuts.py` (CTK shell); Ctrl+1–7 nav; Ctrl+, Settings; `?` help |
| **Button audit** | Living | `docs/button_functionality_audit.md` |
| **History / Diagnostics Export** | Implemented | Top bar **Export** → JSON save-as (`export_sessions_json`, `export_report_json`) |
| **Theme JSON + toasts** | Implemented | Themes page `cerebro_theme_config_v1` import/export (incl. `custom_gradient_stops`); `ToastManager` for scan complete, theme change, export |
| **Accent gradient** | Implemented | `AppSettings.custom_gradient_stops`; `ThemeManager` merge + multi-stop `GradientBar`; Themes page editor |
| **Shell polish** | Implemented | Nav **⇔** density cycle; top-bar Insights toggle; drawer close persists; **Stop for later** on Scan |
| **Window position** | Implemented | `window_x` / `window_y` in `AppSettings` with size (non-maximized exit) |
| **Phase 4 spike** | Opt-in | `CEREBRO_VIRTUAL_NAV=1` → Review Group Navigator uses windowed Treeview rows; `BENCHMARK_BASELINE.md` discovery + incremental `unchanged` rows |
| **Theme contrast audit** | CI-ready | `python -m dedup.scripts.audit_theme_contrast --strict`; report at `docs/THEME_CONTRAST_REPORT.md` |
| **Simple `ui_mode` gates** | Wired | Export / Copy Diag hidden; Diagnostics Phases-only + drawer; Review Compare hidden + shortcuts gated |
| **Mission / Scan simple layout** | Wired | Simple: last-scan–only Mission, Scan left column only; Advanced honors `mission_show_*` / `scan_show_*` + Settings checkboxes |
| **Mission Simple density (Sprint 1 / P0)** | Implemented | Tighter page padding + section gaps in Simple; `rowconfigure(2)` weight only when Recent Sessions row is visible (avoids blank mid-page band) — see `docs/UI_DENSITY_MISSION_SCAN_REVIEW_BLUEPRINT.md` |
| **Bottom status strip (ttk era)** | Removed | Was `dedup/ui/shell/status_strip.py` (legacy shell). **CTK** uses hub → store + page-level surfaces. |
| **Review UX** | CTK + controllers | `ReviewController` + `ToastManager`; `ctk_pages/review_page.py` — parity with old ttk Review Studio is still evolving. |
| **Root README** | Present | `README.md` → `docs/README.md` + contributing + engineering status |
| **Phase 6 triage** | Closed | Simple vs Advanced scope and deferrals recorded in `PHASE_ROLLOUT.md` Phase 6 |

---

## Changelog (append newest first)

### 2026-03-28 — Post–Phase 3 TODO closure (implementation pass)

- **`dedup/infrastructure/ui_settings.py`:** `AppSettings` + JSON persistence (moved out of `ui/utils/ui_state.py`).
- **`SettingsApplicationService`:** `load_ui_preferences` / `persist_ui_preferences`; **`UIState.attach_settings_service`** + **`CerebroCTKApp`** wiring.
- **`ProjectionHub` / `hub_adapter`:** documented pipeline vs hub throttle; metrics coalesce derived from `THROTTLE_MS["metrics"]`.
- **`pipeline.py`:** comment linking discovery progress to hub throttles.
- **`ReviewPageCTK`:** `_ui_alive()` guards for hero/thumbnail paths; controller docstring cleanup.
- **Tests:** `dedup/tests/test_controller_application_services.py` (+ destroyed-host regression).
- **`docs/TODO_POST_PHASE3.md`:** remaining open items cleared except deferred `pipeline`/`models` split.

### 2026-03-28 — MVVM / next-direction checklist

- **`docs/MVVM_AND_NEXT_CHECKLIST.md`:** tickable trace (foundation, core/services, per-page slices, quality, docs). Linked from `docs/README.md` and this file’s header.

### 2026-03-28 — Docs prune (stale audits + generated snapshots)

- **Removed:** superseded trackers/audits (migration tracker, Phase 2 status, transitional seam/path docs, duplicate summaries, UI consistency mega-audit) and committed tool snapshots (ruff/mypy/vulture/pip-outdated/pylint lists, dead-code inventory).
- **Updated:** `CTK_V3_ROADMAP.md`, `PHASE_ROLLOUT.md`, `AUDIT_REPORT_PHASE1.md`, `DEPENDENCY_AUDIT.md`, `BUTTON_HIERARCHY.md` (CTK-oriented), cross-references in `README.md` and blueprints.

### 2026-03-27 — Legacy ttk / ttkbootstrap shell removed

- **Entry:** `python -m dedup` only — `dedup.ui.ctk_app.CerebroCTKApp`. Removed `dedup/ui/app.py`, `dedup/ui/shell/`, legacy `dedup/ui/pages/`.
- **Packaging:** `setup.py` `install_requires` is **`customtkinter>=5.2.0`** (dropped **`ttkbootstrap`**).
- **Components:** ttk widgets under `dedup/ui/components/` kept for tests + `ReviewVM`; see `dedup/ui/components/README.md`.

### 2026-03-25 — UI migration Phases 1–3 (checklist + post-Phase 3 TODO)

- **Authority:** CTK default shell; `docs/UI_AUTHORITY.md`, `PHASES_1_3_CHECKLIST.md`, `TODO_POST_PHASE3.md`.
- **Store:** `UiDegradedFlags`; theme apply failure → store; **ProjectionHubStoreAdapter** coalesces metrics (~100ms) before `set_metrics`.
- **Selectors:** session / phase-local / result-assembly metric scopes (`selectors.py`).
- **Path:** `dedup/infrastructure/path_policy.canonical_scan_root` from `ScanController`.
- **Follow-up:** all remaining items queued in **`docs/TODO_POST_PHASE3.md`**.

### 2026-03-24 — P0 CTK backlog implemented

- **History:** `load_scan` failure → `messagebox.showwarning` (`ctk_app._open_history_scan_in_review`).
- **Cancel:** `ScanCoordinator.start_scan(..., on_cancel=…)` → worker `on_cancel`; CTK `set_scan_busy(False)` on main thread after cooperative cancel.
- **Version:** `dedup.__version__` = `3.0.0-beta.1`; `main.py --version`, `CerebroApp` / `CerebroCTKApp` titles, `setup.py`; roadmap P0 backlog cleared.

### 2026-03-24 — CTK P0 parity walk

- **`docs/CTK_V3_ROADMAP.md`**: P0 items marked done vs open; ordered **P0 backlog** (#1 History load UX, #2 cancel UI sync, #3 version alignment); Phase A table status column.

### 2026-03-24 — CTK v3 roadmap

- **`docs/CTK_V3_ROADMAP.md`**: end goal (CTK-only shell), phased steps (A–D), P0/P1/P2 parity checklist, principles (shared coordinator/core). Linked from `docs/README.md`.

### 2026-03-21 — Review P1: rail DELETE, drawer dedupe, Compare copy, deletion toasts

- **Nav rail:** under **Review**, prominent `DELETE` control (trash + danger border); `CerebroApp._review_delete_from_rail` → `ReviewController.handle_execute_deletion`.
- **Top bar:** Review actions = **Preview Effects** only (DELETE removed from center).
- **Insights drawer:** toggle hidden on Review; `_update_drawer_content("review")` returns no sections (Provenance ribbon + Safety panel hold the same facts on-page).
- **Workspace:** Compare mode buttons rephrased; removed duplicate second row that mirrored keep left/right; table “Keep this file” label.
- **Toasts:** `ReviewController` optional `toast_notify` — messages before confirm, “Deleting…”, then success/partial summary (messagebox retained for partial-failure headline).

### 2026-03-21 — Sprint 2 (P0-S1): Status strip hierarchy + Simple collapse

- `StatusStrip`: vertical group separators; **phase** label uses `text_primary`; `_apply_colors` reapplies engine/warnings semantic colors after theme (fixes muted overwrite).
- **Simple** `ui_mode`: hide **storage** (schema) and **intent** cells; **Advanced**: full strip, `hand2` cursor, click anywhere on strip navigates to **Diagnostics**; session cell hover shows full session id (`CerebroApp._on_status_strip_click`, `set_ui_mode` from `_apply_preferences`).
- Tests: `dedup/tests/test_status_strip.py`.
- Blueprint: `docs/UI_DENSITY_MISSION_SCAN_REVIEW_BLUEPRINT.md` (P0-S1).

### 2026-03-21 — Sprint 1 (P0): Mission Simple density

- **Stage 0 (baseline):** `CerebroApp` root `minsize` **580×320** (`dedup/ui/app.py`); first-run default geometry ≈ **45% × 65%** of primary screen, clamped to mins and caps (`STARTUP_MAX_W_CAP` 1600, `STARTUP_MAX_H_CAP` 1000). Mission Simple vs Advanced layout rules: `MissionPage.sync_chrome()` + store `ui_mode`; content max width remains `AppShell` / `MAX_CONTENT_WIDTH` (see blueprint P0 global density).
- `MissionPage`: Simple mode uses slightly smaller page padding (`_S(5)` vs `_PAD_PAGE`) and `_GAP_MD` between hero → readiness → quick scan; Advanced unchanged.
- Grid: `content` row 2 (Recent Sessions) gets `weight=1` only when that row is shown; `weight=0` when Recent is hidden so extra height does not accumulate in an empty row.
- Blueprint: `docs/UI_DENSITY_MISSION_SCAN_REVIEW_BLUEPRINT.md` (P0-M1, row-weight fix).

### 2026-03-21 — Shell alignment + accent gradient tooling + docs

- Nav rail **⇔** → density cycle; top bar Insights toggle; insight drawer **×** / toggle persist `show_insight_drawer` with save; global shortcuts (Ctrl+4/5, Ctrl+\\ drawer, etc.); window **x/y** persistence; Scan **Stop for later** label.
- **`custom_gradient_stops`** in `AppSettings`; `ThemeManager.apply(..., gradient_stops=...)`; `gradients.py` multi-stop strip; Themes page gradient editor; JSON import/export includes stops; `ToastManager` module docstring.
- Docs: `THEME_SYSTEM.md`, `PHASE_ROLLOUT.md` Phase 2/3, this file.

### 2026-03-21 — Phase 7: theme contrast audit + AA token fixes

- `audit_theme_contrast.py` (`--strict`, `--md-out`); `THEME_CONTRAST_REPORT.md`; `theme_tokens.py` updates for muted text and accent contrast on failing presets; `THEME_SYSTEM.md` + `PHASE_ROLLOUT.md` Phase 7 updated.

### 2026-03-21 — Phase 4: incremental benchmark baseline row

- `BENCHMARK_BASELINE.md`: `bench_incremental_scan` `unchanged` scenario (193 files, ~1.0–1.14× speedup sample).

### 2026-03-21 — Phase 6–7 docs: consistency triage + root README

- `README.md` at repo root; `PHASE_ROLLOUT.md` Phase 6/7 updates.

### 2026-03-21 — Phase 5: Mission & Scan `ui_mode` + settings-driven panels

- `MissionPage` / `ScanPage`: `ui_state` + `sync_chrome()`; store-driven Mission layout; Scan layout after store attach.
- `AppSettings.scan_show_phase_metrics` default **True** (matches prior Scan UI); Settings Behavior: Mission dashboard + Scan panel toggles.
- `_apply_preferences` refreshes mission/scan chrome.

### 2026-03-21 — Phase 5 follow-up: simple-mode UI gates

- `store.state.ui_mode` drives TopBar actions (no Export on History/Diagnostics, no Copy Diag on Scan in simple), Diagnostics notebook tabs + `apply_ui_mode`, insight drawer Compat section; Review `set_ui_mode` for Compare.
- `_apply_preferences()` syncs shell + `ui_mode` + Review + contextual actions (Settings Advanced checkbox stays consistent).
- `AppShell.active_page`; docs: `MODE_TOGGLE.md`, `PHASE_ROLLOUT.md`.

### 2026-03-21 — Phase 4 follow-up: virtual navigator + benchmark snapshot

- `virtual_navigator.py` (scroll math + env gate); Review page virtual vs legacy scroll binding; `DataTable(sortable=False, vsb=…)` for navigator; tests `test_virtual_navigator.py`.
- `docs/BENCHMARK_BASELINE.md` snapshot log; sample `bench_discovery` run; `PHASE_ROLLOUT.md` Phase 4 updated.

### 2026-03-21 — Theme JSON bundle + ToastManager wiring (Phase 2/3 follow-up)

- Themes page: export/import `cerebro_theme_config_v1` (theme key, `ThemeConfig`, UI accessibility flags); `ThemeConfig.from_dict` hardened for JSON lists.
- `CerebroApp`: toasts on scan complete (deduped per `scan_id`), theme apply (readable name), Themes export; import uses messagebox + theme toast only (no duplicate “imported” toast).
- Docs: `THEME_SYSTEM.md`, `PHASE_ROLLOUT.md`, this file.

### 2026-03-21 — History & Diagnostics export (Phase 3 follow-up)

- Shell **Export** on History and Diagnostics calls real exporters: filtered sessions → `cerebro_history_v1` JSON; diagnostics view → `cerebro_diagnostics_v1` JSON (overview, phases, artifacts, compat, events_log, integrity).
- `docs/button_functionality_audit.md` and this file updated.

### 2026-03-21 — Phase 1 completion

- Ruff check/format clean; scripts E402 allowed in `pyproject.toml`; import/`_log` order fixed in `pipeline.py`, `hub.py`.
- Pre-commit + `pre-commit` dev dependency; CONTRIBUTING updated.
- Duplicate test removed in `test_review_page.py`; diagnostics one-line `if`s split; unused `PHASE_ALIASES` export removed.
- Dead-code cleanup: `review_workspace` preview helper arity; `status_strip._item` signature.
- Refreshed tooling snapshots; `pip_audit_report.json` updated where applicable.
- Docs: `AUDIT_REPORT_PHASE1.md` marked complete; `button_functionality_audit.md`, `runtime_warnings.md`, `PHASE_ROLLOUT.md` updated.

### 2026-03-21 — Multi-phase rollout baseline

- Themes page, `contrast.py`, `theme_config.py`, `ShortcutRegistry`, `ToastManager` stub, `safe_ui_call`, `ui_mode` on store, initial audit docs. See `PHASE_ROLLOUT.md`.

---

## How to update this file when continuing

1. Adjust the **Current snapshot** table if any row changes materially.
2. Add a dated **Changelog** entry (short bullets).
3. If a whole phase closes, update `PHASE_ROLLOUT.md` and `AUDIT_REPORT_PHASE*.md` as appropriate.
