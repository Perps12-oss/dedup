"""Mission page domain models (shared with ViewModels and adapters)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional


@dataclass(frozen=True)
class CapabilityInfo:
    name: str
    available: bool
    detail: str = ""


@dataclass(frozen=True)
class EngineStatus:
    hash_backend: str
    resume_available: bool
    schema_version: Any  # int or "—"


@dataclass(frozen=True)
class LastScanSummary:
    files_scanned: int
    duplicate_groups: int
    reclaimable_bytes: int
    duration_s: float


@dataclass(frozen=True)
class RecentSession:
    """One row in recent sessions list."""

    scan_id: str
    started_at: str
    roots: tuple[str, ...]
    files_scanned: int
    duplicates_found: int
    reclaimable_bytes: int
    status: str
    duration_s: float

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RecentSession:
        roots = d.get("roots") or []
        return cls(
            scan_id=str(d.get("scan_id", "")),
            started_at=str(d.get("started_at", "")),
            roots=tuple(str(x) for x in roots),
            files_scanned=int(d.get("files_scanned") or 0),
            duplicates_found=int(d.get("duplicates_found") or 0),
            reclaimable_bytes=int(d.get("reclaimable_bytes") or 0),
            status=str(d.get("status", "")),
            duration_s=float(d.get("duration_s") or 0),
        )


def recent_sessions_from_dicts(rows: List[dict[str, Any]]) -> List[RecentSession]:
    return [RecentSession.from_dict(r) for r in rows]
