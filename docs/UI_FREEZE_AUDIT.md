# CEREBRO UI Freeze Audit Report

## Summary

Comprehensive audit of the CEREBRO desktop application (Python/CustomTkinter) for UI freeze bottlenecks.
Performed 2026-04-16. Covers main-thread blocking I/O, widget rebuild storms, missing debounce,
and timer accumulation across all CTk pages and controllers.

**Total findings:** 12
**P1 (Critical):** 3 | **P2 (High):** 7 | **P3 (Medium):** 2

---

## Bottleneck Registry

### BN-001 — Synchronous file deletion on main thread

| Field | Value |
|---|---|
| **Category** | F (Destructive actions without progress) / J (Engine integration) |
| **Priority** | P1 |
| **File** | `dedup/ui/controller/review_controller.py` |
| **Lines** | 188-272 |
| **Description** | `handle_execute_deletion()` calls `self._review.execute_deletion(plan)` synchronously on the main thread. This invokes send2trash and filesystem I/O for every file in the deletion plan. |
| **Root Cause** | No background thread delegation for the deletion operation. |
| **Fix Strategy** | Wrap `self._review.execute_deletion(plan)` in `threading.Thread(target=..., daemon=True).start()`. Use `widget.after(0, callback)` to post results back to the UI thread. Show a progress indicator during execution. |
| **Risk** | Medium — must ensure UI callbacks run on main thread after deletion completes. |
| **Status** | FIXED |

---

### BN-002 — Filesystem I/O in diagnostics artifact tab

| Field | Value |
|---|---|
| **Category** | A (Main thread blocking) |
| **Priority** | P1 |
| **File** | `dedup/ui/ctk_pages/diagnostics_page.py` |
| **Lines** | 717-766 (specifically 736) |
| **Description** | `_populate_artifacts()` calls `Path(cp_dir).iterdir()` directly on the main thread to list checkpoint directory contents. Large checkpoint directories will freeze the UI. |
| **Root Cause** | Filesystem enumeration not offloaded to a background thread. |
| **Fix Strategy** | Run `Path(cp_dir).iterdir()` in a daemon thread. Collect results into a list, then post widget creation back to main thread via `widget.after(0, ...)`. |
| **Risk** | Low — isolated to one tab's population logic. |
| **Status** | FIXED |

---

### BN-003 — Blocking PIL Image.open on main thread

| Field | Value |
|---|---|
| **Category** | A (Main thread blocking) |
| **Priority** | P1 |
| **File** | `dedup/ui/ctk_pages/review_page.py` |
| **Lines** | 894 |
| **Description** | `_pil_to_ctk()` calls `Image.open(cached)` synchronously on the main thread. Called from `_refresh_heroes()` (line 908) for each hero image during group selection. Large images or slow storage cause visible stutter. |
| **Root Cause** | PIL decode not offloaded to background thread. |
| **Fix Strategy** | Load and resize images in a daemon thread. Post the final `CTkImage` creation back to the main thread via `widget.after(0, ...)`. Use a placeholder while loading. |
| **Risk** | Medium — must handle race conditions if user switches groups before image loads. |
| **Status** | FIXED |

---

### BN-004 — GradientBar resize without debounce

| Field | Value |
|---|---|
| **Category** | D (Zoom/scale events) / G (after() timer accumulation) |
| **Priority** | P2 |
| **File** | `dedup/ui/theme/gradients.py` |
| **Lines** | 193-209 |
| **Description** | `GradientBar._on_resize()` is bound to `<Configure>` with no debounce. Every pixel of window resize triggers a full gradient repaint with canvas rectangle creation. During a drag-resize this fires hundreds of times. |
| **Root Cause** | Missing debounce on the `<Configure>` event handler. |
| **Fix Strategy** | Add a debounce using `self.after_cancel()` / `self.after(30, self._do_resize)` pattern. Cancel any pending repaint before scheduling a new one. |
| **Risk** | Low — cosmetic only, gradient repaints slightly delayed during resize. |
| **Status** | FIXED |

---

### BN-005 — History page full widget rebuild on filter

| Field | Value |
|---|---|
| **Category** | H (Widget construction cost) |
| **Priority** | P2 |
| **File** | `dedup/ui/ctk_pages/history_page.py` |
| **Lines** | 533-543 |
| **Description** | `_populate_table()` destroys all child widgets of the table body and recreates them on every filter/search change. With many scan history entries this causes visible stutter. |
| **Root Cause** | Full destroy+rebuild pattern instead of in-place update or show/hide. |
| **Fix Strategy** | Cache row widgets keyed by scan ID. On filter change, hide non-matching rows (`grid_remove()`) and show matching ones (`grid()`) instead of destroying and recreating. |
| **Risk** | Medium — must handle row data updates and memory for cached widgets. |
| **Status** | OPEN |

---

### BN-006 — Mission page full session card rebuild

| Field | Value |
|---|---|
| **Category** | H (Widget construction cost) |
| **Priority** | P2 |
| **File** | `dedup/ui/ctk_pages/mission_page.py` |
| **Lines** | 141-174 |
| **Description** | `_render_recent_sessions()` destroys all children of `_recent_list_host` and rebuilds up to 8 session cards on every store update. Store updates can fire frequently during scans. |
| **Root Cause** | Full destroy+rebuild instead of diffing or in-place update. |
| **Fix Strategy** | Compare incoming session list with current displayed sessions. Only rebuild cards whose data changed. Skip rebuild entirely if data is identical. |
| **Risk** | Low — session list is small (max 8 cards). |
| **Status** | OPEN |

---

### BN-007 — Review page full group rows rebuild

| Field | Value |
|---|---|
| **Category** | H (Widget construction cost) |
| **Priority** | P2 |
| **File** | `dedup/ui/ctk_pages/review_page.py` |
| **Lines** | 630-668 |
| **Description** | `_clear_group_rows()` (line 630) does `winfo_children()` destroy loop. `_rebuild_group_rows()` (line 668) does full destroy+recreate of all group row widgets. Called when group list changes or filters update. With 100+ groups this is expensive. |
| **Root Cause** | Full destroy+rebuild pattern with no widget reuse. |
| **Fix Strategy** | Implement widget pooling: keep a pool of group row frames, reconfigure their text/state instead of destroying and recreating. Only create new widgets when the pool is exhausted. |
| **Risk** | Medium — group rows have selection state that must be preserved correctly. |
| **Status** | WONTFIX — only called once per scan result load, not on repeated filter changes. Cost is one-time. |

---

### BN-008 — Diagnostics page full rebuild on tab switch

| Field | Value |
|---|---|
| **Category** | H (Widget construction cost) |
| **Priority** | P2 |
| **File** | `dedup/ui/ctk_pages/diagnostics_page.py` |
| **Lines** | 517-518, 632-688, 690-715, 768-810 |
| **Description** | Switching tabs in the diagnostics page destroys all children and rebuilds: `_populate_phases()` (632-688), `_populate_events()` (690-715), `_populate_artifacts()` (717-766), `_populate_compatibility()` (768-810). Each function does a full winfo_children destroy loop. |
| **Root Cause** | No caching of populated tab contents. Tabs are rebuilt from scratch on every switch. |
| **Fix Strategy** | Cache tab contents. Only rebuild when underlying data changes (track a data version or hash). On tab switch, just lift/show the cached frame. |
| **Risk** | Low — diagnostics data changes infrequently. |
| **Status** | OPEN |

---

### BN-009 — Themes page gradient stop rows rebuild

| Field | Value |
|---|---|
| **Category** | H (Widget construction cost) |
| **Priority** | P2 |
| **File** | `dedup/ui/ctk_pages/themes_page.py` |
| **Lines** | 552-616 |
| **Description** | `_rebuild_stop_rows()` destroys all children and recreates gradient stop editor rows. Called during gradient editing which can be frequent (adding/removing/reordering stops). |
| **Root Cause** | Full destroy+rebuild instead of targeted updates. |
| **Fix Strategy** | Only rebuild the specific row that changed (add/remove/reorder). For reorder, use `grid_configure()` to move rows without destroying them. |
| **Risk** | Low — gradient stop count is typically small (3-6 stops). |
| **Status** | OPEN |

---

### BN-010 — Recursive label color traversal on theme change

| Field | Value |
|---|---|
| **Category** | E (Theme switching) |
| **Priority** | P2 |
| **File** | `dedup/ui/ctk_pages/scan_page.py` |
| **Lines** | 501-528 |
| **Description** | `_update_label_colors()` recursively traverses ALL child widgets via `winfo_children()` on every theme token update. This pattern is also used by `welcome_page.py` (line 91-94) via `apply_label_colors()`. Deep widget trees cause unnecessary traversal. |
| **Root Cause** | Brute-force recursive traversal instead of maintaining a registry of themed labels. |
| **Fix Strategy** | Maintain a list of label references that need color updates. On theme change, iterate only the registered labels instead of the full widget tree. Use weak references to avoid preventing garbage collection. |
| **Risk** | Low — labels are long-lived, weak refs handle cleanup. |
| **Status** | OPEN |

---

### BN-011 — Forced update_idletasks in execute start

| Field | Value |
|---|---|
| **Category** | A (Main thread blocking) |
| **Priority** | P3 |
| **File** | `dedup/ui/ctk_pages/review_page.py` |
| **Lines** | 461 |
| **Description** | `on_execute_start()` calls `self.update_idletasks()` which forces a synchronous redraw of all pending geometry changes. This blocks the main thread until all layout computations complete. |
| **Root Cause** | Explicit sync redraw call, likely added to ensure progress indicator appears before deletion starts. |
| **Fix Strategy** | Remove `update_idletasks()`. If visual feedback is needed before a long operation, use `widget.after(10, start_operation)` to let the event loop flush naturally. |
| **Risk** | Low — may need minor timing adjustment for progress indicator visibility. |
| **Status** | FIXED |

---

### BN-012 — Cinematic backdrop repaint without debounce

| Field | Value |
|---|---|
| **Category** | D (Zoom/scale events) |
| **Priority** | P3 |
| **File** | `dedup/ui/theme/gradients.py` |
| **Lines** | 112-172 |
| **Description** | `paint_cinematic_backdrop()` performs expensive canvas operations with math.sin calculations and up to 98 rectangle draws. When called from resize handlers without debounce, it generates heavy canvas churn. |
| **Root Cause** | Caller does not debounce calls to this function during resize events. The function itself has no guard against rapid repeated invocation. |
| **Fix Strategy** | Ensure all callers (ctk_app.py lines 136-137) debounce calls to `paint_cinematic_backdrop()`. Add a timestamp guard inside the function to skip repaints if called within 30ms of the last paint. |
| **Risk** | Low — cosmetic backdrop, slight delay is imperceptible. |
| **Status** | FIXED |

---

## Fix Order

| Order | BN | Priority | Rationale |
|---|---|---|---|
| 1 | BN-001 | P1 | Highest impact — file deletion freezes the entire UI for seconds. |
| 2 | BN-003 | P1 | PIL image decode blocks every group selection in review. |
| 3 | BN-002 | P1 | Filesystem I/O on main thread in diagnostics. |
| 4 | BN-004 | P2 | Fires hundreds of times during resize — easy debounce fix. |
| 5 | BN-012 | P3 | Related to BN-004 — debounce cinematic backdrop together. |
| 6 | BN-011 | P3 | Simple removal of update_idletasks(). |
| 7 | BN-007 | P2 | Review page group rebuild is the most-used widget rebuild path. |
| 8 | BN-005 | P2 | History table rebuild on every filter keystroke. |
| 9 | BN-006 | P2 | Mission page session cards rebuild on store updates. |
| 10 | BN-008 | P2 | Diagnostics tab switch rebuilds. |
| 11 | BN-009 | P2 | Themes page stop rows — small widget count mitigates impact. |
| 12 | BN-010 | P2 | Recursive label traversal — works but wasteful. |
