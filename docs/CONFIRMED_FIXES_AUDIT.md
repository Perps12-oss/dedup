# Confirmed fixes audit — evidence and status

Every “confirmed and fixed” claim is backed below by file path, exact change, before/after, and branch/merge status.

**Branch:** `feature/ui-store-intents-migration`  
**Merge status:** **Branch only** — not merged into `main`.  
(`git log main..feature/ui-store-intents-migration` shows 12 commits ahead of main.)

**Later evolution:** The shell gained a **Themes** page (seven NavRail destinations). Current narrative: `docs/ENGINEERING_STATUS.md`.

---

## 1. Direct page/backend coupling — Review actions

| Field | Value |
|-------|--------|
| **File path** | `dedup/ui/app.py` |
| **Exact symbol / text** | Action map for page `"review"`: lambda targets and button labels. |
| **Before** | `("Preview Effects", "Ghost.TButton", lambda: self._review._on_dry_run())` and `("DELETE", "Danger.TButton", lambda: self._review._on_execute())` |
| **After** | `("Preview Effects", "Ghost.TButton", lambda: self._review_controller.handle_preview_deletion())` and `("DELETE", "Danger.TButton", lambda: self._review_controller.handle_execute_deletion())` |
| **Location** | Lines 276–277 (approximate). |
| **Branch/merged** | Branch only. |

---

## 2. Direct page/backend coupling — History refresh

| Field | Value |
|-------|--------|
| **File path** | `dedup/ui/app.py` |
| **Exact symbol / text** | Action map for page `"history"`: Refresh action callable. |
| **Before** | `("Refresh", "Ghost.TButton", lambda: self._history._refresh())` |
| **After** | `("Refresh", "Ghost.TButton", lambda: self._history.refresh())` |
| **Location** | Line 280. |
| **Branch/merged** | Branch only. |

**Supporting change (public API):**  
- **File path:** `dedup/ui/pages/history_page.py`  
- **Added:** `def refresh(self):` with docstring `"""Public API: refresh session list and table from coordinator."""` delegating to `self._refresh()`. Internal `_refresh()` unchanged.  
- **Also:** Call site that previously invoked `self._refresh()` in the “no request refresh” branch now calls `self.refresh()`. |

---

## 3. Direct page/backend coupling — Diagnostics refresh

| Field | Value |
|-------|--------|
| **File path** | `dedup/ui/app.py` |
| **Exact symbol / text** | Action map for page `"diagnostics"`: Refresh action callable. |
| **Before** | `("Refresh", "Ghost.TButton", lambda: self._diagnostics._refresh())` |
| **After** | `("Refresh", "Ghost.TButton", lambda: self._diagnostics.refresh())` |
| **Location** | Line 284. |
| **Branch/merged** | Branch only. |

**Supporting change (public API):**  
- **File path:** `dedup/ui/pages/diagnostics_page.py`  
- **Added:** `def refresh(self):` with docstring `"""Public API: refresh diagnostics data from coordinator."""` delegating to `self._refresh()`.  
- **Changed:** `on_show(self)` now calls `self.refresh()` instead of `self._refresh()`. |

---

## 4. ScanPage single authority when store attached

| Field | Value |
|-------|--------|
| **File path** | `dedup/ui/pages/scan_page.py` |
| **Exact symbol / text** | `attach_store()` body and docstring. |
| **Before** | `def attach_store(...):` then `self.detach_store()` and `self._store = store`. Docstring: “Subscribe to UIStateStore for scan display. Store is fed by hub adapter.” |
| **After** | First line of body: `self.detach_hub()`, then `self.detach_store()`, then `self._store = store`. Docstring extended: “… Single authority: when store is attached, hub is detached.” |
| **Location** | Lines 107–111 (method body), docstring at 108. |
| **Branch/merged** | Branch only. |

---

## 5. Stale comment — Review page Clear selection

| Field | Value |
|-------|--------|
| **File path** | `dedup/ui/pages/review_page.py` |
| **Exact symbol / text** | Module docstring, “Clear Selection” paragraph. |
| **Before** | “There is no dedicated ‘Clear Selection’ button in the Review UI. To clear a group’s keep choice, the user may (a) select a different file as KEEP in that group, or (b) load a new scan result (load_result resets vm.keep_selections). ReviewVM.clear_keep(group_id) exists but is not wired to any UI control. Workspace state and plan state are both driven by vm.keep_selections.” |
| **After** | “Clear Selection: The workspace toolbar shows ‘Clear selection’ when the current group has a keep choice; it calls clear_keep for the selected group. User can also change keep to another file in the group or load a new scan (load_result resets vm.keep_selections). Workspace and plan state are driven by vm.keep_selections.” |
| **Location** | Lines 11–15 (docstring). |
| **Branch/merged** | Branch only. |

---

## 6. Branding / product description — README

| Field | Value |
|-------|--------|
| **File path** | `README.md` (repo root) |
| **Exact symbol / text** | Title, Philosophy, Features, Architecture, and related wording. |
| **Before** | “DEDUP - Minimal Duplicate File Finder”; “The UI is only a thin interface”; “Minimal UI: Four screens only - Home, Scan, Results, History”; “Repository Audit Summary” and “What Was Simplified” (e.g. “Reduced from 7+ to 4 essential screens”). |
| **After** | “CEREBRO Dedup — Duplicate File Finder & Operations Shell”; “six-page CEREBRO operations shell”; “The UI is a structured operations shell, not a thin one-off”; “Six-page shell: Mission (home), Scan (live), Review (decision studio), History, Diagnostics, Settings”; “Store + controllers”; “See docs/CONTROLLER_CONTRACTS.md and docs/REPO_AUTHORITY.md”; packaging note that tests are excluded. Old “Repository Audit Summary” / “What Was Simplified” / “Risk Register” sections removed or replaced. |
| **Location** | Full file rewrite. |
| **Branch/merged** | Branch only. |

---

## 7. Branding / product description — main entrypoint

| Field | Value |
|-------|--------|
| **File path** | `dedup/main.py` |
| **Exact symbol / text** | Module docstring (top of file). |
| **Before** | “DEDUP - A minimal, high-performance duplicate file finder. A simplified duplicate file finder with a production-grade engine capable of handling 1,000,000+ files.” |
| **After** | “CEREBRO Dedup - Duplicate file finder and operations shell. Production-grade engine and six-page UI (Mission, Scan, Review, History, Diagnostics, Settings). Capable of handling 1,000,000+ files with store- and controller-driven architecture.” |
| **Location** | Lines 2–6. |
| **Branch/merged** | Branch only. |

---

## 8. DedupApp alias comment

| Field | Value |
|-------|--------|
| **File path** | `dedup/ui/app.py` |
| **Exact symbol / text** | Line immediately before `DedupApp = CerebroApp`. |
| **Before** | (no comment) `DedupApp = CerebroApp` |
| **After** | `# Public alias for compatibility; CerebroApp is the canonical class name.` then `DedupApp = CerebroApp` |
| **Location** | Lines 523–524. |
| **Branch/merged** | Branch only. |

---

## 9. Packaging — tests excluded from distribution

| Field | Value |
|-------|--------|
| **File path** | `setup.py` (repo root) |
| **Exact symbol / text** | `packages=` argument to `setup()`. |
| **Before** | `packages=find_packages(),` |
| **After** | `packages=find_packages(exclude=["dedup.tests", "dedup.tests.*"]),` |
| **Location** | Line 20. |
| **Branch/merged** | Branch only. |

---

## 10. Documentation — single-authority matrix

| Field | Value |
|-------|--------|
| **File path** | `REPO_AUTHORITY.md` (repo root) |
| **Exact symbol / text** | New file. |
| **Before** | (file did not exist) |
| **After** | New file: “Single-authority matrix” for Scan, Review, other pages; live read path, command path, notes; rules (no app→page-private for actions; ScanPage store-only when attached; Review selectors + controller; packaging note). |
| **Location** | Whole file. |
| **Branch/merged** | Branch only. |

---

## 11. Documentation — docs index

| Field | Value |
|-------|--------|
| **File path** | `docs/README.md` |
| **Exact symbol / text** | New file. |
| **Before** | (file did not exist) |
| **After** | New file: “Docs index” with Canonical (CONTROLLER_CONTRACTS, BUTTON_HIERARCHY, LOADING_ERROR_STATES, REVIEW_SCALE), Phase and status, Reference/design, and pointer to repo-root REPO_AUTHORITY.md. |
| **Location** | Whole file. |
| **Branch/merged** | Branch only. |

---

## Summary table

| # | Claim | File(s) | Branch/merged |
|---|--------|---------|----------------|
| 1 | Review actions use controller not page-private | `dedup/ui/app.py` | Branch only |
| 2 | History refresh via public API | `dedup/ui/app.py`, `dedup/ui/pages/history_page.py` | Branch only |
| 3 | Diagnostics refresh via public API | `dedup/ui/app.py`, `dedup/ui/pages/diagnostics_page.py` | Branch only |
| 4 | ScanPage detach hub when attaching store | `dedup/ui/pages/scan_page.py` | Branch only |
| 5 | Review docstring Clear selection accurate | `dedup/ui/pages/review_page.py` | Branch only |
| 6 | README CEREBRO / six-page / store+controllers | `README.md` | Branch only |
| 7 | main.py docstring CEREBRO / six-page | `dedup/main.py` | Branch only |
| 8 | DedupApp alias commented | `dedup/ui/app.py` | Branch only |
| 9 | Tests excluded from packages | `setup.py` | Branch only |
| 10 | REPO_AUTHORITY.md added | `REPO_AUTHORITY.md` | Branch only |
| 11 | docs/README.md index added | `docs/README.md` | Branch only |

---

## Remaining audit (not done in this sweep)

These were called out in the original action plan but were **not** implemented as code/docs in this pass; they remain as possible future work:

- **Priority 0 — Repo inventory:** Classify every file/dir as canonical / transitional / stale / test / docs-archive with “keep / merge / delete / archive” and owner layer. *Not produced.*
- **Priority 1 — Full authority audit:** Page-by-page table of hub vs store vs VM vs coordinator vs controller for every page and selector vs raw state. *Partially covered by REPO_AUTHORITY.md; not exhaustive per-symbol.*
- **Priority 2 — Dead/stale code:** Legacy aliases, unused components, duplicated utils, files not imported, superseded docs. *Not produced.*
- **Priority 3 — Packaging report:** install_requires vs requirements.txt, entrypoint naming, “production-safe packaging target” and recommended order. *Only fix: exclude tests in setup.py.*
- **Priority 4 — Doc drift report:** Systematic comparison of README, root audits, docs/, and in-file docstrings to current shell/pages/naming. *Only fix: README and main.py + docs/README.md index.*
- **Priority 5 — UI/component hygiene:** Hardcoded fonts/spacing, old variants, shell/pages/components/badges/ribbons not aligned to design system. *Not re-audited in this pass (Phase 2C/3A work assumed).*
- **Priority 6 — Production checkpoints:** Checkpoint matrix (architecture convergence, stale code removed, docs synced, packaging, no legacy action calls, no duplicate ScanPage paths, smoke/release checklist). *Not produced.*

**Conclusion:** All “confirmed and fixed” items above are backed by the evidence in this document. They exist **only on** `feature/ui-store-intents-migration`. The listed “remaining audit” items are still open and would require a separate pass.
