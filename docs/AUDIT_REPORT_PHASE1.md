# Phase 1 — Repository audit & analysis

**Date:** 2026-03-21  
**Scope:** Static analysis, dependencies, dead-code hints, architecture notes, button inventory (partial).

## Summary

| Area | Tool / method | Result | Severity (overall) |
|------|----------------|--------|---------------------|
| Style / imports | Ruff (`python -m ruff check dedup`) | See `docs/ruff_issues.txt` (hundreds of findings; mostly W293 whitespace, I001 import sort, some F401 unused) | Low–medium |
| Types | Mypy (`dedup/engine`, `orchestration`, `infrastructure`) | See `docs/mypy_issues.txt` (multiple errors; typing not clean on these packages yet) | Medium |
| Dead code hints | Vulture (`--min-confidence 80`) | 2 hits (see `docs/vulture_report.txt`) | Low |
| CVE / deps | `pip-audit` | Run locally: `python -m pip_audit -r docs/requirements.txt` (network); optional JSON → `docs/pip_audit_report.json` | TBD |
| Outdated packages | `pip list --outdated` | `docs/pip_outdated.txt` | Info |
| Pylint | Not run in CI | **Skipped:** overlap with Ruff; full pylint is noisy on Tk code. **Plan:** enable `pylint` on `dedup/engine` only after Ruff W293/I001 backlog is reduced. | — |
| Import cycles | Grep / policy | No `dedup.ui` imports under `dedup/engine` or `dedup/orchestration`. | OK |
| Runtime GUI soak | Manual | **Skipped in automation.** **Plan:** capture stderr to `docs/runtime_warnings.md` after Mission→Scan→Review→Delete on ~10k-file fixture. | — |
| pydeps graph | **Skipped** (needs Graphviz for SVG). **Plan:** `python -m pydeps dedup --max-bacon=2` once graphviz installed; store `docs/deps.svg`. | — |

## Owners / next actions

1. **Ruff:** Auto-fix safe items: `python -m ruff check dedup --fix` (review diff), then tackle remaining W293 manually or pre-commit hook.
2. **Mypy:** Fix `media_types.get_extensions_for_category` `None` handling; then `inventory_repo`, `grouping`, `pipeline` hot spots listed in `mypy_issues.txt`.
3. **Vulture:** Remove or prefix unused params in `review_workspace.py` and `status_strip.py` (or suppress with comment if API-stable).
4. **Buttons:** Complete `docs/button_functionality_audit.md` (stub rows + known `lambda: None` exports).

## Files produced (Phase 1)

- `docs/ruff_issues.txt`
- `docs/mypy_issues.txt`
- `docs/vulture_report.txt`
- `docs/pip_outdated.txt`
- `pyproject.toml` (tooling)
- `requirements-dev.txt`
