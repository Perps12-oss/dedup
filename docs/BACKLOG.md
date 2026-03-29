# Backlog

Small items worth tracking. Not scheduled.

**Living implementation status:** `docs/ENGINEERING_STATUS.md` — keep in sync when closing backlog items.

---

## CTK Review page test coverage (follow-up — not a dead-layer merge blocker)

**Why `test_review_page.py` was removed:** That file exercised **VM-era and ttk-only paths** (`ReviewVM`, `review_workspace`, `SafetyPanel`, gallery/compare widgets). None of that is imported by the active **`dedup.ui.ctk_pages.review_page.ReviewPageCTK`** + `ReviewController` stack.

**Gap:** The live CTK review surface has **no direct automated tests** after removal. Add targeted coverage in a follow-up PR, for example:

- Instantiate `ReviewPageCTK` with a mock `on_execute` / minimal `UIStateStore` (or stub coordinator callbacks).
- Assert `load_result`, group selection, `_confirm_execute` / cancel paths, and `_show_result_panel` visibility rules.

Branch name suggestion: `test/ctk-review-page` or fold into `design/store-retention-and-projection-limits` only if tests need real store lifecycle fixtures.

---

## Branch 3 — `design/store-retention-and-projection-limits`

**Policy + implementation:** see `docs/STORE_RETENTION_AND_PROJECTION.md` (coordinator `_last_result`, store `reset_live_scan_projection` / `reset_review_state`, hub session start).

**Still optional / later:** lightweight `ScanResult` summaries after deletion; extra coordinator tests with a mocked worker.

**CTK Review tests:** `dedup/tests/test_ctk_review_page.py` — extend as behaviors grow.

---

## ~~Clear Keep UI control~~ ✅ Implemented

- **Context:** `ReviewVM.clear_keep(group_id)` exists but is not wired to any UI control.
- **Current behavior:** User can only change keep choice by selecting a different file as KEEP, or by loading a new scan.
- **Proposal:** Add a tertiary "Clear selection" (or similar) control somewhere in the Review UI to explicitly deselect the keeper for a group. Would call `vm.clear_keep(gid)` and refresh workspace + safety panel.
- **Docs:** See `dedup/ui/pages/review_page.py` module docstring (Clear Selection section).
- **Status:** Implemented. "Clear selection" toolbar in ReviewWorkspaceStack, wired to `ReviewVM.clear_keep()`.

---

## ~~Thumbnail worker shutdown cleanup~~ ✅ Implemented

- **Context:** `generate_thumbnails_async` spawns background threads. When the main Tk loop exits (e.g. test teardown), pending callbacks can `self.after(0, ...)` into a destroyed window → `RuntimeError: main thread is not in main loop`.
- **Impact:** Mostly visible as pytest warnings during `test_on_execute_delete_calls_executor` and similar.
- **Proposal:** Add a cancellation/shutdown hook so thumbnail workers can be told to stop and not schedule callbacks when the parent widget is gone. Or guard `after()` with a liveness check.
- **Status:** Implemented. `cancel_event` support in `generate_thumbnails_async`; Gallery/Compare views use it with `_on_destroy` bind and liveness check before `after()`.
