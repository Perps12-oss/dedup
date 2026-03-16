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
class ScanSessionMetrics:
    files_discovered_total: int = 0
    directories_scanned_total: int = 0
    candidates_total: int = 0
    duplicate_groups_total: int = 0
    duplicate_files_total: int = 0
    reclaimable_bytes_total: int = 0
    elapsed_total_s: float = 0.0
    files_reused_total: int = 0
    dirs_reused_total: int = 0
    dirs_skipped_via_manifest: int = 0
    hash_cache_hits: int = 0
    hash_cache_misses: int = 0
    run_mode: str = "fresh"

    @property
    def discovery_speed(self) -> float:
        if self.elapsed_total_s > 0:
            return self.files_discovered_total / self.elapsed_total_s
        return 0.0

    @property
    def skip_ratio(self) -> float:
        if self.directories_scanned_total > 0:
            return self.dirs_skipped_via_manifest / self.directories_scanned_total
        return 0.0

    @property
    def hash_cache_hit_rate(self) -> float:
        total = self.hash_cache_hits + self.hash_cache_misses
        if total > 0:
            return self.hash_cache_hits / total
        return 0.0


@dataclass
class ScanPhaseMetrics:
    phase_name: str = "discovery"
    completed_units: int = 0
    total_units: Optional[int] = None
    elapsed_phase_s: float = 0.0
    current_item_label: str = ""
    status: str = "pending"


@dataclass
class ResultAssemblyMetrics:
    rows_processed: int = 0
    rows_total: int = 0
    groups_assembled: int = 0
    duplicate_files_in_results: int = 0


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
    session_metrics: ScanSessionMetrics                = field(default_factory=ScanSessionMetrics)
    phase_metrics: ScanPhaseMetrics                    = field(default_factory=ScanPhaseMetrics)
    result_metrics: ResultAssemblyMetrics              = field(default_factory=ResultAssemblyMetrics)

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
        self.session_metrics = ScanSessionMetrics()
        self.phase_metrics = ScanPhaseMetrics()
        self.result_metrics = ResultAssemblyMetrics()
        self.is_scanning  = True
        self.current_file = ""
        self.error_message= ""
        self._start_wall  = time.time()

    def apply_session_projection(self, proj: SessionProjection) -> None:
        self.session = proj
        if proj.status == "running" and proj.resume_policy in ("safe", "rebuild_phase"):
            self.session_metrics.run_mode = "resume"
        elif proj.status == "running":
            self.session_metrics.run_mode = "fresh"

    def apply_phase_projection(self, phases: Dict[str, PhaseProjection]) -> None:
        self.phases = phases
        active = next((p for p in phases.values() if p.status == "running"), None)
        if active:
            self.phase_metrics.phase_name = active.phase_name
            self.phase_metrics.completed_units = max(
                self.phase_metrics.completed_units, int(active.rows_written or 0)
            )
            self.phase_metrics.status = "active"

    def apply_metrics_projection(self, proj: MetricsProjection) -> None:
        self.metrics = proj
        sm = self.session_metrics
        sm.files_discovered_total = max(sm.files_discovered_total, int(proj.files_discovered_total or 0))
        sm.directories_scanned_total = max(sm.directories_scanned_total, int(proj.dirs_scanned or 0))
        sm.candidates_total = max(sm.candidates_total, int(proj.result_rows_assembled or 0))
        sm.duplicate_groups_total = max(sm.duplicate_groups_total, int(proj.result_duplicate_groups or proj.duplicate_groups_live or 0))
        sm.duplicate_files_total = max(sm.duplicate_files_total, int(proj.result_duplicate_files or 0))
        sm.reclaimable_bytes_total = max(sm.reclaimable_bytes_total, int(proj.result_reclaimable_bytes or 0))
        sm.elapsed_total_s = max(sm.elapsed_total_s, float(proj.elapsed_s or 0.0))
        sm.files_reused_total = max(sm.files_reused_total, int(proj.files_reused_from_prior_inventory or 0))
        sm.dirs_reused_total = max(sm.dirs_reused_total, int(proj.dirs_reused or 0))
        sm.dirs_skipped_via_manifest = max(sm.dirs_skipped_via_manifest, int(proj.dirs_skipped_via_manifest or 0))
        sm.hash_cache_hits = max(sm.hash_cache_hits, int(proj.hash_cache_hits or 0))
        sm.hash_cache_misses = max(sm.hash_cache_misses, int(proj.hash_cache_misses or 0))
        if proj.discovery_reuse_mode and proj.discovery_reuse_mode != "none":
            sm.run_mode = "incremental"

        pm = self.phase_metrics
        if proj.current_phase_name:
            pm.phase_name = proj.current_phase_name
        pm.completed_units = int(proj.current_phase_rows_processed or 0)
        pm.total_units = (
            int(proj.current_phase_total_units)
            if proj.current_phase_total_units is not None
            else None
        )
        pm.elapsed_phase_s = float(proj.current_phase_elapsed_s or 0.0)
        pm.current_item_label = proj.current_file or ""
        if proj.current_phase_name:
            pm.status = "active"

        rm = self.result_metrics
        rm.rows_processed = int(proj.result_rows_assembled or 0)
        rm.rows_total = int(proj.result_rows_assembled or 0)
        rm.groups_assembled = int(proj.result_duplicate_groups or 0)
        rm.duplicate_files_in_results = int(proj.result_duplicate_files or 0)

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
        sm = self.session_metrics
        skip_pct = f"{sm.skip_ratio * 100:.0f}%" if sm.skip_ratio > 0 else "—"
        hit_pct = f"{sm.hash_cache_hit_rate * 100:.0f}%" if sm.hash_cache_hit_rate > 0 else "—"
        return {
            "Reuse mode":        self.metrics.discovery_reuse_mode or sm.run_mode,
            "Dirs skipped":      str(sm.dirs_skipped_via_manifest),
            "Files reused":      str(sm.files_reused_total),
            "Skip ratio":        skip_pct,
            "Hash cache hit rate": hit_pct,
            "Compatible prior":  "Yes" if self.metrics.prior_session_compatible else "No",
            "Compatibility reason": (self.metrics.prior_session_rejected_reason or "none")[:40],
            "Time saved":        f"~{self.metrics.time_saved_estimate:.0f}s" if self.metrics.time_saved_estimate else "—",
        }
