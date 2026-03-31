# Legacy ttk / ttkbootstrap UI (removed)

The former **ttkbootstrap** shell (`dedup/ui/app.py`, `dedup/ui/shell/`, `dedup/ui/pages/`) has been **removed**.

The only desktop entry point is **CustomTkinter**: `python -m dedup` → `dedup.ui.ctk_app.CerebroCTKApp`.

Shared layers (**`ProjectionHub`**, **`UIStateStore`**, **`dedup.application` services**, controllers) remain in use by the CTK shell.
