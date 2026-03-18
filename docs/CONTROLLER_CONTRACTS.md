# Controller callback contracts (Phase 2C.2)

Controllers receive callbacks from the app so they can trigger UI updates without holding page references. These are the documented contracts.

## ScanController

- **Constructor:** `ScanController(coordinator, store)`
- **Methods:** `handle_start_scan(path, options, on_progress, on_complete, on_error)`, `handle_start_resume(scan_id, on_progress, on_complete, on_error)`, `handle_cancel()`
- **Callbacks (passed at invoke time by ScanPage):**
  - `on_progress(): None` — optional; called during scan progress.
  - `on_complete(result: ScanResult): None` — called when scan finishes successfully; app/page navigates to review or updates UI.
  - `on_error(message: str): None` — called when scan fails.
- **Store:** Controller updates `store.scan.last_intent` (idle / accepted / completed / failed) via store setters used by the app or by the controller if given store access. ScanPage does not pass store to the controller; intent lifecycle is updated by the code path that invokes the controller.
- **No page reference.** ScanController does not hold a reference to ScanPage or any widget.

## ReviewController

- **Constructor:** `ReviewController(coordinator, store, get_current_result, on_preview_result, on_refresh_review_ui, on_confirm_deletion, on_execute_start, on_execute_done)`
- **Callbacks (injected by app at construction):**
  - `get_current_result() -> Any` — returns the current ScanResult or None; used to build deletion plan.
  - `on_preview_result(message: str) -> None` — show dry-run/preview result in SafetyPanel.
  - `on_refresh_review_ui() -> None` — refresh workspace and safety panel from store.
  - `on_confirm_deletion(plan, prev) -> str` — show confirmation dialog; return "ok" to proceed, else cancel.
  - `on_execute_start() -> None` — disable execute button, show “Executing…” (or similar).
  - `on_execute_done(result) -> None` — re-enable button, update UI, notify app.
- **Store:** Controller reads `review_selection(state)` and calls `store.set_review_selection(...)` for SetKeep/ClearKeep. Plan and execute use coordinator; UI updates go through callbacks.
- **No page reference.** ReviewController does not hold a reference to ReviewPage or SafetyPanel; all UI updates are via the callbacks above.

## Review: intents and store access (Phase 3A.2)

- **Intents:** SetKeep, ClearKeep, PreviewDeletion, ExecuteDeletion. All are handled by ReviewController; no page logic duplicates them.
- **Read path:** All review state read by the controller or by the page when syncing from store MUST use selectors: `review_selection(state)`, `review_plan(state)`, `review_index(state)`, `review_preview(state)`. Do not read `state.review` or `state.review.selection` directly.
- **Write path:** Only `store.set_review_selection(...)` is used for review UI-driven updates. Plan/preview slices are updated by the app or adapter when appropriate.

## Rules

- Controllers must not take a page or widget in their constructor or in callback signatures (except for the explicit callback functions that the app wires to page methods).
- New controllers should follow the same pattern: coordinator + store + callbacks only.
