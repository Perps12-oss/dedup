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

Adds: `ruff`, `mypy`, `pytest`, `vulture`, `pip-audit`, `pydeps`, `pylint`.

## Audits to run locally

```bash
python -m pip install -r requirements-dev.txt
python -m pip_audit -r docs/requirements.txt
python -m pip list --outdated
```

Record CVE output under `docs/pip_audit_report.json` (or paste summary here).  
`docs/pip_outdated.txt` is a snapshot from one machine; refresh before releases.

## Pruning opportunities

- **blake3** remains commented in `docs/requirements.txt` — enable only if benchmarks justify it.
- Keep Pillow optional: large installs on minimal environments.
