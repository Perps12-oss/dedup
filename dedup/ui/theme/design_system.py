"""
CEREBRO Design System
======================
Theme-agnostic tokens for typography, spacing, and elevation.
Shell and page components use these with theme colors for consistent layout and hierarchy.
Aligns with Master Plan: large page titles, compact data labels, consistent numeric typography.
"""

from __future__ import annotations

import sys
import tkinter.font as tkfont
from typing import Any, Dict

# ---------------------------------------------------------------------------
# Typography (font family, size, weight)
# Prefer modern UI stacks when available (Fluent / Sonoma–style).
# ---------------------------------------------------------------------------
FONT_FAMILY = "Segoe UI Variable" if sys.platform == "win32" else "Segoe UI"


def get_ui_font_family() -> str:
    return FONT_FAMILY


def apply_root_typography(root) -> None:
    """Resolve a modern UI font and apply Tk option_add defaults (call once after Tk exists)."""
    global FONT_FAMILY
    candidates = (
        "Segoe UI Variable",
        "Segoe UI",
        "Inter",
        "SF Pro Text",
        "Helvetica Neue",
        "Tahoma",
    )
    for name in candidates:
        try:
            f = tkfont.Font(root, family=name, size=10)
            actual = f.actual("family")
            if actual:
                FONT_FAMILY = str(actual)
                break
        except Exception:
            continue
    else:
        FONT_FAMILY = "Segoe UI"
    try:
        root.option_add("*Font", (FONT_FAMILY, 10))
        root.option_add("*TkDefaultFont", (FONT_FAMILY, 10))
        root.option_add("*TkTextFont", (FONT_FAMILY, 10))
        root.option_add("*TkFixedFont", ("Consolas", 10))
    except Exception:
        pass

# Display density (TopBar ⊞ control + Settings). Scales default font sizes in font_tuple().
_DENSITY_FONT_SCALE: Dict[str, float] = {
    "comfortable": 1.0,
    "cozy": 0.94,
    "compact": 0.88,
}
_UI_DENSITY: str = "comfortable"

TYPOGRAPHY: Dict[str, Any] = {
    # Page-level: hero and primary headings
    "page_title": {"size": 32, "weight": "bold"},
    "page_subtitle": {"size": 15, "weight": "normal"},
    # Section and card titles
    "section_title": {"size": 20, "weight": "bold"},
    "card_title": {"size": 20, "weight": "bold"},
    # Data: compact labels and values (consistent numeric typography)
    "data_label": {"size": 13, "weight": "normal"},
    "data_value": {"size": 15, "weight": "bold"},
    "metric_value": {"size": 26, "weight": "bold"},  # large stat (e.g. MetricCard)
    "numeric": {"size": 13, "weight": "normal"},  # tabular where applicable
    # Body and UI default
    "body": {"size": 15, "weight": "normal"},
    "body_bold": {"size": 15, "weight": "bold"},
    # Small/caption and strip
    "caption": {"size": 13, "weight": "normal"},
    "strip": {"size": 11, "weight": "normal"},
    # Shell/nav
    "nav_icon": {"size": 18, "weight": "normal"},
    # Empty state / large placeholder
    "empty_icon": {"size": 40, "weight": "normal"},
}


def set_ui_density(density: str) -> None:
    """Called when AppSettings.density changes (TopBar or Settings)."""
    global _UI_DENSITY
    _UI_DENSITY = density if density in _DENSITY_FONT_SCALE else "comfortable"


def get_ui_density() -> str:
    return _UI_DENSITY


def get_font_scale() -> float:
    return float(_DENSITY_FONT_SCALE.get(_UI_DENSITY, 1.0))


def font_tuple(style_name: str) -> tuple:
    """Return (family, size, weight) for tkinter font=."""
    s = TYPOGRAPHY.get(style_name, TYPOGRAPHY["body"])
    scale = get_font_scale()
    size = max(8, min(44, int(round(s["size"] * scale))))
    return (FONT_FAMILY, size, s["weight"])


# ---------------------------------------------------------------------------
# Spacing (padding/margin scale in pixels)
# ---------------------------------------------------------------------------
SPACING = {
    "xs": 4,
    "sm": 8,
    "md": 16,
    "lg": 24,
    "xl": 32,
    "page": 32,  # page edge padding
    "card": 24,  # card internal padding
}


# ---------------------------------------------------------------------------
# Elevation (semantic names; actual colors come from theme: bg_base, bg_panel, bg_elevated)
# ---------------------------------------------------------------------------
ELEVATION_LEVELS = ("base", "panel", "elevated", "overlay")
