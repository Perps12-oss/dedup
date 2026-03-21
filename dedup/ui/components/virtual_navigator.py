"""
Windowed flat-list scrolling for large Treeview tables (Review group navigator spike).

Set ``CEREBRO_VIRTUAL_NAV=1`` (or ``true`` / ``yes`` / ``on``) to enable. When the
filtered group count exceeds the table's visible row count, only that window of
rows is inserted into the Treeview; the scrollbar drives a logical offset into
the full list. When disabled or the list is short, Review uses the legacy path
(unchanged), including the existing 2000-row cap.

This is intentionally minimal — no hierarchical tree virtualization.
"""

from __future__ import annotations

import os

# Treeview row iids for virtual mode (stable per refresh slot index).
NAV_SLOT_PREFIX = "navslot:"


def virtual_navigator_enabled() -> bool:
    v = os.environ.get("CEREBRO_VIRTUAL_NAV", "").strip().lower()
    return v in ("1", "true", "yes", "on")


def clamp_top(top: int, total: int, visible: int) -> int:
    if total <= 0 or visible <= 0:
        return 0
    max_top = max(0, total - visible)
    return max(0, min(int(top), max_top))


def scrollbar_fracs(top: int, total: int, visible: int) -> tuple[float, float]:
    if total <= 0:
        return (0.0, 1.0)
    if total <= visible:
        return (0.0, 1.0)
    first = top / total
    last = (top + visible) / total
    return (float(first), float(last))


def slot_iid(slot: int) -> str:
    return f"{NAV_SLOT_PREFIX}{int(slot)}"
