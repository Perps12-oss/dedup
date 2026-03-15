"""
ScanVM — live state for the Scan page.

Now thin: owns only the projections it receives from ProjectionHub
plus user-interaction state (is_scanning, current_file display).
All business logic and metric computation live in the projection layer.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import time

from ..projections.session_projection import SessionProjection, EMPTY_SESSION
from ..projections.phase_projection import PhaseProjection, initial_phase_map
from ..projections.metrics_projection import MetricsProjection, EMPTY_METRICS
from ..projections.compatibility_projection import CompatibilityProjection, EMPTY_COMPAT


@dataclass
class ScanVM:
    """
    View-model for the Scan page.
    Thin holder of projection snapshots + UI interaction state.
    """
    # --- Projections (pushed by ProjectionHub) ---
    session:       SessionProjection                   = field(default_factory=lambda: EMPTY_SESSION)
    phases:        Dict[str, PhaseProjection]          = field(default_factory=initial_phase_map)
    metrics:       MetricsProjection                   = field(default_factory=lambda: EMPTY_METRICS)
    compat:        CompatibilityProjection             = field(default_factory=lambda: EMPTY_COMPAT)
    events_log:    List[str]                           = field(default_factory=list)

    # --- UI interaction state ---
    is_scanning:   bool  = False
    current_file:  str   = ""
    error_message: str   = ""
    _start_wall:   float = field(default_factory=time.time)

    def elapsed_display(self) -> str:
        """Wall-clock elapsed (for the UI timer label, independent of metrics)."""
        from ..utils.formatting import fmt_duration
        return fmt_duration(time.time() - self._start_wall)

    def reset(self) -> None:
        from ..projections.phase_projection import initial_phase_map as _im
        self.session      = EMPTY_SESSION
        self.phases       = _im()
        self.metrics      = EMPTY_METRICS
        self.compat       = EMPTY_COMPAT
        self.events_log   = []
        self.is_scanning  = True
        self.current_file = ""
        self.error_message= ""
        self._start_wall  = time.time()

    # --- Convenience accessors used by the page ---

    @property
    def resume_ribbon_variant(self) -> str:
        return self.compat.ribbon_variant if self.compat else "idle"

    @property
    def resume_detail(self) -> str:
        if not self.compat:
            return ""
        return self.session.resume_reason or self.compat.overall_resume_reason

    @property
    def work_saved_info(self) -> dict:
        """Summary dict consumed by the Work Saved panel."""
        c = self.compat
        reused_phases = [
            p for p in self.phases.values() if p.is_reused
        ]
        return {
            "Discovery reused":  "Yes" if any(p.phase_name == "discovery"      and p.is_reused for p in self.phases.values()) else "No",
            "Size reduction":    "Yes" if any(p.phase_name == "size_reduction" and p.is_reused for p in self.phases.values()) else "No",
            "Files skipped":     str(self.metrics.files_skipped),
            "Time saved":        f"~{self.metrics.time_saved_estimate:.0f}s" if self.metrics.time_saved_estimate else "—",
            "Resume reason":     self.session.resume_reason[:40] if self.session.resume_reason else "—",
            "Outcome":           self.session.resume_outcome_label or "—",
        }
