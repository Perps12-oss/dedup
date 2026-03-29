# Dependency audit

## Runtime (`requirements-ctk.txt`)

| Package | Role | Notes |
|---------|------|--------|
| customtkinter | GUI shell | Required |
| xxhash | Faster hashing | Required (install); MD5 fallback only if import fails |
| send2trash | Recycle bin / trash | Required (install) |
| tkinterdnd2 | Drag-and-drop | Optional UX; shell falls back if missing |
| Pillow | Thumbnails | Optional; graceful degradation |

Install: `pip install -r requirements-ctk.txt` (or `pip install .` for core deps from `setup.py`).

## Dev (`requirements-dev.txt`)

Includes everything from `requirements-ctk.txt`, plus: `ruff`, `mypy`, `pytest`, `vulture`, `pip-audit`, `pydeps`, **`pre-commit`** (for `.pre-commit-config.yaml` at repo root), and a pinned **`requests>=2.33.0`** for transitive security (pip-audit).

## Audits to run locally

```bash
python -m pip install -r requirements-dev.txt
pre-commit install   # optional: run ruff + ruff-format on commit
python -m pip_audit -r requirements-ctk.txt
python -m pip_audit -r requirements-ctk.txt -f json   # optional local artifact (gitignored)
python -m pip list --outdated
```

**Optional checked-in snapshots:** prefer not to commit pip-audit JSON; add `docs/pip_audit_report.json` to `.gitignore` if you regenerate locally.

## Pruning opportunities

- **blake3** can be added to `extras_require` only if benchmarks justify it.
- Pillow remains optional in `extras_require["recommended"]` for minimal environments.
