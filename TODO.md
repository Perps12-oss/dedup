# Dedup — engineering backlog (living)

## Landed in recent work

- **Batch full-hash writes** (`FullHashRepository.upsert_batch`, `grouping.py`).
- **Packaging / Python 3.11+** (`requirements-ctk.txt`, `setup.py`, `requests` pin for pip-audit).
- **Dead MVVM and legacy ttk surfaces removed** (viewmodels, legacy pages, unused components; `ThemeManager` inlines Sun Valley try/import).
- **Store retention + session boundaries** (`docs/STORE_RETENTION_AND_PROJECTION.md`, `UIStateStore` reset helpers, coordinator clears `_last_result` on fresh scan, CTK app resets store slices).
- **CTK Review tests** (`dedup/tests/test_ctk_review_page.py`, `test_store_retention.py`).

## Still open (see docs)

| Topic | Where |
|-------|--------|
| Optional post-deletion `ScanResult` summarization | `docs/STORE_RETENTION_AND_PROJECTION.md` |
| Broader CTK page / controller coverage | `docs/BACKLOG.md` |
| Clearly optional UI enhancements | `docs/BACKLOG.md` |

## Suggested merge order into `main`

1. `chore/environment-and-deps`
2. `chore/dead-layer-purge`
3. `design/store-retention-and-projection-limits`
