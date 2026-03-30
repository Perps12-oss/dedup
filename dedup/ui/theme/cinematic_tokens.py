"""
Cinematic chrome tokens — align inset CTk chrome with card/panel surfaces.

Themes may set ``cinematic_chrome_base`` / ``cinematic_chrome_dark``; otherwise values
are derived. ``bg_panel`` and ``bg_elevated`` are recomputed from chrome so repaints
match the main column fill.
"""

from __future__ import annotations

from typing import Any, Dict

from .gradients import cinematic_chrome_color as _compute_chrome_from_gradient
from .gradients import hex_to_rgb, rgb_to_hex

ThemeDict = Dict[str, Any]


def adjust_color(hex_color: str, *, brightness: int = 0) -> str:
    """Shift each RGB channel by ``brightness`` (negative = darker). Clamped to 0–255."""
    r, g, b = hex_to_rgb(hex_color)
    r = max(0, min(255, r + brightness))
    g = max(0, min(255, g + brightness))
    b = max(0, min(255, b + brightness))
    return rgb_to_hex(r, g, b)


def _is_hex_color(value: object) -> bool:
    s = str(value).strip()
    return len(s) == 7 and s.startswith("#")


def finalize_cinematic_tokens(t: ThemeDict) -> ThemeDict:
    """
    Ensure chrome keys exist; derive ``bg_panel`` / ``bg_elevated`` from chrome base.

    Fallback when ``cinematic_chrome_base`` is absent: same heuristic as
    :func:`gradients.cinematic_chrome_color` (gradient wash approximation).
    """
    out = dict(t)
    mode = str(out.get("mode", "dark")).lower()
    is_dark = mode != "light"

    raw_base = out.get("cinematic_chrome_base")
    if _is_hex_color(raw_base):
        base = str(raw_base).strip()
    else:
        base = _compute_chrome_from_gradient(out, reduced=False)
    out["cinematic_chrome_base"] = base

    raw_dark = out.get("cinematic_chrome_dark")
    if _is_hex_color(raw_dark):
        out["cinematic_chrome_dark"] = str(raw_dark).strip()
    else:
        delta = -14 if is_dark else -10
        out["cinematic_chrome_dark"] = adjust_color(base, brightness=delta)

    out["bg_panel"] = adjust_color(base, brightness=-5)
    out["bg_elevated"] = adjust_color(base, brightness=-2)
    # Surface token for scrollables and contained elements (between base and panel)
    if "bg_surface" not in out or not _is_hex_color(out.get("bg_surface")):
        out["bg_surface"] = adjust_color(base, brightness=-3)

    return out
