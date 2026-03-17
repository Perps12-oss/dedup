"""
HistoryVM — state for the History page.

Owns:
  - HistoryProjection snapshot (refreshed on demand)
  - UI selection / filter state
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

from ..projections.history_projection import (
    HistoryProjection, HistorySessionProjection, EMPTY_HISTORY,
    build_history_from_coordinator,
)


@dataclass
class HistoryVM:
    """
    View-model for the History page.
    Thin: owns HistoryProjection + filter / selection state.
    """
    # --- Projection snapshot ---
    history:       HistoryProjection          = field(default_factory=lambda: EMPTY_HISTORY)

    # --- UI state ---
    selected_id:   Optional[str]              = None
    search_text:   str                        = ""
    show_resumable_only: bool                 = False
    show_failed_only:    bool                 = False

    def refresh(self, coordinator) -> None:
        """Pull fresh data. Safe to call on UI thread (no async work)."""
        self.history = build_history_from_coordinator(coordinator)

    def refresh_from_history(self, history: HistoryProjection) -> None:
        """Update from store history slice (when page is fed from store)."""
        self.history = history

    @property
    def filtered_sessions(self):
        sessions = list(self.history.sessions)
        if self.show_resumable_only:
            sessions = [s for s in sessions if s.is_resumable]
        if self.show_failed_only:
            sessions = [s for s in sessions if s.status == "failed"]
        if self.search_text:
            q = self.search_text.lower()
            sessions = [
                s for s in sessions
                if q in s.scan_id.lower()
                or q in s.roots_display.lower()
                or q in s.status.lower()
            ]
        return sessions

    @property
    def selected_session(self) -> Optional[HistorySessionProjection]:
        if not self.selected_id:
            return None
        for s in self.history.sessions:
            if s.scan_id == self.selected_id:
                return s
        return None

    # --- Aggregate metrics for summary cards ---
    @property
    def total_scans(self) -> int:
        return self.history.total_scans

    @property
    def resumable_count(self) -> int:
        return self.history.resumable_count

    @property
    def avg_duration_s(self) -> float:
        return self.history.avg_duration_s

    @property
    def avg_reclaim_bytes(self) -> int:
        return self.history.avg_reclaim_bytes

    # Legacy compat: history pages that iterate vm.entries
    @property
    def entries(self):
        return list(self.history.sessions)


# Backward-compatibility alias
SessionEntry = HistorySessionProjection
