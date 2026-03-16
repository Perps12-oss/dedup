"""Display-formatting helpers for CEREBRO UI."""
from __future__ import annotations
from pathlib import Path
from typing import Union
import datetime


def fmt_bytes(n: int) -> str:
    if n < 0:
        return "—"
    if n == 0:
        return "0 B"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return f"{n:.1f} PB"


def fmt_int(n: int) -> str:
    return f"{n:,}"


def fmt_pct(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "—"
    return f"{100 * numerator / denominator:.1f}%"


def fmt_duration(seconds: float) -> str:
    if seconds < 0:
        return "—"
    # Show fractional seconds for very short durations to avoid displaying "0s"
    if seconds < 10:
        return f"{seconds:.1f}s"
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    m = s // 60
    s2 = s % 60
    if m < 60:
        return f"{m}m {s2}s" if s2 else f"{m}m"
    h = m // 60
    m2 = m % 60
    return f"{h}h {m2}m" if m2 else f"{h}h"


def fmt_dt(dt_str: str) -> str:
    """Format ISO datetime string for display."""
    if not dt_str:
        return "—"
    try:
        s = str(dt_str).replace("T", " ")[:19]
        return s
    except Exception:
        return str(dt_str)[:19]


def truncate_path(path: Union[str, Path], max_len: int = 55) -> str:
    s = str(path)
    if len(s) <= max_len:
        return s
    name = Path(s).name
    if len(name) >= max_len - 3:
        return "…" + name[-(max_len - 1):]
    prefix = s[: max_len - len(name) - 4]
    return f"{prefix}…/{name}"
