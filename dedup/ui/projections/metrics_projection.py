"""
MetricsProjection — truthful metrics with confidence labels.

Rule (Noah's law): every field is an actual measured value or explicitly None.
No fabricated estimates presented as fact. ETA is labeled with its confidence tier.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class MetricsProjection:
    """
    Immutable metrics snapshot, explicitly separated by scope.
    """
    # Scan scope (live totals)
    files_discovered_total: int
    files_discovered_fresh: int
    files_reused_from_prior_inventory: int
    dirs_scanned: int
    dirs_reused: int
    elapsed_s: float
    duplicate_groups_live: int

    # Phase scope (current phase only)
    current_phase_name: str
    current_phase_progress: str
    current_phase_rows_processed: int
    current_phase_total_units: Optional[int]
    current_phase_elapsed_s: float
    current_phase_started_at: Optional[float]
    current_phase_last_updated_at: Optional[float]
    current_file: str

    # Result scope (terminal/result summary)
    result_duplicate_files: int
    result_duplicate_groups: int
    result_rows_assembled: int
    result_reclaimable_bytes: int

    # Work Saved / reuse scope
    discovery_reuse_mode: str
    dirs_skipped_via_manifest: int
    prior_session_compatible: bool
    prior_session_rejected_reason: str
    time_saved_estimate: float

    # Throughput hints
    disk_read_bps: float
    rows_per_sec: float
    cache_hit_rate: float
    hash_cache_hits: int
    hash_cache_misses: int
    eta_seconds: Optional[float]
    eta_confidence: str

    @property
    def eta_label(self) -> str:
        if self.eta_seconds is None:
            return "—"
        from ..utils.formatting import fmt_duration
        return f"~{fmt_duration(self.eta_seconds)} ({self.eta_confidence})"

    @property
    def cache_hit_pct(self) -> str:
        if self.cache_hit_rate <= 0:
            return "—"
        return f"{self.cache_hit_rate * 100:.0f}%"


EMPTY_METRICS = MetricsProjection(
    files_discovered_total=0,
    files_discovered_fresh=0,
    files_reused_from_prior_inventory=0,
    dirs_scanned=0,
    dirs_reused=0,
    elapsed_s=0.0,
    duplicate_groups_live=0,
    current_phase_name="",
    current_phase_progress="",
    current_phase_rows_processed=0,
    current_phase_total_units=None,
    current_phase_elapsed_s=0.0,
    current_phase_started_at=None,
    current_phase_last_updated_at=None,
    current_file="",
    result_duplicate_files=0,
    result_duplicate_groups=0,
    result_rows_assembled=0,
    result_reclaimable_bytes=0,
    discovery_reuse_mode="none",
    dirs_skipped_via_manifest=0,
    prior_session_compatible=False,
    prior_session_rejected_reason="none",
    time_saved_estimate=0.0,
    disk_read_bps=0.0,
    rows_per_sec=0.0,
    cache_hit_rate=0.0,
    hash_cache_hits=0,
    hash_cache_misses=0,
    eta_seconds=None,
    eta_confidence="unknown",
)


def build_metrics_from_progress(progress) -> MetricsProjection:
    """
    Build a MetricsProjection from a ScanProgress object.
    Only populates fields that ScanProgress actually carries.
    """
    bps = getattr(progress, "bytes_per_second", None) or 0.0
    fps = getattr(progress, "files_per_second", None) or 0.0
    eta = getattr(progress, "estimated_remaining_seconds", None)
    eta_conf = "unknown"
    if eta is not None:
        elapsed = getattr(progress, "elapsed_seconds", 0.0) or 0.0
        if elapsed > 30:
            eta_conf = "medium"
        if elapsed > 120:
            eta_conf = "high"

    return MetricsProjection(
        files_discovered_total=getattr(progress, "files_found", 0),
        files_discovered_fresh=getattr(progress, "files_found", 0),
        files_reused_from_prior_inventory=0,
        dirs_scanned=getattr(progress, "dirs_scanned", 0) or 0,
        dirs_reused=getattr(progress, "dirs_reused", 0) or 0,
        elapsed_s=getattr(progress, "elapsed_seconds", 0.0) or 0.0,
        duplicate_groups_live=getattr(progress, "groups_found", 0),
        current_phase_name=getattr(progress, "phase", "") or "",
        current_phase_progress=(
            f"{getattr(progress, 'phase_completed_units', 0)} / "
            f"{getattr(progress, 'phase_total_units', '—') if getattr(progress, 'phase_total_units', None) is not None else '—'}"
        ),
        current_phase_rows_processed=getattr(progress, "phase_completed_units", 0),
        current_phase_total_units=getattr(progress, "phase_total_units", None),
        current_phase_elapsed_s=getattr(progress, "phase_elapsed_s", 0.0) or 0.0,
        current_phase_started_at=getattr(progress, "phase_started_at", None),
        current_phase_last_updated_at=getattr(progress, "phase_last_updated_at", None),
        current_file=getattr(progress, "current_file", "") or "",
        result_duplicate_files=0,
        result_duplicate_groups=0,
        result_rows_assembled=0,
        result_reclaimable_bytes=0,
        discovery_reuse_mode="none",
        dirs_skipped_via_manifest=0,
        prior_session_compatible=False,
        prior_session_rejected_reason="none",
        time_saved_estimate=0.0,
        disk_read_bps=bps,
        rows_per_sec=fps,
        cache_hit_rate=0.0,
        hash_cache_hits=0,
        hash_cache_misses=0,
        eta_seconds=eta,
        eta_confidence=eta_conf,
    )


def merge_metrics(
    base: MetricsProjection,
    files_discovered_total: Optional[int] = None,
    files_discovered_fresh: Optional[int] = None,
    files_reused_from_prior_inventory: Optional[int] = None,
    dirs_scanned: Optional[int] = None,
    dirs_reused: Optional[int] = None,
    duplicate_groups_live: Optional[int] = None,
    current_phase_name: Optional[str] = None,
    current_phase_progress: Optional[str] = None,
    current_phase_rows_processed: Optional[int] = None,
    current_phase_total_units: Optional[int] = None,
    current_phase_elapsed_s: Optional[float] = None,
    current_phase_started_at: Optional[float] = None,
    current_phase_last_updated_at: Optional[float] = None,
    current_file: Optional[str] = None,
    result_duplicate_files: Optional[int] = None,
    result_duplicate_groups: Optional[int] = None,
    result_rows_assembled: Optional[int] = None,
    result_reclaimable_bytes: Optional[int] = None,
    discovery_reuse_mode: Optional[str] = None,
    dirs_skipped_via_manifest: Optional[int] = None,
    prior_session_compatible: Optional[bool] = None,
    prior_session_rejected_reason: Optional[str] = None,
    disk_read_bps: Optional[float] = None,
    rows_per_sec: Optional[float] = None,
    cache_hit_rate: Optional[float] = None,
    hash_cache_hits: Optional[int] = None,
    hash_cache_misses: Optional[int] = None,
    eta_seconds: Optional[float] = None,
    eta_confidence: Optional[str] = None,
    time_saved_estimate: Optional[float] = None,
    elapsed_s: Optional[float] = None,
) -> MetricsProjection:
    """Return a new MetricsProjection with only the provided fields updated."""
    return MetricsProjection(
        files_discovered_total=files_discovered_total if files_discovered_total is not None else base.files_discovered_total,
        files_discovered_fresh=files_discovered_fresh if files_discovered_fresh is not None else base.files_discovered_fresh,
        files_reused_from_prior_inventory=(
            files_reused_from_prior_inventory
            if files_reused_from_prior_inventory is not None
            else base.files_reused_from_prior_inventory
        ),
        dirs_scanned=dirs_scanned if dirs_scanned is not None else base.dirs_scanned,
        dirs_reused=dirs_reused if dirs_reused is not None else base.dirs_reused,
        elapsed_s=elapsed_s if elapsed_s is not None else base.elapsed_s,
        duplicate_groups_live=duplicate_groups_live if duplicate_groups_live is not None else base.duplicate_groups_live,
        current_phase_name=current_phase_name if current_phase_name is not None else base.current_phase_name,
        current_phase_progress=current_phase_progress if current_phase_progress is not None else base.current_phase_progress,
        current_phase_rows_processed=(
            current_phase_rows_processed
            if current_phase_rows_processed is not None
            else base.current_phase_rows_processed
        ),
        current_phase_total_units=(
            current_phase_total_units
            if current_phase_total_units is not None
            else base.current_phase_total_units
        ),
        current_phase_elapsed_s=(
            current_phase_elapsed_s
            if current_phase_elapsed_s is not None
            else base.current_phase_elapsed_s
        ),
        current_phase_started_at=(
            current_phase_started_at
            if current_phase_started_at is not None
            else base.current_phase_started_at
        ),
        current_phase_last_updated_at=(
            current_phase_last_updated_at
            if current_phase_last_updated_at is not None
            else base.current_phase_last_updated_at
        ),
        current_file=current_file if current_file is not None else base.current_file,
        result_duplicate_files=(
            result_duplicate_files
            if result_duplicate_files is not None
            else base.result_duplicate_files
        ),
        result_duplicate_groups=(
            result_duplicate_groups
            if result_duplicate_groups is not None
            else base.result_duplicate_groups
        ),
        result_rows_assembled=(
            result_rows_assembled
            if result_rows_assembled is not None
            else base.result_rows_assembled
        ),
        result_reclaimable_bytes=(
            result_reclaimable_bytes
            if result_reclaimable_bytes is not None
            else base.result_reclaimable_bytes
        ),
        discovery_reuse_mode=(
            discovery_reuse_mode if discovery_reuse_mode is not None else base.discovery_reuse_mode
        ),
        dirs_skipped_via_manifest=(
            dirs_skipped_via_manifest
            if dirs_skipped_via_manifest is not None
            else base.dirs_skipped_via_manifest
        ),
        prior_session_compatible=(
            prior_session_compatible
            if prior_session_compatible is not None
            else base.prior_session_compatible
        ),
        prior_session_rejected_reason=(
            prior_session_rejected_reason
            if prior_session_rejected_reason is not None
            else base.prior_session_rejected_reason
        ),
        disk_read_bps=disk_read_bps if disk_read_bps is not None else base.disk_read_bps,
        rows_per_sec=rows_per_sec if rows_per_sec is not None else base.rows_per_sec,
        cache_hit_rate=cache_hit_rate if cache_hit_rate is not None else base.cache_hit_rate,
        hash_cache_hits=hash_cache_hits if hash_cache_hits is not None else base.hash_cache_hits,
        hash_cache_misses=hash_cache_misses if hash_cache_misses is not None else base.hash_cache_misses,
        eta_seconds=eta_seconds if eta_seconds is not None else base.eta_seconds,
        eta_confidence=eta_confidence or base.eta_confidence,
        time_saved_estimate=time_saved_estimate if time_saved_estimate is not None else base.time_saved_estimate,
    )
