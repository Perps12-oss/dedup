# Backlog

Small items worth tracking. Not scheduled.

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
