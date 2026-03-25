# CEREBRO v3.0 — CTK roadmap

Strategic direction: **keep the path you are on** (CTK as a dedicated shell on the shared orchestrator) while making the **end state explicit** and measurable. This doc is the north star; update it when phases complete or priorities shift.

---

## End goal (definition of done for v3.0)

1. **CTK is the primary CEREBRO experience** — New users and default documentation assume the CustomTkinter shell. Versioning and messaging say **3.0** (product), not “experimental sidebar.”
2. **Classic ttk shell is legacy, not dead** — Remains available as `--ui-backend ttk` for a defined period: **maintenance** (fixes, regressions), not new product features unless critical.
3. **One shared core** — Engine (`dedup/engine/`), orchestration (`ScanCoordinator`, worker), persistence, and CLI scan path stay **single implementations**. v3 does **not** fork scan or delete logic inside the UI.
4. **Safety and clarity match the classic bar** — Any flow that moves bytes or deletes files (review, plan, execute, confirmations) is as trustworthy on CTK as on classic, with clear copy and no cross-thread UI bugs.

---

## Where we are today

| Layer | CTK (`--ui-backend ctk`) | Classic (default `ttk`) |
|--------|---------------------------|-------------------------|
| **Chrome** | CustomTkinter, `dedup/ui/ctk_app.py` + `ctk_pages/` | `DedupApp`, ttk + theme system, NavRail, status strip |
| **Orchestration** | **`ScanCoordinator` directly** (thin shell) | **`ScanCoordinator` + `ScanController` + `UIStateStore`** |
| **Visual polish** | Strong direction (you like the new visuals); pages still maturing | Years of density, shortcuts, theme tooling, Simple/Advanced gates |

**Implication:** You are **not** building a second backend. You are **finishing a second front-end** on the same coordinator. Optional later step: fold CTK into `ScanController` contracts where duplication becomes painful — **not required** to ship v3 if coordinator usage stays disciplined.

---

## Guiding principles (hold these while executing)

1. **Shared brain, two faces** — New scan/delete/history behavior belongs in engine or orchestration, not duplicated in `ctk_pages/`.
2. **One owner per feature** — Secondary entry points (Welcome, Mission, Scan) call the same shell handler; keep `docs/CTK_MIGRATION_TRACKER.md` accurate.
3. **Main thread owns Tk** — Worker callbacks marshal to the UI thread (same rule as classic).
4. **Parity is scoped** — v3 GA means **agreed P0/P1 parity**, not necessarily pixel-perfect clone of every classic-only bell.

---

## Phases and concrete steps

### Phase A — Baseline and demarcation *(in progress)*

| Step | Outcome | Status |
|------|---------|--------|
| A.1 | This roadmap linked from `docs/README.md` and `CTK_MIGRATION_TRACKER.md` | Done |
| A.2 | **Version story:** single package version (`dedup.__version__`), CLI `--version`, shell window titles, `setup.py` | Done (`3.0.0-beta.1`) |
| A.3 | **Parity checklist** appended below (or in tracker): P0 / P1 / P2 with checkboxes | Done |
| A.4 | Install path stable: `requirements-ctk.txt` + `python -m dedup --ui-backend ctk` (see `docs/README.md`) | Done |

### Phase B — Parity pass (CTK catches classic on essentials)

**Suggested priority**

- **P0 — Must ship for v3.0**  
  Start/stop/cancel scan, resume, honest progress, post-scan routing, open review from last/history, review + deletion path end-to-end with coordinator + confirmations, no unsafe threading.

- **P1 — Strong v3**  
  History and Diagnostics at “trustworthy daily driver” level (including export if classic users rely on it), Settings aligned with real config paths and persistence where it matters.

- **P2 — Delight**  
  Themes depth (accent, presets), keyboard shortcuts where CTK allows, Mission/Scan density polish to match the visual quality you already like.

**Exit criteria for Phase B:** P0 complete and signed off; P1 items explicitly decided (done or deferred with reason).

### Phase C — Release candidate and launch

| Step | Outcome |
|------|---------|
| C.1 | Recommended launch command or env documented for **CTK-first** trials (e.g. `DEDUP_UI_BACKEND=ctk`) |
| C.2 | Short **manual QA matrix** (Windows first; spot-check macOS/Linux if supported) |
| C.3 | Tag **3.0.0-rc** → **3.0.0** when P0+P1 bar is met; README positions classic as legacy |

### Phase D — Classic demotion (after 3.0)

- Default `python -m dedup` may flip to **ctk** when you are ready (breaking change — call out in changelog).
- Classic: bugfixes and security only; no parallel feature races unless unavoidable.
- Optional refactor: drive CTK actions through `ScanController` / store where it **removes** duplicate logic (do when cost/benefit is clear).

---

## Parity checklist (edit as you learn)

Use this as the contract between “nice visuals” and “shippable v3.” Check items when CTK matches classic **behavior** for that capability.

### P0

Walked against `dedup/ui/ctk_app.py` + `ctk_pages/` (2026-03-24). Code references for “done” are indicative, not exhaustive.

- [x] **Scan:** folder pick, presets (photos/videos/files), start, **cancel**, progress, completion state — `ScanPageCTK`, `_handle_start_scan_payload`, `_on_scan_cancel`, `_on_scan_progress` / `_apply_scan_complete`, `_start_scan_mode` / Welcome presets.
- [x] **Resume** interrupted scan (happy path + clear failure when none) — `_resume_scan_latest` (“No resumable scans found”, exception path).
- [x] **Post-scan routing** (Mission / Scan / Review) honored — `_route_after_scan` after completion; dropdown + `apply_decision_defaults` on Scan.
- [x] **Review (core):** load last result, keep selection, execute via coordinator, confirm dialog, outcome in result panel — `ReviewPageCTK`, `_open_last_review`, `_execute_review_lite_deletion`.
- [x] **Review (history):** open saved scan from History — `messagebox.showwarning` when `load_scan` returns `None` (`_open_history_scan_in_review`).
- [x] **Thread safety:** no direct Tk updates from worker callbacks for progress / complete / error — `root.after(0, …)` in `_on_scan_progress`, `_on_scan_complete`, `_on_scan_error`.

### P0 backlog *(cleared 2026-03-24 — implementation landed)*

1. ~~**History → Review failed load**~~ — `messagebox.showwarning` when `load_scan` returns `None`.
2. ~~**Cancel → UI sync**~~ — `ScanCoordinator.start_scan(..., on_cancel=…)` wires worker `on_cancel`; CTK marshals `_apply_scan_cancelled_ui` → `set_scan_busy(False)`.
3. ~~**Version alignment**~~ — `dedup.__version__` = `3.0.0-beta.1`; `main.py --version`, `CerebroCTKApp` / `CerebroApp` titles, `setup.py`.

*Next: run P0 smoke (scan, cancel, history bad row, `--version`) and sign off for GA when ready.*

### P1

- [ ] History: list, open in review, resumable clarity
- [ ] Diagnostics: useful for support; export if required by your support story
- [ ] Settings: DB path truth, links to Themes/Diagnostics, persisted where classic persists

### P2

- [ ] Themes: appearance + accent at level you want for “3.0 brand”
- [ ] Shortcuts / accessibility pass (what CTK can support)

---

## Success metrics (lightweight)

- A new user can **scan → review → act** entirely in CTK without switching backend.
- You are willing to **screenshot** CTK as the product homepage.
- Classic remains available without blocking v3 narrative.

---

## Related documents

| Doc | Role |
|-----|------|
| `docs/CTK_MIGRATION_TRACKER.md` | Per-feature ownership and migration status |
| `docs/ENGINEERING_STATUS.md` | Classic shell detailed implementation status |
| `docs/README.md` | Install, `--ui-backend`, architecture overview |
