"""
Failure semantics and diagnostics recording.

Used by pipeline, coordinator, event bus, and hub to record
checkpoint failures, callback delivery failures, and repository issues
so they can be surfaced in the diagnostics UI instead of being swallowed.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional

_log = logging.getLogger(__name__)

# Categories for diagnostics
CATEGORY_CHECKPOINT = "checkpoint"
CATEGORY_REPOSITORY = "repository"
CATEGORY_CALLBACK = "callback"
CATEGORY_HUB_DELIVERY = "hub_delivery"
CATEGORY_AUDIT_LOG = "audit_log"
CATEGORY_DELETION = "deletion"


@dataclass
class DiagnosticEntry:
    """Single recorded warning/error for diagnostics display."""

    category: str
    message: str
    detail: str = ""
    timestamp: float = field(default_factory=time.monotonic)
    wall_time: float = field(default_factory=time.time)


class DiagnosticsRecorder:
    """
    Thread-safe recorder of operational failures and degraded-state events.
    Bounded buffer of recent entries; counts per category.
    """

    def __init__(self, max_entries: int = 100):
        self._max_entries = max_entries
        self._lock = threading.Lock()
        self._entries: List[DiagnosticEntry] = []
        self._counts: Dict[str, int] = defaultdict(int)

    def record(
        self,
        category: str,
        message: str,
        detail: str = "",
        log_level: int = logging.WARNING,
    ) -> None:
        """Record a diagnostic event and log it."""
        _log.log(
            log_level,
            "[%s] %s%s",
            category,
            message,
            f" | {detail}" if detail else "",
        )
        with self._lock:
            self._counts[category] += 1
            self._entries.append(
                DiagnosticEntry(
                    category=category,
                    message=message,
                    detail=detail,
                    timestamp=time.monotonic(),
                    wall_time=time.time(),
                )
            )
            if len(self._entries) > self._max_entries:
                self._entries.pop(0)

    def get_counts(self) -> Dict[str, int]:
        """Return copy of per-category counts."""
        with self._lock:
            return dict(self._counts)

    def get_recent(self, limit: int = 50, category: Optional[str] = None) -> List[DiagnosticEntry]:
        """Return most recent entries, optionally filtered by category."""
        with self._lock:
            entries = self._entries[-limit:] if limit else list(self._entries)
            entries = list(reversed(entries))
            if category:
                entries = [e for e in entries if e.category == category]
            return entries[:limit]

    def clear(self) -> None:
        """Clear all entries and counts (e.g. at start of new scan)."""
        with self._lock:
            self._entries.clear()
            self._counts.clear()

    @property
    def has_warnings(self) -> bool:
        """True if any diagnostic events have been recorded."""
        with self._lock:
            return sum(self._counts.values()) > 0


# Singleton used by pipeline, coordinator, events, hub
_recorder: Optional[DiagnosticsRecorder] = None
_recorder_lock = threading.Lock()


def get_diagnostics_recorder() -> DiagnosticsRecorder:
    global _recorder
    with _recorder_lock:
        if _recorder is None:
            _recorder = DiagnosticsRecorder()
        return _recorder
