# CEREBRO v3.0 — CTK roadmap

Strategic direction: **CTK is the only desktop shell** on the shared orchestrator. This doc is the north star; update it when phases complete or priorities shift.

---

## End goal (definition of done for v3.0)

1. **CTK is the CEREBRO experience** — `python -m dedup` → `CerebroCTKApp`. Docs and packaging assume CustomTkinter (`setup.py` `install_requires`).
2. **~~Classic ttk shell~~** — **Removed** from the repository (no `--ui-backend ttk`).
3. **One shared core** — Engine (`dedup/engine/`), orchestration (`ScanCoordinator`, worker), persistence, and CLI scan path stay **single implementations**. v3 does **not** fork scan or delete logic inside the UI.
4. **Safety and clarity** — Review/plan/execute flows use the same controllers and services as before; polish and parity are **CTK-only** going forward.

---

## Where we are today

| Layer | CTK (only shell) |
|--------|-------------------|
| **Chrome** | CustomTkinter — `dedup/ui/ctk_app.py` + `ctk_pages/` |
| **Orchestration** | `ScanCoordinator` + `ScanController` / `ReviewController` + `UIStateStore` + `ProjectionHub` |
| **Visual polish** | CTK pages; Simple/Advanced `ui_mode` via store + settings |

**Implication:** Finish **one** front-end on the shared coordinator; optional refactors to reduce duplication inside `ctk_pages/` as needed.

---

## Guiding principles (hold these while executing)

1. **Shared brain, two faces** — New scan/delete/history behavior belongs in engine or orchestration, not duplicated in `ctk_pages/`.
2. **One owner per feature** — Secondary entry points (Welcome, Mission, Scan) call the same shell handler; note ownership changes in `docs/ENGINEERING_STATUS.md` when behavior splits.
3. **Main thread owns Tk** — Worker callbacks marshal to the UI thread (same rule as classic).
4. **Parity is scoped** — v3 GA means **agreed P0/P1 parity**, not necessarily pixel-perfect clone of every classic-only bell.

---

## Phases and concrete steps

### Phase A — Baseline and demarcation *(done)*

| Step | Outcome | Status |
|------|---------|--------|
| A.1 | This roadmap linked from `docs/README.md` | Done |
| A.2 | **Version story:** single package version (`dedup.__version__`), CLI `--version`, shell window titles, `setup.py` | Done (`3.0.0`) |
| A.3 | **Parity checklist** appended below (or in tracker): P0 / P1 / P2 with checkboxes | Done |
| A.4 | Install path stable: `pip install -r requirements-ctk.txt` + `python -m dedup` (see `docs/README.md`) | Done |

### Phase B — Parity pass (CTK catches classic on essentials)

**Suggested priority**

- **P0 — Must ship for v3.0**  
  Start/stop/cancel scan, resume, honest progress, post-scan routing, open review from last/history, review + deletion path end-to-end with coordinator + confirmations, no unsafe threading.

- **P1 — Strong v3**  
  History and Diagnostics at “trustworthy daily driver” level (including export if classic users rely on it), Settings aligned with real config paths and persistence where it matters.

- **P2 — Delight**  
  Themes depth (accent, presets), keyboard shortcuts where CTK allows, Mission/Scan density polish to match the visual quality you already like.

**Exit criteria for Phase B:** P0 complete and signed off; P1 items explicitly decided (done or deferred with reason). **Status: met for v3.0.0** (see parity checklist below).

### Phase C — Release candidate and launch

| Step | Outcome |
|------|---------|
| C.1 | Default launch is CTK only (`python -m dedup`) |
| C.2 | Short **manual QA matrix** — `docs/CTK_V3_MANUAL_QA.md` |
| C.3 | Tag **`v3.0.0`** when P0+P1 bar is met and QA matrix is signed off |

### Phase D — Post-3.0 consolidation

- Optional refactor: drive UI actions through `ScanController` / `ReviewController` / application services where it **removes** duplicate logic in `ctk_pages/` (do when cost/benefit is clear).
- MVVM direction: `dedup/core/`, `dedup/models/`, `dedup/services/`, `dedup/ui/viewmodels/` — evolve without forking orchestration or engine behavior.

---

## Parity checklist (edit as you learn)

Use this as the contract between “nice visuals” and “shippable v3.” Check items when CTK behavior matches the agreed product bar for that capability.

### P0

Walked against `dedup/ui/ctk_app.py` + `ctk_pages/` (2026-03-24). Code references for “done” are indicative, not exhaustive.

- [x] **Scan:** folder pick, presets (photos/videos/files), start, **cancel**, progress, completion state — `ScanPageCTK`, `_handle_start_scan_payload`, `_on_scan_cancel`, `_on_scan_progress` / `_apply_scan_complete`, `_start_scan_mode` / Welcome presets.
- [x] **Resume** interrupted scan (happy path + clear failure when none) — `_resume_scan_latest` (“No resumable scans found”, exception path).
- [x] **Post-scan routing** (Mission / Scan / Review) honored — `_route_after_scan` after completion; dropdown + `apply_decision_defaults` on Scan.
- [x] **Review (core):** load last result, keep selection, execute via coordinator, confirm dialog, outcome in result panel — `ReviewPageCTK`, `_open_last_review`, `_execute_review_lite_deletion`.
- [x] **Review (history):** open saved scan from History — `messagebox.showwarning` when `load_scan` returns `None` (`_open_history_scan_in_review`).
- [x] **Thread safety:** no direct Tk updates from worker callbacks for progress / complete / error — `root.after(0, …)` in `_on_scan_progress`, `_on_scan_complete`, `_on_scan_error`.

### P1

- [x] **History:** list, open in review, resumable clarity — filters, summary, detail **Resumable** field, export JSON, **delete** wired to `HistoryApplicationService.delete_scan`, up to 50 sessions.
- [x] **Diagnostics:** useful for support — runtime + session tabs; **Phases** from `phase_checkpoints`; **Artifacts** from checkpoint dir; **Compatibility** from stored verification/benchmark JSON; export JSON; copy DB path / active scan id.
- [x] **Settings:** DB path + **engine `config.json`** + **`ui_settings.json`** with **Copy**; links to Themes / Diagnostics; persistence via `SettingsApplicationService` + `UIState`.

### P2

- [x] **Themes:** appearance + accent + gradient + contrast + import/export; subtitle documents Ctrl+7.
- [x] **Shortcuts / accessibility:** global shortcuts in `ctk_app` (`CTKShortcutRegistry`); `?` help; F5 refresh — within what CTK/Tk allows on the desktop.

---

## Success metrics (lightweight)

- A new user can **scan → review → act** entirely in CTK.
- You are willing to **screenshot** CTK as the product homepage.

---

## Related documents

| Doc | Role |
|-----|------|
| `docs/CTK_V3_MANUAL_QA.md` | Manual QA matrix before tagging **v3.0.0** |
| `docs/ENGINEERING_STATUS.md` | What is implemented now; changelog when phases land |
| `docs/README.md` | Install, architecture overview |
