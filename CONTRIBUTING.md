# Contributing

## Layout

- Python package: `dedup/` (run with `python -m dedup` from the repository root).
- Documentation: `docs/` (start with `docs/README.md`, `docs/REPO_AUTHORITY.md`).
- **Living implementation status:** `docs/ENGINEERING_STATUS.md` — update this when you merge meaningful changes so the narrative stays current.
- Phase history / deferrals: `docs/PHASE_ROLLOUT.md`.

## Development setup

**Python:** 3.11+ (aligned with `setup.py`, Ruff, and mypy in `pyproject.toml`).

```bash
pip install -r requirements-dev.txt   # includes runtime deps from requirements-ctk.txt
pre-commit install   # optional: git hooks from .pre-commit-config.yaml
python -m pytest dedup/tests
python -m ruff check dedup
python -m ruff format dedup
python -m mypy dedup/engine dedup/orchestration dedup/infrastructure
python -m vulture dedup --exclude=__pycache__,tests --min-confidence=70
```

## Conventions

- **UI:** Prefer store + controllers over calling the engine from pages (`docs/CONTROLLER_CONTRACTS.md`).
- **Theming:** Use semantic tokens; see `docs/THEME_SYSTEM.md`.
- **Buttons:** Follow `docs/BUTTON_HIERARCHY.md`.
- **Threading:** Never mutate Tk/UI objects from worker threads; route updates through store/controller UI-thread marshalling.

## Local quality gates

- Install hooks once: `pre-commit install`
- Run hooks manually: `pre-commit run --all-files`
- Hooks currently run Ruff + compile checks before commit.

## Pull requests

- Keep changes scoped; note any deferred work in `docs/PHASE_ROLLOUT.md` or `docs/BACKLOG.md`.
