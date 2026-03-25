# UI parity matrix (primary CTK vs legacy ttk)

| Area | Primary (CTK) | Legacy (ttk) | Notes |
|------|---------------|--------------|--------|
| Default entry | `python -m dedup` | `python -m dedup --ui-backend ttk` | Env: `DEDUP_UI_BACKEND` |
| Scan / resume / cancel | Yes | Yes | Shared `ScanController` + `ScanApplicationService` |
| Review / keep / delete | Yes | Yes | Shared `ReviewController` + `ReviewApplicationService` |
| History | Yes | Yes | |
| Diagnostics | Yes | Yes | |
| Themes / settings | Yes | Yes | |
| Hub → store pipeline | Yes | Yes | Same `ProjectionHub` + `UIStateStore` |

Updates to this matrix should accompany any intentional divergence between shells.
