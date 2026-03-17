"""
MissionVM — state for the Mission page.

Owns:
  - Last session projection snapshot (engine health, resumability)
  - Coordinator-sourced summaries (last scan, capabilities, recent folders)
  - Engine status and last_scan / recent_sessions for the Mission page UI.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..projections.session_projection import SessionProjection, EMPTY_SESSION
from ..projections.history_projection import (
    HistoryProjection, EMPTY_HISTORY, build_history_from_coordinator,
)


@dataclass
class CapabilityInfo:
    name: str
    available: bool
    detail: str = ""


@dataclass
class EngineStatus:
    """Engine status summary for the Mission page engine card."""
    hash_backend: str
    resume_available: bool
    schema_version: Any  # int or "—"


@dataclass
class LastScanSummary:
    """Last scan summary for the Mission page last-scan card."""
    files_scanned: int
    duplicate_groups: int
    reclaimable_bytes: int
    duration_s: float


@dataclass
class MissionVM:
    """
    View-model for the Mission page.
    Refreshed on demand (page focus, post-scan) rather than tick-driven.
    """
    # --- Projection snapshots ---
    session:  SessionProjection = field(default_factory=lambda: EMPTY_SESSION)
    history:  HistoryProjection = field(default_factory=lambda: EMPTY_HISTORY)

    # --- Coordinator-sourced data ---
    recent_folders:  List[str]           = field(default_factory=list)
    capabilities:    List[CapabilityInfo] = field(default_factory=list)
    last_scan_root:  str                 = ""
    last_scan_date:  str                 = ""
    engine_warnings: List[str]           = field(default_factory=list)

    # --- Mission page UI contract (populated by refresh_from_coordinator or refresh_from_mission_state) ---
    engine_status:   EngineStatus        = field(default_factory=lambda: EngineStatus("—", False, "—"))
    last_scan:       Optional[LastScanSummary] = None
    recent_sessions: List[Dict[str, Any]] = field(default_factory=list)
    resumable_scan_ids: List[str]         = field(default_factory=list)

    def refresh_from_mission_state(self, state: Any) -> None:
        """Update VM from UIStateStore (mission slice). Use when page is fed from store."""
        mission = getattr(state, "mission", None)
        scan = getattr(state, "scan", None)
        if mission is None:
            return
        # last_scan
        ls = getattr(mission, "last_scan", None)
        self.last_scan = LastScanSummary(
            files_scanned=getattr(ls, "files_scanned", 0),
            duplicate_groups=getattr(ls, "duplicate_groups", 0),
            reclaimable_bytes=getattr(ls, "reclaimable_bytes", 0),
            duration_s=getattr(ls, "duration_s", 0.0),
        ) if ls else None
        self.recent_sessions = list(getattr(mission, "recent_sessions", ()))
        self.recent_folders = list(getattr(mission, "recent_folders", ()))
        self.resumable_scan_ids = list(getattr(mission, "resumable_scan_ids", ()))
        # capabilities and engine_status (still local)
        self.capabilities = _detect_capabilities()
        schema = "—"
        if scan and getattr(scan, "session", None):
            schema = getattr(scan.session, "schema_version", None) or "—"
        self.engine_status = EngineStatus(
            hash_backend=_hash_backend_from_caps(self.capabilities),
            resume_available=len(self.resumable_scan_ids) > 0,
            schema_version=schema,
        )

    def refresh_from_coordinator(self, coordinator) -> None:
        """Pull fresh data from the coordinator. Safe to call on UI thread."""
        # Recent folders
        try:
            self.recent_folders = list(coordinator.get_recent_folders() or [])[:10]
        except Exception:
            self.recent_folders = []

        # History (sessions + resumable)
        try:
            self.history = build_history_from_coordinator(coordinator, limit=50)
        except Exception:
            self.history = EMPTY_HISTORY

        # Last scan from first session
        try:
            raw = coordinator.get_history(limit=1)
            if raw:
                d = raw[0]
                self.last_scan_root = str((d.get("roots") or [""])[0])
                ts = str(d.get("started_at", ""))[:10]
                self.last_scan_date = ts
                self.last_scan = LastScanSummary(
                    files_scanned=int(d.get("files_scanned") or 0),
                    duplicate_groups=int(d.get("duplicates_found") or 0),
                    reclaimable_bytes=int(d.get("reclaimable_bytes") or 0),
                    duration_s=float(d.get("duration_s") or 0),
                )
            else:
                self.last_scan = None
        except Exception:
            self.last_scan = None

        # Recent sessions as list of dicts for the table
        resumable_ids = set(coordinator.get_resumable_scan_ids() or [])
        self.recent_sessions = []
        for s in self.history.sessions:
            self.recent_sessions.append({
                "scan_id": s.scan_id,
                "started_at": s.started_at,
                "roots": list(s.roots),
                "files_scanned": s.files_scanned,
                "duplicates_found": s.duplicates_found,
                "reclaimable_bytes": s.reclaimable_bytes,
                "status": s.status,
                "duration_s": s.duration_s,
            })

        # Capabilities
        self.capabilities = _detect_capabilities()

        # Engine status
        hash_backend = "—"
        for c in self.capabilities:
            if c.name == "xxhash" and c.available:
                hash_backend = "xxhash64"
                break
            if c.name == "blake3" and c.available:
                hash_backend = "blake3"
        if hash_backend == "—" and self.capabilities:
            hash_backend = "stdlib"
        schema = self.session.schema_version if self.session.schema_version else "—"
        self.engine_status = EngineStatus(
            hash_backend=hash_backend,
            resume_available=self.history.resumable_count > 0,
            schema_version=schema,
        )

    @property
    def engine_health_label(self) -> str:
        return self.session.engine_health

    @property
    def has_resumable(self) -> bool:
        return self.history.resumable_count > 0

    def capabilities_by_name(self) -> Dict[str, bool]:
        """Dict of capability name -> available for Mission page capability checks."""
        return {c.name: c.available for c in self.capabilities}


def _hash_backend_from_caps(caps: List[CapabilityInfo]) -> str:
    for c in caps:
        if c.name == "xxhash" and c.available:
            return "xxhash64"
        if c.name == "blake3" and c.available:
            return "blake3"
    return "stdlib" if caps else "—"


def _detect_capabilities() -> List[CapabilityInfo]:
    caps = []

    # Hash backend
    try:
        import xxhash  # noqa: F401
        caps.append(CapabilityInfo("xxhash", True, "Fast non-cryptographic hashing"))
    except ImportError:
        caps.append(CapabilityInfo("xxhash", False, "pip install xxhash"))

    try:
        import blake3  # noqa: F401
        caps.append(CapabilityInfo("blake3", True, "High-security hashing"))
    except ImportError:
        caps.append(CapabilityInfo("blake3", False, "Optional"))

    # Trash support — key must match page's _cap_vars key "send2trash"
    try:
        import send2trash  # noqa: F401
        caps.append(CapabilityInfo("send2trash", True, "System trash supported"))
    except ImportError:
        caps.append(CapabilityInfo("send2trash", False, "pip install send2trash"))

    # Thumbnails — key must match page's _cap_vars key "pillow"
    try:
        from PIL import Image  # noqa: F401
        caps.append(CapabilityInfo("pillow", True, "Image preview enabled"))
    except ImportError:
        caps.append(CapabilityInfo("pillow", False, "pip install Pillow"))

    # DnD
    try:
        import tkinterdnd2  # noqa: F401
        caps.append(CapabilityInfo("tkdnd", True, "Folder drop enabled"))
    except ImportError:
        caps.append(CapabilityInfo("tkdnd", False, "Optional"))

    # Built-in capabilities — keys match page's _cap_vars
    caps.append(CapabilityInfo("durable", True, "SQLite-backed durable pipeline"))
    caps.append(CapabilityInfo("audit", True, "Deletion audit trail active"))
    caps.append(CapabilityInfo("revalidation", True, "Pre-delete revalidation"))

    return caps
