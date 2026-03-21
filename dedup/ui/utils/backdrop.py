"""
Optional OS backdrop hints (Windows Mica-style titlebar blend).

Requires: pip install pywinstyles  (extra: modern-ui)
Safe no-op if unavailable or not on Windows.
"""

from __future__ import annotations

import sys
from typing import Any


def try_apply_mica(root: Any, enabled: bool) -> bool:
    """
    On Windows 11+, try to apply Mica to the Tk toplevel when enabled.
    Returns True if a backend call succeeded.
    """
    if not enabled or sys.platform != "win32":
        return False
    try:
        import pywinstyles  # type: ignore[import-untyped]

        hwnd = root.winfo_id()
        dark = _is_dark(root)
        try:
            pywinstyles.apply_mica(hwnd, dark_mode=dark)
        except TypeError:
            pywinstyles.apply_mica(hwnd)
        return True
    except Exception:
        pass
    return False


def _is_dark(root: Any) -> bool:
    try:
        bg = root.cget("background")
        if isinstance(bg, str) and bg.startswith("#") and len(bg) == 7:
            r = int(bg[1:3], 16)
            g = int(bg[3:5], 16)
            b = int(bg[5:7], 16)
            lum = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0
            return lum < 0.45
    except Exception:
        pass
    return True
