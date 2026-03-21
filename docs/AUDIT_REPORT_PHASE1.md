# Phase 1 — Repository audit & analysis (complete)

**Last updated:** 2026-03-21 (completion pass)

## Summary

| Area | Tool / method | Result | Severity |
|------|----------------|--------|----------|
| Style / imports | Ruff `check` + `format` on `dedup/` | **Clean** — `docs/ruff_issues.txt` records “No violations” | — |
| Pre-commit | `.pre-commit-config.yaml` | Ruff fix + ruff-format hooks added | — |
| Types | Mypy (`engine`, `orchestration`, `infrastructure`) | See `docs/mypy_issues.txt` (errors remain; backlog) | Medium |
| Dead code | Vulture `--min-confidence 80` | **Clean** — `docs/vulture_report.txt` | — |
| CVE | `pip-audit -r docs/requirements.txt -f json` | **No known vulns** on scanned optional deps → `docs/pip_audit_report.json` | OK |
| Outdated | `pip list --outdated` | `docs/pip_outdated.txt` (machine snapshot) | Info |
| Buttons | Static audit | `docs/button_functionality_audit.md` (per-page + Export stubs) | Low |
| Runtime | Pytest + notes | `docs/runtime_warnings.md` | Info |
| Import cycles | Grep | No `dedup.ui` under `engine` / `orchestration` | OK |

## Still deferred (not blocking Phase 1 “done”)

| Item | Reason | Next step |
|------|--------|-----------|
| Pylint | Overlaps Ruff; noisy on Tk | Optional `pylint dedup/engine --errors-only` |
| pydeps SVG | Needs Graphviz | `pydeps dedup -o docs/deps.svg` when installed |
| Full GUI soak | Manual | Fill `runtime_warnings.md` log on release candidate |
| Mypy green | Large backlog | Triage `mypy_issues.txt` by module |

## Code fixes shipped in this pass

- **Ruff:** `--fix` + `ruff format` across `dedup/`; import order in `pipeline.py`, `hub.py`; **E402** allowed for `dedup/scripts/**` in `pyproject.toml`.
- **Tests:** Removed duplicate `test_clear_selection_button_shown_when_keep_set` definition.
- **Diagnostics:** Split one-line `if` assignments for E701.
- **Projections package:** Dropped unused `PHASE_ALIASES` re-export.
- **Vulture:** Removed unused `is_left` parameter in `ReviewCompareView._render_pair`; dropped unused `fg_key` in `status_strip._item`.

## Artifacts

- `docs/ruff_issues.txt`, `docs/mypy_issues.txt`, `docs/vulture_report.txt`, `docs/pip_outdated.txt`, `docs/pip_audit_report.json`
- `pyproject.toml`, `requirements-dev.txt`, `.pre-commit-config.yaml`
- `docs/button_functionality_audit.md`, `docs/runtime_warnings.md`, `docs/ARCHITECTURE_REVIEW.md`, …
