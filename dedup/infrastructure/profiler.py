"""
DEDUP Profiler - Optional timing probes for bottleneck analysis.

Enable via: DEDUP_PROFILE=1

Usage:
    with measure("discovery.stat"):
        st = entry.stat()
"""
from __future__ import annotations

import os
import time
from contextlib import contextmanager
from threading import Lock
from typing import Dict, Any

_ENABLED = os.environ.get("DEDUP_PROFILE") == "1"
_TIMERS: Dict[str, list] = {}
_LOCK = Lock()


@contextmanager
def measure(name: str):
    """Context manager to time a block. No-op when DEDUP_PROFILE != 1."""
    if not _ENABLED:
        yield
        return
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        with _LOCK:
            _TIMERS.setdefault(name, []).append(elapsed)


def get_stats() -> Dict[str, Any]:
    """Return per-name stats: count, total_s, avg_ms. Empty when profiling disabled."""
    if not _ENABLED:
        return {}
    with _LOCK:
        out: Dict[str, Any] = {}
        for name, values in _TIMERS.items():
            total = sum(values)
            count = len(values)
            out[name] = {
                "count": count,
                "total_s": total,
                "avg_ms": (total / count) * 1000 if count else 0.0,
            }
        return out


def clear_stats() -> None:
    """Reset all collected timings."""
    if not _ENABLED:
        return
    with _LOCK:
        _TIMERS.clear()
