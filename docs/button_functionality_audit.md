# Button & interactive audit

**Last updated:** Phase 1 completion pass (static review + shell / page grep).  
**Living project status:** `docs/ENGINEERING_STATUS.md` — update both when button behaviour changes.  
**Convention:** `docs/BUTTON_HIERARCHY.md`.

## Shell — `TopBar` contextual actions (`ctk_app` → `set_page_actions`)

| Page | Label | Style | Callback | Status |
|------|-------|-------|----------|--------|
| mission | New Scan | Accent | `_navigate("scan")` | OK |
| mission | Resume | Ghost | `_on_resume_latest` | OK |
| scan | Pause | Ghost | `_on_scan_pause` | OK |
| scan | Cancel | Ghost | `_on_scan_cancel` | OK |
| scan | Copy Diag | Ghost | `_copy_diagnostics` | OK |
| review | Preview Effects | Ghost | `ReviewController.handle_preview_deletion` | OK |
| review | DELETE | Danger | `ReviewController.handle_execute_deletion` | OK |
| history | Refresh | Ghost | `_history.refresh` | OK |
| history | Export | Ghost | `HistoryPage.export_sessions_json` | OK — JSON save-as (filtered rows) |
| diagnostics | Refresh | Ghost | `_diagnostics.refresh` | OK |
| diagnostics | Export | Ghost | `DiagnosticsPage.export_report_json` | OK — JSON snapshot of current view |
| settings | — | — | — | In-page only |
| themes | — | — | — | Swatches only |

## Mission (`mission_page.py`)

| Control | Style | Command / behaviour | Status |
|---------|-------|---------------------|--------|
| Start New Scan | Accent | `_on_start` | OK |
| Resume Interrupted | Ghost | `_on_resume` | OK |
| Open Last Review | Ghost | `_on_open_last_review` | OK |
| Watch Tour | Ghost | `_show_quick_tour` (messagebox) | OK |
| Documents / Pictures / Downloads | Ghost | `_set_path` | OK |
| Browse… | Ghost | `_on_browse` | OK |
| Start Scan (quick start) | Accent | `_on_start` | OK |
| Resume (quick start) | Ghost | `_on_resume` | OK |
| Recent session card Resume/Review | Ghost | `on_resume_scan` / `_on_open_last_review` | OK |
| Recent folder chips | Ghost | `_set_path` | OK |

## Scan (`scan_page.py`)

Primary buttons (footer / actions area): **Cancel**, **Go to Review**, path **Browse**, intent / diagnostic actions — all wired to `ScanController` or page methods (`_on_cancel`, `_go_review`, etc.). **Status:** OK (verify Pause semantics match coordinator on your build).

## Review (`review_page.py`)

Large surface: workspace modes, Smart Rules, SafetyPanel, dialogs. **SafetyPanel** exposes Preview / DELETE via controller from shell; in-page buttons call `ReviewController` / `ReviewVM` / `_on_execute` paths. **Status:** OK (see tests `test_review_page.py`).

## History (`history_page.py`)

List selection drives load/resume; **Refresh** from shell. Row actions depend on `DataTable` / bindings — wired to coordinator callbacks passed into page. **Status:** OK.

## Diagnostics (`diagnostics_page.py`)

**Refresh** from shell; in-page controls refresh projections / integrity views. **Status:** OK.

## Settings (`settings_page.py`)

Preference toggles and **Save** / **Reset**-style actions (if present) call `_on_pref` / persistence. **Status:** OK.

## Themes (`theme_page.py`)

Swatch grid only; selection calls `on_theme_change` (app `_on_theme_change`). **Status:** OK.

## Components (sample)

| Area | Notes |
|------|--------|
| `ReviewWorkspaceStack` | Table/Gallery/Compare + Keep actions → `on_keep` |
| `SafetyPanel` | DELETE / Preview → callbacks |
| `NavRail` | `on_navigate` per key |
| `InsightDrawer` | Sections are display-only |

## Follow-ups

1. Optional: CSV export, or **Simple mode** hiding Export if product wants a leaner bar.
2. Re-audit after any new page or toolbar action.
