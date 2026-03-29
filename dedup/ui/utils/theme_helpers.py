"""
Theme helpers for CTk — normalize registry values to (light, dark) pairs.
"""

from __future__ import annotations

from typing import Any, Tuple

ColorPair = Tuple[str, str]


def theme_pair(value: Any, fallback: ColorPair) -> ColorPair:
    """Convert a single hex string, 2-tuple/list, or None into a (light, dark) pair for CTk."""
    if value is None:
        return fallback
    if isinstance(value, (tuple, list)) and len(value) >= 2:
        return (str(value[0]), str(value[1]))
    if isinstance(value, str) and value.startswith("#"):
        return (value, value)
    return fallback
