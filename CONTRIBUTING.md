# Contributing

## Layout

- Python package: `dedup/` (run with `python -m dedup` from the repository root).
- Documentation: `docs/` (start with `docs/README.md`, `docs/REPO_AUTHORITY.md`).
- Phase tracking: `docs/PHASE_ROLLOUT.md`.

## Development setup

```bash
pip install -r requirements-dev.txt
pip install -r docs/requirements.txt   # optional runtime extras
python -m pytest dedup/tests
python -m ruff check dedup
python -m mypy dedup/engine dedup/orchestration dedup/infrastructure
```

## Conventions

- **UI:** Prefer store + controllers over calling the engine from pages (`docs/CONTROLLER_CONTRACTS.md`).
- **Theming:** Use semantic tokens; see `docs/THEME_SYSTEM.md`.
- **Buttons:** Follow `docs/BUTTON_HIERARCHY.md`.

## Pull requests

- Keep changes scoped; note any deferred work in `docs/PHASE_ROLLOUT.md` or `docs/BACKLOG.md`.
