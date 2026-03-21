# Button & interactive audit (living document)

## Convention

See `docs/BUTTON_HIERARCHY.md`: `Accent.TButton` (primary), `Ghost.TButton` (secondary), `Danger.TButton` (destructive), `Nav` cells (custom tk frames).

## Shell / app-level actions (`app.py` → `TopBar.set_page_actions`)

| Page | Label | Style | Callback | Status | Notes |
|------|-------|-------|----------|--------|-------|
| mission | New Scan | Accent | `_navigate("scan")` | OK | |
| mission | Resume | Ghost | `_on_resume_latest` | OK | |
| scan | Pause | Ghost | `_on_scan_pause` | Verify | Coordinator pause semantics |
| scan | Cancel | Ghost | `_on_scan_cancel` | OK | |
| scan | Copy Diag | Ghost | `_copy_diagnostics` | OK | |
| review | Preview Effects | Ghost | ReviewController preview | OK | |
| review | DELETE | Danger | ReviewController execute | OK | |
| history | Refresh | Ghost | `_history.refresh` | OK | |
| history | Export | Ghost | `lambda: None` | **Stub** | Implement export or remove (Phase 6) |
| diagnostics | Refresh | Ghost | `_diagnostics.refresh` | OK | |
| diagnostics | Export | Ghost | `lambda: None` | **Stub** | Same as history |
| settings | — | — | — | N/A | Actions in-page |
| themes | — | — | — | N/A | Phase 2 page uses swatches + apply |

## Per-page inventory

**Skipped in Phase 1:** exhaustive grep of every `ttk.Button` / `tk.Button` in each page (~1000+ LOC refactored recently).  
**Plan:** extend this table file-by-file (Mission → Settings) in a **Phase 3 sub-pass** after Export stubs are resolved.

## Non-functional links policy

Any `command=lambda: None` must be either implemented, hidden in Simple mode, or removed.
