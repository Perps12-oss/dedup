"""
Optional Sun Valley (sv-ttk) base theme — Fluent-style ttk on Windows/macOS/Linux.

Install: pip install sv-ttk  (extra: modern-ui)
If import fails, ThemeManager falls back to clam + token overrides only.
"""

from __future__ import annotations


def set_sun_valley_theme(_root, dark: bool) -> bool:
    """
    Apply sv-ttk light or dark theme. Call before applying CEREBRO token overrides.

    Returns True if sv-ttk was applied, False if the package is missing or failed.
    """
    try:
        import sv_ttk  # type: ignore[import-untyped]

        sv_ttk.set_theme("dark" if dark else "light")
        return True
    except Exception:
        return False


def sun_valley_available() -> bool:
    try:
        import sv_ttk  # noqa: F401

        return True
    except Exception:
        return False
