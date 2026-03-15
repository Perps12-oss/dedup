"""
MissionVM — state for the Mission page.

Owns:
  - Last session projection snapshot (engine health, resumability)
  - Coordinator-sourced summaries (last scan, capabilities, recent folders)
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..projections.session_projection import SessionProjection, EMPTY_SESSION
from ..projections.history_projection import HistoryProjection, EMPTY_HISTORY


@dataclass
class CapabilityInfo:
    name: str
    available: bool
    detail: str = ""


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

    def refresh_from_coordinator(self, coordinator) -> None:
        """Pull fresh data from the coordinator. Safe to call on UI thread."""
        # Recent folders
        try:
            self.recent_folders = list(coordinator.get_recent_folders() or [])[:10]
        except Exception:
            self.recent_folders = []

        # Last scan from history
        try:
            hist = coordinator.get_history(limit=1)
            if hist:
                d = hist[0]
                self.last_scan_root = str((d.get("roots") or [""])[0])
                ts = str(d.get("started_at", ""))[:10]
                self.last_scan_date = ts
        except Exception:
            pass

        # Capabilities
        self.capabilities = _detect_capabilities()

    @property
    def engine_health_label(self) -> str:
        return self.session.engine_health

    @property
    def has_resumable(self) -> bool:
        return self.history.resumable_count > 0


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

    # Trash support
    try:
        import send2trash  # noqa: F401
        caps.append(CapabilityInfo("Trash protection", True, "System trash supported"))
    except ImportError:
        caps.append(CapabilityInfo("Trash protection", False, "pip install send2trash"))

    # Thumbnails
    try:
        from PIL import Image  # noqa: F401
        caps.append(CapabilityInfo("Thumbnails", True, "Image preview enabled"))
    except ImportError:
        caps.append(CapabilityInfo("Thumbnails", False, "pip install Pillow"))

    # DnD
    try:
        import tkinterdnd2  # noqa: F401
        caps.append(CapabilityInfo("Drag-and-drop", True, "Folder drop enabled"))
    except ImportError:
        caps.append(CapabilityInfo("Drag-and-drop", False, "Optional"))

    # Persistence
    caps.append(CapabilityInfo("Persistence", True, "SQLite-backed durable pipeline"))
    caps.append(CapabilityInfo("Audit logging", True, "Deletion audit trail active"))

    return caps
