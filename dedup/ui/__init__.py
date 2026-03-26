"""
CEREBRO Dedup Engine — desktop UI (CustomTkinter).

The ttk / ttkbootstrap shell has been removed; use `CerebroCTKApp` from `dedup.ui.ctk_app`
or run `python -m dedup`.
"""

from __future__ import annotations

__all__ = ["CerebroCTKApp", "main"]


def CerebroCTKApp(*args, **kwargs):  # type: ignore[misc]
    from .ctk_app import CerebroCTKApp as _CerebroCTKApp

    return _CerebroCTKApp(*args, **kwargs)


def main(*args, **kwargs):  # type: ignore[misc]
    """Delegate to package CLI (`dedup.main.main`)."""
    import dedup.main as _m

    return _m.main(*args, **kwargs)
