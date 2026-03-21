# Dependency audit

## Runtime (`docs/requirements.txt`)

| Package | Role | Notes |
|---------|------|--------|
| xxhash | Faster hashing | CPython-only marker in requirements |
| send2trash | Recycle bin / trash | Recommended |
| tkinterdnd2 | Drag-and-drop | Optional; `app.py` falls back if missing |
| Pillow | Thumbnails | Optional; graceful degradation |

Core app runs on **stdlib + Tkinter** only.

## Dev (`requirements-dev.txt`)

Adds: `ruff`, `mypy`, `pytest`, `vulture`, `pip-audit`, `pydeps`, `pylint`, **`pre-commit`** (for `.pre-commit-config.yaml` at repo root).

## Audits to run locally

```bash
python -m pip install -r requirements-dev.txt
pre-commit install   # optional: run ruff + ruff-format on commit
python -m pip_audit -r docs/requirements.txt
python -m pip_audit -r docs/requirements.txt -f json   # refresh artifact
python -m pip list --outdated
```

**Checked in artifacts (refresh before releases):**

- `docs/pip_audit_report.json` — last structured pip-audit for optional runtime deps
- `docs/pip_outdated.txt` — machine snapshot; regenerate with `pip list --outdated`

## Pruning opportunities

- **blake3** remains commented in `docs/requirements.txt` — enable only if benchmarks justify it.
- Keep Pillow optional: large installs on minimal environments.
