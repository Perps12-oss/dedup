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

- **Constructor:** `ReviewController(coordinator, store, callbacks)` where `callbacks` implements `IReviewCallbacks` (single interface; no lambdas).
- **IReviewCallbacks (Protocol):**
  - `get_current_result() -> Any` — current ScanResult or None.
  - `set_preview_result(msg: str) -> None` — show dry-run result in SafetyPanel.
  - `refresh_review_ui() -> None` — refresh workspace and safety panel from store.
  - `confirm_deletion(plan, prev) -> str` — show confirmation dialog; return "cancel", "preview", or "delete".
  - `on_execute_start() -> None` — disable execute button, show “Executing…”.
  - `on_execute_done(result) -> None` — re-enable button, update UI, notify app.
- **App wiring:** App passes `callbacks=self._review`; ReviewPage implements IReviewCallbacks (public methods). No lambdas closing over page internals.
- **Store:** Controller reads `review_selection(state)` and calls `store.set_review_selection(...)` for SetKeep/ClearKeep. Plan and execute use coordinator.
- **No page reference.** Controller holds only the callbacks interface; UI updates are via that contract.

## Review: intents and store access (Phase 3A.2)

- **Intents:** SetKeep, ClearKeep, PreviewDeletion, ExecuteDeletion. All are handled by ReviewController; no page logic duplicates them.
- **Read path:** All review state read by the controller or by the page when syncing from store MUST use selectors: `review_selection(state)`, `review_plan(state)`, `review_index(state)`, `review_preview(state)`. Do not read `state.review` or `state.review.selection` directly.
- **Write path:** Only `store.set_review_selection(...)` is used for review UI-driven updates. Plan/preview slices are updated by the app or adapter when appropriate.

## Rules

- Controllers must not take a page or widget in their constructor or in callback signatures (except for the explicit callback functions that the app wires to page methods).
- New controllers should follow the same pattern: coordinator + store + callbacks only.
