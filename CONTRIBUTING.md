# Contributing

## Layout

- Python package: `dedup/` (run with `python -m dedup` from the repository root).
- Documentation: `docs/` (start with `docs/README.md`, `docs/REPO_AUTHORITY.md`).
- **Living implementation status:** `docs/ENGINEERING_STATUS.md` — update this when you merge meaningful changes so the narrative stays current.
- Phase history / deferrals: `docs/PHASE_ROLLOUT.md`.

## Development setup

```bash
pip install -r requirements-dev.txt
pip install -r docs/requirements.txt   # optional runtime extras
pre-commit install   # optional: git hooks from .pre-commit-config.yaml
python -m pytest dedup/tests
python -m ruff check dedup
python -m ruff format dedup
python -m mypy dedup/engine dedup/orchestration dedup/infrastructure
```

## Conventions

- **UI:** Prefer store + controllers over calling the engine from pages (`docs/CONTROLLER_CONTRACTS.md`).
- **Theming:** Use semantic tokens; see `docs/THEME_SYSTEM.md`.
- **Buttons:** Follow `docs/BUTTON_HIERARCHY.md`.

## Pull requests

- Keep changes scoped; note any deferred work in `docs/PHASE_ROLLOUT.md` or `docs/BACKLOG.md`.
