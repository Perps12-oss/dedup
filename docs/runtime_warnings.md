# Runtime warnings capture

## Automated check (2026-03-21)

- `python -m pytest dedup/tests/` — **exit 0** (full suite).
- **Known pytest noise:** thumbnail worker threads may raise `RuntimeError: main thread is not in main loop` when Tk is destroyed without a running mainloop (`test_review_page` compare / gallery paths). This is a **test harness** limitation, not a production defect.

## GUI soak (manual)

Run when validating a release:

1. `python -m dedup`
2. Mission → Scan (small folder) → Review → Preview Effects → cancel execute.
3. Toggle Themes, Settings, Advanced.
4. Copy any **stderr** / Tk warnings below.

### Log

_(No interactive soak captured in this pass.)_
