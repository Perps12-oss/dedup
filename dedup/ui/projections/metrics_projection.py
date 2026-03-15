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
    Immutable metrics snapshot. Replaced on every throttled flush.
    Only quantities we actually measured are non-None.
    """
    files_scanned: int
    files_skipped: int
    candidates: int
    potential_duplicates: int
    duplicate_groups: int
    reclaimable_bytes: int
    disk_read_bps: float          # bytes/sec measured, 0.0 if unavailable
    rows_per_sec: float           # pipeline throughput
    cache_hit_rate: float         # 0.0 – 1.0
    eta_seconds: Optional[float]  # None = unknown
    eta_confidence: str           # "high" | "medium" | "low" | "unknown"
    time_saved_estimate: float    # seconds saved by reuse (0.0 if no reuse)
    elapsed_s: float

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
    files_scanned=0,
    files_skipped=0,
    candidates=0,
    potential_duplicates=0,
    duplicate_groups=0,
    reclaimable_bytes=0,
    disk_read_bps=0.0,
    rows_per_sec=0.0,
    cache_hit_rate=0.0,
    eta_seconds=None,
    eta_confidence="unknown",
    time_saved_estimate=0.0,
    elapsed_s=0.0,
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
        files_scanned=getattr(progress, "files_found", 0),
        files_skipped=0,
        candidates=0,
        potential_duplicates=getattr(progress, "duplicates_found", 0),
        duplicate_groups=getattr(progress, "groups_found", 0),
        reclaimable_bytes=0,
        disk_read_bps=bps,
        rows_per_sec=fps,
        cache_hit_rate=0.0,
        eta_seconds=eta,
        eta_confidence=eta_conf,
        time_saved_estimate=0.0,
        elapsed_s=getattr(progress, "elapsed_seconds", 0.0) or 0.0,
    )


def merge_metrics(
    base: MetricsProjection,
    files_scanned: Optional[int] = None,
    files_skipped: Optional[int] = None,
    candidates: Optional[int] = None,
    potential_duplicates: Optional[int] = None,
    duplicate_groups: Optional[int] = None,
    reclaimable_bytes: Optional[int] = None,
    disk_read_bps: Optional[float] = None,
    rows_per_sec: Optional[float] = None,
    cache_hit_rate: Optional[float] = None,
    eta_seconds: Optional[float] = None,
    eta_confidence: Optional[str] = None,
    time_saved_estimate: Optional[float] = None,
    elapsed_s: Optional[float] = None,
) -> MetricsProjection:
    """Return a new MetricsProjection with only the provided fields updated."""
    return MetricsProjection(
        files_scanned=files_scanned if files_scanned is not None else base.files_scanned,
        files_skipped=files_skipped if files_skipped is not None else base.files_skipped,
        candidates=candidates if candidates is not None else base.candidates,
        potential_duplicates=potential_duplicates if potential_duplicates is not None else base.potential_duplicates,
        duplicate_groups=duplicate_groups if duplicate_groups is not None else base.duplicate_groups,
        reclaimable_bytes=reclaimable_bytes if reclaimable_bytes is not None else base.reclaimable_bytes,
        disk_read_bps=disk_read_bps if disk_read_bps is not None else base.disk_read_bps,
        rows_per_sec=rows_per_sec if rows_per_sec is not None else base.rows_per_sec,
        cache_hit_rate=cache_hit_rate if cache_hit_rate is not None else base.cache_hit_rate,
        eta_seconds=eta_seconds if eta_seconds is not None else base.eta_seconds,
        eta_confidence=eta_confidence or base.eta_confidence,
        time_saved_estimate=time_saved_estimate if time_saved_estimate is not None else base.time_saved_estimate,
        elapsed_s=elapsed_s if elapsed_s is not None else base.elapsed_s,
    )
