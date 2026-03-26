"""
HistoryProjection — normalized session summaries for the History page.

Consumed by: HistoryPage session table, session detail panel, History summary metrics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Tuple


@dataclass(frozen=True)
class HistorySessionProjection:
    """Immutable per-session summary row."""

    scan_id: str
    started_at: str
    status: str  # completed | failed | interrupted | cancelled | running
    files_scanned: int
    duplicates_found: int
    reclaimable_bytes: int
    duration_s: float
    roots: Tuple[str, ...]
    config_hash: str
    resume_outcome: str  # safe_resume | rebuild_phase | restart_required | none
    resume_reason: str
    warning_count: int
    is_resumable: bool
    phase_summary: str  # "5/5 phases completed" etc.
    deletion_verification_summary: Dict[str, int] = field(default_factory=dict)
    benchmark_summary: Dict[str, Any] = field(default_factory=dict)

    @property
    def roots_display(self) -> str:
        if not self.roots:
            return "—"
        names = [Path(r).name or r for r in self.roots[:2]]
        result = ", ".join(names)
        if len(self.roots) > 2:
            result += f" +{len(self.roots) - 2}"
        return result

    @property
    def status_variant(self) -> str:
        return {
            "completed": "positive",
            "failed": "danger",
            "interrupted": "warning",
            "cancelled": "warning",
            "running": "accent",
        }.get(self.status, "neutral")

    @property
    def resume_variant(self) -> str:
        if not self.is_resumable:
            return "neutral"
        return "safe_resume" if self.resume_outcome == "safe_resume" else "warning"


@dataclass(frozen=True)
class HistoryProjection:
    """Full history page projection: sessions + aggregate stats."""

    sessions: Tuple[HistorySessionProjection, ...]
    total_scans: int
    avg_duration_s: float
    avg_reclaim_bytes: int
    resumable_count: int
    failed_count: int
    resume_success_rate: float  # 0.0 – 1.0

    @property
    def resumable_pct(self) -> str:
        if self.total_scans == 0:
            return "—"
        return f"{100 * self.resumable_count / self.total_scans:.0f}%"


EMPTY_HISTORY = HistoryProjection(
    sessions=(),
    total_scans=0,
    avg_duration_s=0.0,
    avg_reclaim_bytes=0,
    resumable_count=0,
    failed_count=0,
    resume_success_rate=0.0,
)


def build_history_from_coordinator(
    coordinator,
    limit: int = 200,
) -> HistoryProjection:
    """
    Query history from the coordinator (or any object with ``get_history`` /
    ``get_resumable_scan_ids``, e.g. ``HistoryApplicationService``) and build a HistoryProjection.
    Designed to be called from the UI thread on demand (not in the hot path).
    """
    try:
        history: List[Dict[str, Any]] = coordinator.get_history(limit=limit) or []
    except Exception:
        history = []

    try:
        resumable_ids: set = set(coordinator.get_resumable_scan_ids() or [])
    except Exception:
        resumable_ids = set()

    sessions = []
    total_dur = 0.0
    total_rec = 0
    failed = 0

    for d in history:
        scan_id = d.get("scan_id", "")
        status = d.get("status", "unknown")
        is_res = scan_id in resumable_ids
        dur = float(d.get("duration_s", 0) or 0)
        rec = int(d.get("reclaimable_bytes", 0) or 0)
        roots_raw = d.get("roots") or []
        roots = tuple(str(r) for r in roots_raw)

        total_dur += dur
        total_rec += rec
        if status == "failed":
            failed += 1

        sessions.append(
            HistorySessionProjection(
                scan_id=scan_id,
                started_at=str(d.get("started_at", "—"))[:19].replace("T", " "),
                status=status,
                files_scanned=int(d.get("files_scanned", 0) or 0),
                duplicates_found=int(d.get("duplicates_found", 0) or 0),
                reclaimable_bytes=rec,
                duration_s=dur,
                roots=roots,
                config_hash=str(d.get("config_hash", "") or ""),
                resume_outcome="safe_resume" if is_res else "none",
                resume_reason="",
                warning_count=int(d.get("warning_count", 0) or 0),
                is_resumable=is_res,
                phase_summary="",
                deletion_verification_summary=dict(d.get("deletion_verification_summary") or {}),
                benchmark_summary=dict(d.get("benchmark_summary") or {}),
            )
        )

    n = len(sessions)
    return HistoryProjection(
        sessions=tuple(sessions),
        total_scans=n,
        avg_duration_s=total_dur / n if n else 0.0,
        avg_reclaim_bytes=total_rec // n if n else 0,
        resumable_count=len(resumable_ids),
        failed_count=failed,
        resume_success_rate=len(resumable_ids) / max(1, n),
    )
