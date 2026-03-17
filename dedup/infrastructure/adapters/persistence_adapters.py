"""
Persistence adapters - Implement engine interfaces by delegating to Persistence.

These adapters wrap the existing Persistence instance so the engine can depend
on CheckpointStore, InventoryStore, and SessionStore protocols without
depending on concrete repository types.
"""

from __future__ import annotations

from typing import Any, Dict, Iterator, List, Optional

from ...engine.models import (
    CheckpointInfo,
    FileMetadata,
    PhaseStatus,
    ScanPhase,
)
from ..persistence import Persistence


class CheckpointStoreAdapter:
    """Implements CheckpointStore by delegating to Persistence."""

    def __init__(self, persistence: Persistence) -> None:
        self._persistence = persistence

    def get(self, session_id: str, phase_name: ScanPhase) -> Optional[CheckpointInfo]:
        return self._persistence.checkpoint_repo.get(session_id, phase_name)

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
        self._persistence.shadow_write_checkpoint(
            session_id=session_id,
            phase_name=phase_name,
            completed_units=completed_units,
            total_units=total_units,
            chunk_cursor=chunk_cursor,
            status=status,
            metadata_json=metadata_json,
        )

    def upsert(self, checkpoint: CheckpointInfo) -> None:
        self._persistence.checkpoint_repo.upsert(checkpoint)


class InventoryStoreAdapter:
    """Implements InventoryStore by delegating to Persistence."""

    def __init__(self, persistence: Persistence) -> None:
        self._persistence = persistence

    def add_files_batch(self, session_id: str, files: List[FileMetadata]) -> int:
        return self._persistence.shadow_write_inventory(session_id, files)

    def iter_by_session(self, session_id: str) -> Iterator[FileMetadata]:
        return self._persistence.inventory_repo.iter_by_session(session_id)


class SessionStoreAdapter:
    """Implements SessionStore by delegating to Persistence."""

    def __init__(self, persistence: Persistence) -> None:
        self._persistence = persistence

    def get(self, session_id: str) -> Optional[Any]:
        return self._persistence.session_repo.get(session_id)

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
        self._persistence.shadow_write_session(
            session_id=session_id,
            config_json=config_json,
            config_hash=config_hash,
            root_fingerprint=root_fingerprint,
            discovery_config_hash=discovery_config_hash,
            status=status,
            current_phase=current_phase,
        )

    def update_status(
        self,
        session_id: str,
        status: str,
        current_phase: Optional[str] = None,
        failure_reason: Optional[str] = None,
        metrics: Optional[Dict[str, Any]] = None,
        completed: bool = False,
    ) -> None:
        self._persistence.shadow_update_session(
            session_id=session_id,
            status=status,
            current_phase=current_phase,
            failure_reason=failure_reason,
            metrics=metrics,
            completed=completed,
        )
