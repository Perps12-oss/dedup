"""
WCAG-style contrast helpers for hex colours (sRGB).
Used for theme QA and the Themes page summary.
"""

from __future__ import annotations

import re
from typing import Optional, Tuple

_HEX = re.compile(r"^#?([0-9a-fA-F]{6})$")


def parse_hex(color: str) -> Optional[Tuple[float, float, float]]:
    """Return linear-ish sRGB channels in 0..1, or None if invalid."""
    m = _HEX.match(color.strip())
    if not m:
        return None
    raw = m.group(1)
    r = int(raw[0:2], 16) / 255.0
    g = int(raw[2:4], 16) / 255.0
    b = int(raw[4:6], 16) / 255.0
    return r, g, b


def _channel_luminance(c: float) -> float:
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance_hex(color: str) -> Optional[float]:
    """WCAG relative luminance for #RRGGBB."""
    rgb = parse_hex(color)
    if not rgb:
        return None
    r, g, b = (_channel_luminance(x) for x in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg: str, bg: str) -> Optional[float]:
    """Contrast ratio between two hex colours (1..21)."""
    l1 = relative_luminance_hex(fg)
    l2 = relative_luminance_hex(bg)
    if l1 is None or l2 is None:
        return None
    L1, L2 = max(l1, l2), min(l1, l2)
    return (L1 + 0.05) / (L2 + 0.05)


def passes_aa_normal(ratio: Optional[float]) -> bool:
    return ratio is not None and ratio >= 4.5


def passes_aa_large(ratio: Optional[float]) -> bool:
    return ratio is not None and ratio >= 3.0


def format_ratio(ratio: Optional[float]) -> str:
    if ratio is None:
        return "—"
    return f"{ratio:.2f}:1"
