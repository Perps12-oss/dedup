# Loading / Degraded / Error State Spec

Shared visual and behavioral treatment for system-state surfaces across the app.
Use real store/controller state only; no ad-hoc message strings that bypass state.

## States

| State | When | Visual | Behavior |
|-------|------|--------|----------|
| **loading** | Async work in progress (scan, load, refresh) | Spinner or progress + muted label | Disable primary action; optional cancel |
| **empty** | No data for this view (no groups, no sessions, no diagnostics) | Centered icon + heading + short message | Optional CTA (e.g. "Start scan", "Load results") |
| **degraded** | System can run but with reduced capability (e.g. compatibility degraded) | Banner: warning style, short message | Non-blocking; user can continue |
| **warning** | Recoverable or caution (e.g. partial delete, resume not available) | Inline or banner: warning style | User can dismiss or act |
| **hard error** | Operation failed (scan failed, load failed) | Panel or banner: danger style + message | Retry/dismiss; primary flow blocked until resolved |
| **partial results** | Some data loaded, some failed or truncated | Inline notice: warning style + summary | User can continue with what’s available |

## Reusable Components

- **InlineNotice** — Short inline message (info / warning / error). Use in toolbars, ribbons, or above content.
- **EmptyStateCard** — Centered empty state (icon + heading + message + optional CTA). Use when a section has no data.
- **DegradedBanner** — Full-width banner for degraded mode. Uses store/selector `degraded_state()` when available.
- **ErrorPanel** — Panel for hard errors: message + optional retry action. Use for scan error, load error, etc.

## Rules

1. Prefer in-page state surfaces over modal dialogs for non-blocking and degraded states.
2. Use messagebox only for critical confirmations (e.g. "Cancel scan?") or when a blocking modal is appropriate.
3. Loading state should always be driven by VM/store (e.g. `is_scanning`, `is_loading`).
4. Degraded and error copy should come from store/controller (e.g. `degraded_state(store)`, controller error callback payload).
