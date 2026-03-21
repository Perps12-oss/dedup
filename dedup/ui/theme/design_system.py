"""
CEREBRO Design System
======================
Theme-agnostic tokens for typography, spacing, and elevation.
Shell and page components use these with theme colors for consistent layout and hierarchy.
Aligns with Master Plan: large page titles, compact data labels, consistent numeric typography.
"""

from __future__ import annotations

from typing import Any, Dict

# ---------------------------------------------------------------------------
# Typography (font family, size, weight)
# Segoe UI used for UI; numeric/data can use same family with consistent size/weight
# ---------------------------------------------------------------------------
FONT_FAMILY = "Segoe UI"

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


def font_tuple(style_name: str) -> tuple:
    """Return (family, size, weight) for tkinter font=."""
    s = TYPOGRAPHY.get(style_name, TYPOGRAPHY["body"])
    return (FONT_FAMILY, s["size"], s["weight"])


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
