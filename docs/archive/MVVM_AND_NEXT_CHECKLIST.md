# MVVM & next direction — working checklist

**Purpose:** Single traceable list for the **MVVM / services / core** direction. Tick items as you complete them so progress is visible in git history.

**How to use:** Change `- [ ]` to `- [x]` next to finished items; commit with a short message (e.g. `docs: tick Mission VM slice`). Prefer one vertical slice per PR when possible.

**Related:** `docs/TODO_POST_PHASE3.md` (sprint backlog), `docs/CTK_V3_ROADMAP.md` (Phase D + product bar), `docs/ENGINEERING_STATUS.md` (what shipped).

---

## A — Foundation & repo

- [ ] Dev install from this repo: `pip install -e ".[modern-ui]"` or `pip install -r requirements-ctk.txt`
- [ ] `python -m pytest dedup/tests` green on your machine before large refactors
- [ ] `python -m dedup` and `python -m dedup --ui-backend ctk` documented / understood by the team

---

## B — Core & services spine (`dedup/core/`, `dedup/services/`, `dedup/models/`)

- [ ] **Observable / command** patterns (`dedup/core/`) used where state crosses VM boundaries — document any intentional exceptions
- [ ] **Service adapters** (`dedup/services/adapters/`) remain the preferred seam for tests and alternate UIs
- [ ] **Models** (`dedup/models/`) hold UI-facing DTOs/state shapes; avoid duplicating orchestration types in `ctk_pages/`
- [ ] **Single orchestration path:** engine + `ApplicationRuntime` / coordinators — no second scan/delete pipeline in views

---

## C — Page ViewModels vs CTK pages (vertical slices)

Complete **one bullet** when: VM owns presentation state + commands, page binds to VM (and store/controllers as today), and tests or manual smoke pass.

**Tick slices here** (GitHub renders these as checkboxes):

- [ ] **Mission** — `mission_page_vm.py` / `mission_vm.py` → `ctk_pages/mission_page.py`
- [ ] **Scan** — `scan_page_vm.py` / `scan_vm.py` → `ctk_pages/scan_page.py`
- [ ] **Review** — `review_page_vm.py` / `review_vm.py` → `ctk_pages/review_page.py`
- [ ] **History** — `history_page_vm.py` / `history_vm.py` → `ctk_pages/history_page.py`
- [ ] **Diagnostics** — `diagnostics_page_vm.py` / `diagnostics_vm.py` → `ctk_pages/diagnostics_page.py`
- [ ] **Themes** — `theme_page_vm.py` → `ctk_pages/themes_page.py`
- [ ] **Settings** — `settings_page_vm.py` → `ctk_pages/settings_page.py`
- [ ] **Welcome** — _(add VM when wired)_ → `ctk_pages/welcome_page.py`

**Per-slice criteria (copy into PR description when useful):**

- [ ] User actions go through **controllers** / **application services**, not ad-hoc coordinator grabs from the view.
- [ ] Long-running or worker callbacks still marshal to the **UI thread** via existing store/app patterns.
- [ ] Legacy reference pages (`dedup/ui/pages/*_legacy.py`) consulted only until slice is done; then trim dead paths if any.

---

## D — Quality gates

- [ ] New VM logic covered by **unit tests** where it contains branching or mapping
- [ ] **Integration:** hub adapter / controller tests extended when store or service contracts change (`dedup/tests/`)
- [ ] `python -m ruff check dedup` (and format) before merge

---

## E — Documentation trace (no lost thread)

- [ ] After each milestone: short entry in **`docs/ENGINEERING_STATUS.md`** changelog
- [ ] **`docs/TODO_POST_PHASE3.md`**: tick or adjust items when MVVM work **closes** a listed task
- [ ] **`docs/UI_AUTHORITY.md`** updated if shell / authority rules change
- [ ] This file: **tick sections A–D** as you go; keep **§C** in sync with reality

---

## F — v3.0 alignment (optional, when relevant)

Use **`docs/CTK_V3_ROADMAP.md`** P1/P2 and Phase D — tick here only when you intentionally ship against that doc.

- [ ] P1 History / Diagnostics / Settings bar reviewed against roadmap
- [ ] Phase D “post-3.0 consolidation” items linked from a PR or issue

---

*Last created: 2026-03 — edit dates inline when you make major checklist updates.*
