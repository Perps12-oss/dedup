# Dead code inventory (Phase 1)

## Automated (Vulture, confidence ≥ 80)

See `docs/vulture_report.txt` — **latest run: no issues** (unused preview arg and `fg_key` removed in Phase 1 completion pass).

## Manual / policy

- **Nav pages:** All six primary shell pages are reachable from `NavRail` (`mission`, `scan`, `review`, `history`, `diagnostics`, `settings`) plus **`themes`** (Phase 2).
- **Theme tokens:** Full token usage audit **deferred** — grep each `theme_tokens.py` key against `dedup/ui` **planned** for Phase 2 sub-pass after `ThemePage` stabilizes.
- **Commented blocks / TODO:** Grep `TODO|FIXME` **skipped** in this pass; track in `docs/BACKLOG.md`.
- **Orphan modules:** No standalone scripts under `dedup/` without `__main__` were flagged; `dedup/scripts/` are tooling entrypoints.

## Removal policy

Do not delete public widget APIs without checking `dedup/tests` and grep across `ui/pages`.
