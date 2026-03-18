"""
CEREBRO Design System
======================
Theme-agnostic tokens for typography, spacing, and elevation.
Shell and page components use these with theme colors for consistent layout and hierarchy.
Aligns with Master Plan: large page titles, compact data labels, consistent numeric typography.
"""
from __future__ import annotations
from typing import Dict, Any

# ---------------------------------------------------------------------------
# Typography (font family, size, weight)
# Segoe UI used for UI; numeric/data can use same family with consistent size/weight
# ---------------------------------------------------------------------------
FONT_FAMILY = "Segoe UI"

TYPOGRAPHY: Dict[str, Any] = {
    # Page-level: hero and primary headings
    "page_title": {"size": 18, "weight": "bold"},
    "page_subtitle": {"size": 10, "weight": "normal"},
    # Section and card titles
    "section_title": {"size": 12, "weight": "bold"},
    "card_title": {"size": 10, "weight": "bold"},
    # Data: compact labels and values (consistent numeric typography)
    "data_label": {"size": 8, "weight": "normal"},
    "data_value": {"size": 9, "weight": "bold"},
    "numeric": {"size": 9, "weight": "normal"},  # tabular where applicable
    # Body and UI default
    "body": {"size": 9, "weight": "normal"},
    "body_bold": {"size": 9, "weight": "bold"},
    # Small/caption and strip
    "caption": {"size": 8, "weight": "normal"},
    "strip": {"size": 7, "weight": "normal"},
    # Shell/nav
    "nav_icon": {"size": 14, "weight": "normal"},
}


def font_tuple(style_name: str) -> tuple:
    """Return (family, size, weight) for tkinter font=."""
    s = TYPOGRAPHY.get(style_name, TYPOGRAPHY["body"])
    return (FONT_FAMILY, s["size"], s["weight"])


# ---------------------------------------------------------------------------
# Spacing (padding/margin scale in pixels)
# ---------------------------------------------------------------------------
SPACING = {
    "xs": 2,
    "sm": 4,
    "md": 8,
    "lg": 12,
    "xl": 16,
    "page": 16,   # page edge padding
    "card": 12,   # card internal padding
}


# ---------------------------------------------------------------------------
# Elevation (semantic names; actual colors come from theme: bg_base, bg_panel, bg_elevated)
# ---------------------------------------------------------------------------
ELEVATION_LEVELS = ("base", "panel", "elevated", "overlay")
