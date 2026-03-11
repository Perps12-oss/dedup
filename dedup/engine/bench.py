"""
DEDUP Bench Instrumentation - Internal metrics for performance and scale testing.

Enable via DEDUP_BENCH=1 or pass collect_bench=True to pipeline.
Metrics are logged (debug) or written to a small report; not shown in user UI.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, List, Any


@dataclass
class PhaseMetrics:
    """Per-phase timing and counts."""
    phase: str
    start_time: float = 0.0
    end_time: float = 0.0
    count: int = 0
    bytes_processed: int = 0
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def duration_seconds(self) -> float:
        return self.end_time - self.start_time if self.end_time else 0.0

    @property
    def rate_per_second(self) -> Optional[float]:
        if self.duration_seconds > 0 and self.count > 0:
            return self.count / self.duration_seconds
        return None

    @property
    def bytes_per_second(self) -> Optional[float]:
        if self.duration_seconds > 0 and self.bytes_processed > 0:
            return self.bytes_processed / self.duration_seconds
        return None


class BenchCollector:
    """Collects bench metrics during a scan; do not expose to user UI."""

    def __init__(self, enabled: bool = None):
        if enabled is None:
            enabled = os.environ.get("DEDUP_BENCH", "").strip() in ("1", "true", "yes")
        self._enabled = enabled
        self._phases: Dict[str, PhaseMetrics] = {}
        self._current_phase: Optional[str] = None
        self._current_start: float = 0.0
        self._event_count: int = 0
        self._discovery_count: int = 0
        self._candidate_count: int = 0
        self._confirmed_count: int = 0

    @property
    def enabled(self) -> bool:
        return self._enabled

    def start_phase(self, phase: str):
        if not self._enabled:
            return
        self._end_current_phase()
        self._current_phase = phase
        self._current_start = time.time()
        self._phases[phase] = PhaseMetrics(phase=phase, start_time=self._current_start)

    def end_phase(self, phase: str, count: int = 0, bytes_processed: int = 0, **extra):
        if not self._enabled:
            return
        if phase in self._phases:
            self._phases[phase].end_time = time.time()
            self._phases[phase].count = count
            self._phases[phase].bytes_processed = bytes_processed
            self._phases[phase].extra = extra
        self._current_phase = None

    def _end_current_phase(self):
        if self._current_phase and self._current_phase in self._phases:
            self._phases[self._current_phase].end_time = time.time()

    def record_discovery_batch(self, count: int):
        if self._enabled:
            self._discovery_count += count

    def record_candidates(self, count: int):
        if self._enabled:
            self._candidate_count = count

    def record_confirmed(self, count: int):
        if self._enabled:
            self._confirmed_count = count

    def record_progress_event(self):
        if self._enabled:
            self._event_count += 1

    def get_summary(self) -> Dict[str, Any]:
        """Return a summary dict for logging; not for user display."""
        if not self._enabled:
            return {}
        self._end_current_phase()
        phases = {}
        for name, m in self._phases.items():
            phases[name] = {
                "duration_seconds": round(m.duration_seconds, 3),
                "count": m.count,
                "bytes_processed": m.bytes_processed,
                "rate_per_second": round(m.rate_per_second, 2) if m.rate_per_second else None,
                "bytes_per_second": round(m.bytes_per_second, 2) if m.bytes_per_second else None,
            }
        return {
            "phases": phases,
            "discovery_total": self._discovery_count,
            "candidate_count": self._candidate_count,
            "confirmed_count": self._confirmed_count,
            "progress_events_emitted": self._event_count,
        }


# Optional: call from pipeline at end of run to log bench summary
def log_bench_summary(collector: Optional[BenchCollector]):
    if not collector or not collector.enabled:
        return
    try:
        from ..infrastructure.logger import get_logger
        summary = collector.get_summary()
        get_logger().debug("bench_summary", **summary)
    except Exception:
        pass
