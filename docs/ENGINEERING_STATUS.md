# Engineering status (living document)

**Purpose:** Single place to record **what is implemented now** as the project evolves. Update this file whenever you ship a phase, close an audit item, or change tooling.

**Detailed phase history:** `docs/PHASE_ROLLOUT.md`  
**Phase 1 report:** `docs/AUDIT_REPORT_PHASE1.md`

---

## Current snapshot

| Area | Status | Notes |
|------|--------|--------|
| **Ruff** | Clean | `python -m ruff check dedup`; `ruff format` applied repo-wide |
| **Pre-commit** | Config present | `.pre-commit-config.yaml` → ruff + ruff-format; run `pre-commit install` |
| **Tests** | Passing | `python -m pytest dedup/tests/` |
| **Vulture** (≥80%) | Clean | `docs/vulture_report.txt` |
| **pip-audit** (optional deps) | No CVEs in last scan | `docs/pip_audit_report.json` |
| **Mypy** | Not clean | `docs/mypy_issues.txt` — backlog |
| **UI shell** | 7 nav destinations | Mission, Scan, Review, History, Diagnostics, **Themes**, Settings |
| **Store `ui_mode`** | Wired | `simple` / `advanced` synced with `AppSettings.advanced_mode` |
| **Shortcuts** | Registry | `dedup/ui/shell/shortcut_registry.py`; Ctrl+7 → Themes |
| **Button audit** | Living | `docs/button_functionality_audit.md` |
| **History / Diagnostics Export** | Implemented | Top bar **Export** → JSON save-as (`export_sessions_json`, `export_report_json`) |

---

## Changelog (append newest first)

### 2026-03-21 — History & Diagnostics export (Phase 3 follow-up)

- Shell **Export** on History and Diagnostics calls real exporters: filtered sessions → `cerebro_history_v1` JSON; diagnostics view → `cerebro_diagnostics_v1` JSON (overview, phases, artifacts, compat, events_log, integrity).
- `docs/button_functionality_audit.md` and this file updated.

### 2026-03-21 — Phase 1 completion

- Ruff check/format clean; scripts E402 allowed in `pyproject.toml`; import/`_log` order fixed in `pipeline.py`, `hub.py`.
- Pre-commit + `pre-commit` dev dependency; CONTRIBUTING updated.
- Duplicate test removed in `test_review_page.py`; diagnostics one-line `if`s split; unused `PHASE_ALIASES` export removed.
- Dead-code cleanup: `review_workspace` preview helper arity; `status_strip._item` signature.
- Refreshed: `ruff_issues.txt`, `mypy_issues.txt`, `vulture_report.txt`, `pip_outdated.txt`, `pip_audit_report.json`.
- Docs: `AUDIT_REPORT_PHASE1.md` marked complete; `button_functionality_audit.md`, `runtime_warnings.md`, `dead_code_inventory.md`, `PHASE_ROLLOUT.md` updated.

### 2026-03-21 — Multi-phase rollout baseline

- Themes page, `contrast.py`, `theme_config.py`, `ShortcutRegistry`, `ToastManager` stub, `safe_ui_call`, `ui_mode` on store, initial audit docs. See `PHASE_ROLLOUT.md`.

---

## How to update this file when continuing

1. Adjust the **Current snapshot** table if any row changes materially.
2. Add a dated **Changelog** entry (short bullets).
3. If a whole phase closes, update `PHASE_ROLLOUT.md` and `AUDIT_REPORT_PHASE*.md` as appropriate.
