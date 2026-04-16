# Bottleneck Verification (Code + Runtime)

Use this to validate bottleneck claims with executable evidence rather than docs-only notes.

## 1) Verify claim commits are on `origin/main`

```powershell
python -m dedup.scripts.verify_bottlenecks
```

The script checks each BN SHA against `origin/main` ancestry and prints a JSON report.

## 2) Run bottleneck regression guards only

```powershell
python -m pytest -q -m bottleneck_guard
```

These tests validate:

- BN-005: history rows are reused, not rebuilt for unchanged filtered data.
- BN-006: mission recent sessions skip rebuild when session data is unchanged.
- BN-009: themes stop color picker updates one chip in-place (no full row rebuild).
- BN-010: scan label recolor skips redundant `configure()` when color already matches.
- BN-011: review execute-start has no forced `update_idletasks()` redraw.

## 3) Optional full test run

```powershell
python -m pytest -q
```

## Notes

- If commit ancestry fails, run `git fetch origin` and retry.
- If a guard test fails, treat the corresponding BN as regressed until fixed.
