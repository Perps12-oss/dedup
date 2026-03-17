"""
DEDUP Engine Interfaces - Protocol definitions for dependency inversion.

These protocols define the boundaries between the engine and infrastructure/orchestration.
Implementations (adapters) live in infrastructure/adapters. The engine depends only
on these interfaces, not on concrete persistence or event bus types.
"""

from __future__ import annotations

from typing import Any, Dict, Iterator, List, Optional, Protocol

# Engine models used by protocols (no infrastructure imports)
from ..models import CheckpointInfo, FileMetadata, PhaseStatus, ScanPhase


class CheckpointStore(Protocol):
    """Storage for phase checkpoints (resumable scans)."""

    def get(self, session_id: str, phase_name: ScanPhase) -> Optional[CheckpointInfo]:
        """Load checkpoint for a session/phase. Returns None if missing."""
        ...

    def write(
        self,
        session_id: str,
        phase_name: ScanPhase,
        completed_units: int,
        total_units: Optional[int] = None,
        chunk_cursor: Optional[str] = None,
        status: PhaseStatus = PhaseStatus.RUNNING,
        metadata_json: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Persist checkpoint state. Raises on storage failure."""
        ...

    def upsert(self, checkpoint: CheckpointInfo) -> None:
        """Insert or replace a full checkpoint. Used by resume logic."""
        ...


class InventoryStore(Protocol):
    """Storage for discovered file inventory per session."""

    def add_files_batch(self, session_id: str, files: List[FileMetadata]) -> int:
        """Append a batch of files. Returns count written. Raises on failure."""
        ...

    def iter_by_session(self, session_id: str) -> Iterator[FileMetadata]:
        """Iterate over all stored files for a session."""
        ...


class SessionStore(Protocol):
    """Storage for scan session metadata and status."""

    def get(self, session_id: str) -> Optional[Any]:
        """Return session row or None. Type of return is implementation-defined."""
        ...

    def create(
        self,
        session_id: str,
        config_json: str,
        config_hash: str,
        root_fingerprint: Optional[str] = None,
        discovery_config_hash: Optional[str] = None,
        status: str = "running",
        current_phase: str = "discovery",
    ) -> None:
        """Create or replace session. Raises on failure."""
        ...

    def update_status(
        self,
        session_id: str,
        status: str,
        current_phase: Optional[str] = None,
        failure_reason: Optional[str] = None,
        metrics: Optional[Dict[str, Any]] = None,
        completed: bool = False,
    ) -> None:
        """Update session status. Raises on failure."""
        ...


class EventPublisher(Protocol):
    """Publish scan/phase events without depending on concrete event bus."""

    def publish(self, event_type: str, scan_id: str, payload: Dict[str, Any]) -> None:
        """Emit an event. Subscribers must not break the publisher; failures are logged."""
        ...
