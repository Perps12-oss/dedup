# Legacy ttk / ttkbootstrap UI

The **ttkbootstrap**-based application (`DedupApp`, `dedup/ui/app.py`) is the **legacy** desktop shell.

- **Not** the default launcher; use `--ui-backend ttk` or `DEDUP_UI_BACKEND=ttk` when you need it.
- New product work should target the **CTK** shell unless fixing a regression that only affects legacy.
- Shared orchestration, `ProjectionHub`, `UIStateStore`, and **application services** (`dedup.application`) are the same for both shells.
