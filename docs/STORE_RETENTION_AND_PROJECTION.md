# Store retention and projection lifecycle

This document is the **policy contract** for Branch 3: what stays in memory, what resets at session boundaries, and how the UI store stays consistent with the coordinator and `ProjectionHub`.

## A. ScanResult retention (coordinator)

| Situation | In-memory `ScanResult` (`ScanCoordinator._last_result`) |
|-----------|---------------------------------------------------------|
| **New scan starts** (not resume) | **Cleared** before the new worker starts. Prevents Review from showing duplicate groups from a previous completed scan while a new scan runs. |
| **Resume** | **Not** cleared; the same logical session continues until completion replaces it. |
| **Scan completes** | Set to the new `ScanResult` (existing behavior). |
| **History / load by id** | Loaded via `persistence.get_scan` — not the same as `_last_result` until the app assigns it (e.g. Review `load_result`). |
| **After deletion** | **Not** automatically cleared in v1; Review still holds `load_result` state. Optional future: replace with a lightweight summary or `load_result(None)` after policy-driven “done”. |

**Persistence**: Full `ScanResult` JSON in the DB is unaffected by clearing `_last_result`.

## B. UIStateStore slices

| Method | Purpose |
|--------|---------|
| `reset_live_scan_projection()` | Replaces `UIAppState.scan` with a fresh `ProjectedScanState`. Called when starting **any** scan (including resume) so selectors do not briefly show the **previous** session’s terminal/metrics. |
| `reset_review_state()` | Replaces `UIAppState.review` with a fresh `ReviewState`. Called when starting a **new** scan (not resume) so keep selections and plan slices do not leak into the next run. **Skipped on resume** so in-progress review context is not wiped. |

## C. ProjectionHub

- On `SESSION_STARTED` / engine session start, the hub already resets session, phases, metrics, and event log for the new scan (see `ProjectionHub._on_session_started`).
- **Store** reset above aligns the **store** with that boundary before new events arrive; the hub remains the source of truth for live metrics.

## D. Repeated scan flows (intent)

1. **Fresh scan after a prior scan**: coordinator clears `_last_result`; store clears scan projection + review; hub repopulates from events.
2. **Scan → Review → delete → new scan**: same as (1); deletion does not yet auto-clear Review page data (see backlog).
3. **Resume**: coordinator keeps `_last_result`; store resets **only** live scan projection; review slice preserved.

## E. Caps (existing)

- `set_events_log`: bounded to **500** entries (`store.py`).
- Hub event log: truncated to **500** (`hub.py`).

Further caps for hub-internal checkpoints are documented in `ProjectionHub` module docstring.

## F. Tests

- Store/coordinator lifecycle: `dedup/tests/test_store_retention.py`
- CTK Review page behavior: `dedup/tests/test_ctk_review_page.py`
