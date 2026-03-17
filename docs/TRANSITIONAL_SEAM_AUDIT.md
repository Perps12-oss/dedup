# Transitional Seam Cleanup Audit (Phase 2B)

Answers the board’s backend next move: *Which legacy paths still exist? Which controllers still know too much? Which pages still bypass selectors/store? What still prevents review scale-out from being final?*  
Builds on [BOUNDARY_AUDIT.md](BOUNDARY_AUDIT.md) and [TRANSITIONAL_PATHS.md](TRANSITIONAL_PATHS.md).

---

## 1. Which legacy paths still exist?

From TRANSITIONAL_PATHS and code inspection:

| Path | Location | Status | Remove when / action |
|------|----------|--------|------------------------|
| Mission/History refresh on show | App: `_refresh_mission_state`, `_refresh_history_state` on page `on_show` | **Active** | Store populated by adapter on navigate or scan complete; or dedicated “Refresh” intent. |
| ScanPage receives coordinator | ScanPage __init__, fallback in start_scan/start_resume/_on_cancel | **Active** | ScanPage is store-only for display; all commands via ScanController (ScanController already exists and is wired). |
| ScanPage.attach_hub | App → ScanPage.attach_hub | **Active** | ScanPage subscribes to store only; hub→store adapter is sole writer for scan state. |
| DiagnosticsPage coordinator | DiagnosticsPage._refresh, load(session_id) | **Active** | Diagnostics slice in store or dedicated diagnostics refresh intent. |
| App terminal handler | App: hub.subscribe("terminal", _on_terminal) → _review.load_result, navigate | **Active** | Terminal completion pushes to store; dedicated handler triggers navigation/load. |
| MissionPage/HistoryPage fallback _refresh() | _refresh() when no store or legacy path | **Active** | Store always populated before page show (e.g. adapter on navigate). |
| ReviewController page ref | — | **Removed** | ReviewController already uses store + coordinator + callbacks only; no attach_page. |

**Summary:** No remaining “controller holds page reference” legacy. Remaining seams are: (1) **refresh-on-show** for Mission/History, (2) **ScanPage** still using hub + coordinator for display and fallback commands, (3) **DiagnosticsPage** using coordinator for history/detail, (4) **app terminal** driving review load/navigate directly. Each has a clear “remove when” in TRANSITIONAL_PATHS.

---

## 2. Which controllers still know too much?

| Controller | Knows | Target | Status |
|------------|--------|--------|--------|
| **ReviewController** | Store (review selection), coordinator, callbacks (get_current_result, on_preview_result, on_refresh_review_ui, on_confirm_deletion, on_execute_*) | Already store + coordinator + callbacks; no page, no UI types | **OK** |
| **ScanController** | Coordinator, store (intent lifecycle), callbacks (on_progress, on_complete, on_error) | Same; page passes callbacks at invoke time | **OK** |

**Summary:** Controllers are in good shape. They do not hold page references or widget refs. Remaining work is **contract standardization** (e.g. document callback signatures, ensure no controller ever takes a page/widget in the future).

---

## 3. Which pages still bypass selectors / store patterns?

| Page | Data source | Uses selectors? | Action |
|------|-------------|-----------------|--------|
| **MissionPage** | store (mission slice) via attach_store; VM from state | No selectors; reads `state.mission` and refreshes VM | Optional: add mission selectors and use them for consistency. |
| **ScanPage** | Hub → VM (direct); store only for intent in StatusStrip | No; page reads VM everywhere | **High impact:** migrate to store subscription + selectors for display; keep hub→store as single writer. |
| **ReviewPage** | Store (review selection) for sync; VM for display; controller uses store | Uses `review_selection(state)` in _sync and when pushing to store | **Partial:** expand selector usage for index/plan/preview if read in page. |
| **HistoryPage** | store (history) via attach_store; VM from state | No selectors; reads `state.history` | Optional: history selectors. |
| **DiagnosticsPage** | store (scan) via attach_store; uses selectors for session, phases, compat, events_log | **Yes** | **Pattern to copy** for other pages. |
| **SettingsPage** | UIState.settings; callbacks | N/A (no store slice) | No change. |

**Summary:** DiagnosticsPage is the **reference**: attach_store + selectors only. ScanPage is the **largest bypass**: still hub→VM for all display. Mission and History could adopt selectors for clarity; Review already uses review_selection and can standardize on selectors for any other review slice reads.

---

## 4. What still prevents review scale-out from being final?

From Master Plan Part II Phase 3 and current code:

| Blocker / gap | Current state | Needed for scale-out |
|---------------|----------------|----------------------|
| **Paged / incremental group loading** | Review loads full result; all groups in memory | Load groups in pages or windows; navigator does not hold full list in memory. |
| **Bounded group navigator** | Group list can be large; no virtualization | Virtualization or windowing in Group Navigator; only visible (or nearby) rows materialized. |
| **Thumbnail strategy** | Thumbnails generated on demand; cache exists | Lazy load, bounded concurrency, cache policy; avoid loading all thumbnails for all groups. |
| **Bounded logs / activity feed** | Events log has fixed display cap (e.g. 80) | Kept; ensure backend and store do not unboundedly grow log in memory. |
| **Deletion readiness / plan from store** | Plan built in controller from store selection + result | Already store-friendly; ensure plan slice is sufficient for UI and for future batch/undo. |
| **Review store slices** | index, selection, plan, preview exist | Ensure adapter/controller can drive them for paged data (e.g. index = current window of groups). |

**Summary:** Architecture (store, controller, intents) supports scale-out. The missing pieces are **implementation**: paged/windowed group loading, navigator virtualization, and thumbnail loading strategy. No new “seam” removal is required for scale-out; it’s Phase 3 build-out.

---

## 5. Recommended cleanup order (Phase 2B)

1. **Standardize controller APIs**  
   Document callback contracts for ReviewController and ScanController; ensure no page/widget types in signatures. Optional: small “controller contract” doc or inline docstrings.

2. **Reduce ScanPage’s hub/VM coupling**  
   - Hub → store adapter already pushes scan state.  
   - Add ScanPage subscription to store (scan slice).  
   - ScanPage renders from selectors(store) instead of VM; VM can be deprecated for display or fed only from store.  
   - Remove or narrow ScanPage.attach_hub once store is the only source for display.

3. **Optional selector rollout**  
   - Mission: add mission selectors if useful (e.g. readiness, last_scan, resumable_ids).  
   - History: add history selectors for list/selected.  
   - Review: use selectors for any remaining raw state.review.* reads.

4. **Document and, where useful, add “remove when” comments**  
   - In code: one-line comments at Mission/History refresh, ScanPage coordinator/hub, Diagnostics coordinator, app terminal handler, pointing at TRANSITIONAL_PATHS.  
   - Keeps future removals traceable.

5. **Leave review scale-out to Phase 3**  
   - No further seam removal required for scale-out.  
   - Proceed with paged groups, navigator virtualization, thumbnail strategy when starting Phase 3.

---

## 6. Verification checklist

- [ ] No controller holds a reference to a page or widget.
- [ ] All pages that display store-backed data use store subscription (attach_store or equivalent) and do not read directly from hub/coordinator for that data.
- [ ] At least Mission, Scan, Review, History, Diagnostics use selectors where they read store state (Diagnostics already does).
- [ ] TRANSITIONAL_PATHS and this audit are updated when a path is removed or a new one introduced.
- [ ] Review scale-out work is tracked separately (Phase 3) and does not block Phase 2B seam cleanup.

This document is the single reference for “transitional seam cleanup” and “what prevents review scale-out from being final” in the rebased plan.
