# CTK v3.0 — manual QA matrix

Run these checks on **Windows** first (primary platform); spot-check **macOS** / **Linux** if you ship there.

**Build:** `pip install -r requirements-ctk.txt` then `python -m dedup` from the repo root.

| Area | Steps | Pass |
|------|--------|------|
| **Launch** | App opens; title shows **CEREBRO** and version **3.0.0**; no traceback. | ☐ |
| **CLI** | `python -m dedup --version` prints `3.0.0`. | ☐ |
| **Scan** | Pick folder → start scan → progress updates → cancel or complete. | ☐ |
| **Resume** | Mission/Welcome **Resume** when a resumable checkpoint exists; message when none. | ☐ |
| **Review** | Open last review; change keep; preview; execute deletion (or cancel). | ☐ |
| **History** | List loads; filter/search; **Load** to Review; **Resume** when resumable; **Delete** removes row; **Export JSON**. | ☐ |
| **Diagnostics** | Runtime fields; session combo; **Phases** / **Events** / **Artifacts** / **Compatibility** tabs; **Export JSON**; **Copy** on DB path and active ID. | ☐ |
| **Settings** | Toggles save; **Data** shows DB + `config.json` + `ui_settings.json` paths; **Copy** works; **Open Diagnostics** / **Open Themes**. | ☐ |
| **Themes** | Preset switch; gradient/contrast; export/import bundle. | ☐ |
| **Shortcuts** | Ctrl+1–7, Ctrl+,, F5, `?` help dialog lists shortcuts. | ☐ |
| **Degraded** | If theme apply fails, degraded banner appears (optional negative test). | ☐ |

**Sign-off:** Date ______  Tester ______

When this matrix is green, tag **`v3.0.0`** on the commit that bumps `dedup.__version__` to `3.0.0`.
