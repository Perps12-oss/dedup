# UI coverage matrix (CustomTkinter shell)

The **ttk / ttkbootstrap** shell has been **removed**. This matrix tracks the **CTK** shell only.

| Area | CTK (`python -m dedup`) | Notes |
|------|-------------------------|--------|
| Entry | `CerebroCTKApp` | `dedup/ui/ctk_app.py` |
| Scan / resume / cancel | Yes | `ScanController` + `ScanApplicationService` |
| Review / keep / delete | Yes | `ReviewController` + `ReviewApplicationService`; `ctk_pages/review_page.py` |
| History | Yes | `ctk_pages/history_page.py` |
| Diagnostics | Yes | `ctk_pages/diagnostics_page.py` |
| Themes / settings | Yes | `ctk_pages/themes_page.py`, `settings_page.py` |
| Hub → store pipeline | Yes | `ProjectionHub` + `ProjectionHubStoreAdapter` + `UIStateStore` |

Update this table when adding or changing CTK surfaces.
