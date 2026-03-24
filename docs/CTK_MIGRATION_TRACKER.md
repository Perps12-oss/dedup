# CTK Migration Tracker

Tracks feature movement during the CustomTkinter sweep so we do not duplicate
controls across pages or accidentally re-introduce retired UX patterns.

## Ownership rules

- A user action should have one primary owner page.
- Secondary pages can expose shortcuts to that action, but should call the same
  shared callback/contract.
- During migration, keep a source-of-truth table updated per PR.

## Feature ownership (current CTK branch)

| Feature | Primary owner | Secondary access | Status |
|---|---|---|---|
| Start scan (photos/videos/files) | Welcome | Mission, Scan | Implemented (CTK scaffold) |
| Start generic scan | Scan | Mission | Implemented (CTK scaffold) |
| Resume interrupted scan | Mission | Scan, Welcome | Implemented (shared `resume_scan_latest`) |
| Open last review | Mission | Welcome | Implemented (shared `open_last_review`) |
| Scan progress + status | Scan | Poll heartbeat | Implemented (experimental) |
| Deletion planning/execution | Review | None | Implemented (Review Lite + coordinator) |
| Theme tuning | Themes | Settings (link) | Implemented (experimental) |
| Default keep policy | Scan | Review apply on load | Implemented (CTK scaffold) |
| Post-scan destination | Scan | None | Implemented (CTK scaffold) |
| Scan execution wiring | Scan | Welcome (preset source), Mission (resume shortcut) | Implemented (experimental) |
| Review Lite (groups / compare / keep / execute) | Review | Scan completion strip (route only) | Implemented (experimental) |
| Live scan metrics | Scan | None | Implemented (experimental) |
| Progress bar + guarded ETA (v1) | Scan | None | Implemented (experimental) |
| Deletion confirmation + result panel | Review | None | Implemented (experimental) |
| Disable Start/Resume while scan running | Scan | Shell poll sync | Implemented (experimental) |
| Scan history list + open in Review | History | None | Implemented (experimental) |
| Appearance + accent theme | Themes | Settings shortcut | Implemented (experimental) |
| Settings (paths + Themes / Diagnostics shortcuts) | Settings | None | Implemented (minimal) |
| Mission last-scan + resume + recent snapshot | Mission | Shell refresh on show / after scan | Implemented (experimental) |
| Diagnostics (runtime + recorder log) | Diagnostics | Classic UI for full hub timelines | Implemented (CTK-lite) |

## Moved from Review (planned)

- Content-type entry (`photos/videos/files`) -> Welcome
- Default keep-policy selection -> Scan setup (moved)
- Post-scan routing preference -> Scan setup (moved)

## Notes

- Avoid duplicating button rows with different behavior text/handlers.
- Prefer shared callback names in CTK shell:
  - `start_scan_with_mode(mode)`
  - `start_scan_default()`
  - `resume_scan_latest()`
  - `open_last_review()`
- Welcome and Mission both call the same shell handlers for resume and open review.

## Ownership violations checklist (per sweep step)

- [ ] Did we add any new button that duplicates an existing action on another page?
- [ ] If yes, does it call the same shared handler contract?
- [ ] Did we move setup choices out of Review instead of re-adding them there?
- [ ] Did we update this tracker table for any moved/introduced feature?
