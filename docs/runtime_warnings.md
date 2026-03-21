# Runtime warnings capture (template)

**Purpose:** GUI soak test notes (Mission → Scan → Review → delete dry-run) on a non-trivial dataset.

## Environment

- OS:
- Python version:
- Optional deps installed: xxhash / send2trash / tkinterdnd2 / Pillow (check all that apply)

## Procedure

1. `python -m dedup`
2. Run scan on a directory with ~10k files (or project test fixture).
3. Open Review, switch Table / Gallery / Compare.
4. Copy any **stderr** lines and Tk warnings below.

## Log

_(None captured in automated Phase 1 — fill during manual QA.)_

## Pytest note

Thumbnail worker threads may log `RuntimeError: main thread is not in main loop` when tests tear down Tk without a running mainloop; tracked as pytest warnings, not production defects.
