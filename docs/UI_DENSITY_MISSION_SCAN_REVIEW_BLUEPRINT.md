# Blueprint: UI density, Mission / Scan / Review, and status strip

**Purpose:** Actionable implementation plan derived from design review (screenshot annotations + written feedback), **grounded in this repository** (`dedup/ui/pages/mission_page.py`, `scan_page.py`, `review_page.py`, `dedup/ui/shell/status_strip.py`, `app_shell.py`).  
**Principle:** Every change must **improve** clarity, density, or maintainability **without** degrading architecture, test health, or cross‑platform behavior. Optional deps (`sv-ttk`, `pywinstyles`, etc.) remain optional with safe fallbacks.

**Documentation rule:** For each **stage** below, update **`docs/ENGINEERING_STATUS.md`** (changelog + snapshot table) and, where behavior is user‑visible, **`docs/README.md`** or the relevant doc (`THEME_SYSTEM.md`, `MODE_TOGGLE.md`, etc.). Commit messages should reference the blueprint section ID (e.g. `P0-M1`).

**Testing rule (mandatory after every stage):**

1. `python -m ruff check dedup` and `python -m ruff format dedup` (or project‑equivalent).
2. `python -m pytest dedup/tests -q` — **must pass**; no new unhandled thread/traceback warnings introduced for core flows.
3. **Smoke GUI** (manual): `python -m dedup` — launch Mission → Scan → Review path; cancel scan; open Settings. Confirm no import errors without `[modern-ui]` extras.
4. If the stage touches optional deps, repeat smoke **with** `pip install -e ".[modern-ui]"` on a dev machine **and** without extras on a clean venv.

---

## Issue inventory (master checklist)

Use this table to tick items as you implement. IDs are stable for commits/docs.

| ID | Area | Issue (from review + screenshot) | Priority | Status |
|----|------|-----------------------------------|----------|--------|
| P0-S0 | Global | Excessive vertical whitespace / single‑column feel; wasted horizontal space on wide windows | P0 | ☐ |
| P0-S1 | Status strip | Bottom strip reads as low‑contrast “noise”; users perceive **hidden** or non‑actionable diagnostics (`status_strip.py`) | P0 | ☑ |
| P0-M1 | Mission | First‑time impression: hero + readiness + quick scan compete for attention; **Simple** mode should be calmer than Advanced | P0 | ☑ |
| P0-K1 | Scan | Scan page must stay **progress‑first**; avoid duplicating Review‑level detail during active scan | P0 | ☐ |
| P1-M2 | Mission | **Advanced** options (engine, capabilities, extra cards) should stay behind existing `ui_mode` / `AppSettings` flags — tighten progressive disclosure | P1 | ☐ |
| P1-R1 | Review | Information density: navigator + workspace + rail; risk of overload — need **focus modes** / collapsible rails (respect existing virtual nav) | P1 | ☐ |
| P1-G1 | Grid | Prefer **`grid`** + weighted columns for main shells where `pack` causes center‑heavy empty regions | P1 | ☐ |
| P2-D1 | Docs | README/demo: screenshot or short GIF of Mission + Theme Lab; clarify “CEREBRO” vs legacy naming | P2 | ☐ |
| P2-T1 | Tests | Add/extend UI smoke or VM tests for mission/scan/review **layout invariants** (widget existence, no exception on `sync_chrome`) where feasible | P2 | ☐ |
| P3-X1 | Platform | Linux/macOS: no crash if `pywinstyles` / Mica missing; typography fallbacks already in `design_system` — verify on non‑Windows | P3 | ☐ |

---

## Priority tiers

| Tier | Focus | Rationale |
|------|--------|-----------|
| **P0** | Density, status strip legibility, Mission first impression, Scan vs Review separation | Matches screenshot (“SPACE”, “HIDDEN MENUS”) and core workflow |
| **P1** | Mission/Scan/Review structural layout (grid, sidebars, collapsible sections), Review focus | Usability without rewriting engine |
| **P2** | Documentation, screenshots, automated smoke tests | Sustainability and onboarding |
| **P3** | Cross‑platform verification, CLI story (optional) | Broader audience; do not block P0 |

---

## Stage 0 — Baseline & instrumentation (before code churn)

**Goal:** Measure so we don’t “fix” blindly.

**Steps**

1. Capture **current** window sizes: min/default/max for `CerebroApp` root (`dedup/ui/app.py`).
2. Document **Simple vs Advanced** mission layout rules already in `MissionPage.sync_chrome()` / store — re‑read `MODE_TOGGLE.md` and `mission_page.py` hero + `content_host` max width in `app_shell.py` (`MAX_CONTENT_WIDTH`).
3. Screenshot “before” (Mission, Scan running, Review) for `docs/` or README — attach filenames in ENGINEERING_STATUS.

**Tests:** Full pytest + manual launch (see global testing rule).

**Docs:** `ENGINEERING_STATUS.md` — “UI density baseline” bullet.

---

## P0 — Global density & content width (`app_shell.py`, `design_system.py`)

**Problems:** Centered `content_host` with `MAX_CONTENT_WIDTH` can leave **large side margins** on ultrawide displays — feels like “wasted SPACE” (screenshot).

**Implementation steps**

1. **Review `AppShell._on_content_resize` and `_content_host.place`** — document intended behavior (readable line length vs fill).
2. **Options (choose one per product preference; do not combine blindly):**
   - **A.** Slightly raise `MAX_CONTENT_WIDTH` for Mission/Scan only via page‑specific wrapper (harder), or  
   - **B.** Add `AppSettings` key `content_max_width_ux` (optional) with conservative default — **only if** it doesn’t break Review table readability.  
   - **C.** Leave max width; **reduce internal padding** on Mission hero (`_PAD_PAGE` / `_GAP_*` in `mission_page.py`) — lowest risk.
3. Prefer **C first** (padding + gap tuning), then re‑evaluate B.

**Tests:** Pytest + manual resize window 1280×720 and 1920×1080; no layout exceptions.

**Docs:** Short subsection in this blueprint + ENGINEERING_STATUS; if new setting, document in `MODE_TOGGLE.md` or Settings UI.

**Checklist:** P0-S0 partially addressed by measurement + padding; mark when done.

---

## P0 — Status strip: visible diagnostics, not “hidden” (`status_strip.py`, `app_shell.py`)

**Problems:** Annotation **“HIDDEN MENUS”** on bottom bar — strip is dense, small `strip` font, many tokens; users don’t know what’s interactive vs static.

**Implementation steps**

1. **Clarify semantics:** Status strip is **read‑only telemetry**, not menus. If the product needs actions, add **one** overflow pattern:
   - e.g. click strip opens **Diagnostics** or a popover — **optional**, gated behind Advanced.
2. **Visual hierarchy:**
   - Group related cells (session | phase | engine) with subtle separators or spacing.
   - Increase **contrast** for primary fields (phase, warnings) using existing tokens (`text_muted` vs `text_primary`) in `_apply_colors`.
3. **Simple mode:** Hide or collapse low‑value cells (`storage`, `intent`) when `store.state.ui_mode == "simple"` — wire through `StatusStrip` + `CerebroApp._update_status` or hub subscription (align with existing simple gating philosophy).
4. **Tooltip / title:** Set `widget.tooltip` or `bind` to show full session id on hover (if not already).

**Tests:** Pytest; manual Simple/Advanced toggle; strip updates during scan without exceptions.

**Docs:** `ENGINEERING_STATUS.md` + one paragraph in `docs/README.md` (“Bottom strip shows …”).

**Checklist:** P0-S1 ☑

---

## P0 — Mission page: calmer first impression (`mission_page.py`)

**Current state (code):** `MissionPage._build` already uses a **grid**, hero, MetricCards, Quick Scan — **not** the fictional single `MissionView` from external review. The issue is **perceived crowding** and **empty regions** depending on mode.

**Implementation steps**

1. **Simple mode (store `ui_mode`):**  
   - Ensure **single column** hero + last scan + quick scan only (existing behavior) — **verify** `sync_chrome()` hides Engine/Recent when intended.  
   - Reduce vertical gap between hero CTAs and Quick Scan (`_GAP_LG` → `_GAP_MD`) **only in simple** via conditional in `_build` or `sync_chrome`.
2. **Advanced mode:** Keep multi‑card dashboard; consider **two‑column** readiness row already present — ensure **row weights** so “Recent sessions” doesn’t leave a huge void: use `content.rowconfigure` and minimum heights on cards consistently.
3. **Quick Scan row:** Buttons “Documents / Pictures / Downloads” — keep horizontal; ensure `SectionCard` doesn’t add redundant vertical padding.
4. **Progressive disclosure:** Any **new** scan options belong in **Scan** or **Settings**, not Mission — do not add fields here unless they reduce navigation steps.

**Tests:** Pytest; manual Simple vs Advanced; start scan from quick path.

**Docs:** Update mission section in `PHASE_ROLLOUT.md` or README feature list if layout changes user‑visible behavior.

**Checklist:** P0-M1 ☑

---

## P0 — Scan page: progress‑first (`scan_page.py`, hub projections)

**Problems (review):** Mixing duplicate **detail** into live scan view confuses users. Our codebase may show phase metrics / events — verify against product: **during scan**, user should see **phase, progress, cancel/stop**, not a full duplicate review table.

**Implementation steps**

1. Audit `ScanPage` for any widget that lists **duplicate groups** before completion — if present, gate behind **Advanced** or remove from active scan panel.
2. Ensure **primary progress** (bar or indeterminate + label) is top‑of‑fold; **Live Metrics** / **Activity** cards respect `scan_show_*` flags (`AppSettings`).
3. **Cancel / Stop** — align with `CerebroApp` actions; labels already clarified in prior work — verify one obvious path.
4. Threading: coordinator/workers already off UI thread; UI updates via hub/store — **do not** move long work to UI thread.

**Tests:** Pytest + manual scan start/cancel; no UI freeze (subjective; watch phase updates).

**Docs:** Short “Scan page contract” bullet in ENGINEERING_STATUS.

**Checklist:** P0-K1 ☐

---

## P1 — Review page: reduce overload without losing power (`review_page.py`, components)

**Problems:** Review is feature‑rich (navigator, workspace, rail, dialogs). Risk: too many simultaneous panels.

**Implementation steps**

1. **Defaults:** Collapse or narrow **non‑essential** rails in Simple mode (e.g. compare hidden already — verify `set_ui_mode`).
2. **Navigator:** Keep virtualized path when `CEREBRO_VIRTUAL_NAV` — document env in README.
3. **Summary band:** Strengthen **top summary** (groups, reclaimable) — single glance row; avoid duplicating in three places.
4. **Spacing:** Apply same 8px grid tightening as Mission — use `_S` helpers; avoid adding new fonts.
5. **Batch actions:** If batch UX exists in `ReviewController`, surface **one** primary batch CTA; move rare actions to menu or Advanced.

**Tests:** Pytest (review tests); manual large‑group scroll.

**Docs:** `REVIEW_SCALE.md` update if thresholds change.

**Checklist:** P1-R1 ☐

---

## P1 — Layout system: grid adoption policy

**Steps**

1. For new layout work, prefer **`grid`** inside `SectionCard` bodies and page `content` frames; keep `pack` only for trivial stacks.
2. Document in `docs/UI_CONSISTENCY_AUDIT.md` or a short **`docs/LAYOUT_CONVENTIONS.md`** (new file allowed if team wants single source of truth).

**Tests:** No separate test; lint + manual.

**Checklist:** P1-G1 ☐

---

## P2 — Documentation & demo assets

**Steps**

1. Add **screenshot** or GIF: Mission + Themes page (Theme Lab) — store under `docs/assets/` or repo wiki; link from `README.md`.
2. **ENGINEERING_STATUS:** Realistic line on test coverage and mypy backlog (review’s point).
3. **License:** Verify `LICENSE` exists at repo root; if missing, add MIT text (legal decision — product owner).

**Tests:** N/A.

**Checklist:** P2-D1 ☐

---

## P2 — Automated tests

**Steps**

1. Add lightweight tests: e.g. instantiate `MissionPage` / `ScanPage` with a hidden `Tk` in tests **if** existing patterns allow — or extend `dedup/tests` with layout smoke that doesn’t require full GUI.
2. Ensure CI runs `pytest` on PRs.

**Tests:** pytest green.

**Checklist:** P2-T1 ☐

---

## P3 — Cross‑platform & optional CLI

**Steps**

1. Run app on Linux/macOS VM: confirm `try_apply_mica` no‑ops; `sun_valley_shell` off still uses clam; fonts resolve.
2. **CLI:** Core already has `python -m dedup /path` — document in README; no need for new CLI if it duplicates.

**Checklist:** P3-X1 ☐

---

## What we are **not** doing in this blueprint (scope guard)

- Full **CustomTkinter** migration of the shell (high risk; optional preview only exists).
- **Ripple / cross‑fade** animations on all widgets until P0–P1 are stable.
- Rewriting **duplicate detection engine** — out of scope for UI blueprint; engine stays decoupled in `dedup/engine/`.

---

## Suggested implementation order (sprints)

| Sprint | Stages | Exit criteria |
|--------|--------|----------------|
| **1** | Stage 0 + P0 content padding + P0 Mission simple gaps | Pytest + GUI smoke; ENGINEERING_STATUS updated |
| **2** | P0 Status strip hierarchy + simple collapse | Pytest + GUI smoke; screenshot “after” strip |
| **3** | P0 Scan audit + P1 Review spacing/summary | Pytest + manual scan→review |
| **4** | P1 Grid conventions doc + P2 README assets + tests | Pytest + doc links valid |
| **5** | P3 cross‑platform smoke | Manual matrix documented |

---

## Final checklist (sign‑off)

- [ ] All **P0** rows in master checklist addressed or explicitly deferred with reason in ENGINEERING_STATUS.
- [ ] **No regression** in `pytest`; no new mandatory deps for default install.
- [ ] **Documentation** updated per stage (see Documentation rule).
- [ ] **README** reflects Mission/Scan/Review intent and optional extras.

---

*This blueprint supersedes generic advice that referenced non‑existent `main_window.py` / `MissionView` classes; all file paths refer to the current CEREBRO layout under `dedup/ui/`.*
