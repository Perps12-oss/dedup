"""Repository for durable phase checkpoints."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import List, Optional

from ...engine.models import CheckpointInfo, PhaseStatus, ScanPhase


class CheckpointRepository:
    """CRUD access for phase checkpoints."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def get(self, session_id: str, phase_name: ScanPhase) -> Optional[CheckpointInfo]:
        row = self.conn.execute(
            """
            SELECT * FROM phase_checkpoints
            WHERE session_id = ? AND phase_name = ?
            """,
            (session_id, phase_name.value),
        ).fetchone()
        if not row:
            return None
        return CheckpointInfo(
            session_id=row["session_id"],
            phase_name=ScanPhase(row["phase_name"]),
            chunk_cursor=row["chunk_cursor"],
            completed_units=row["completed_units"],
            total_units=row["total_units"],
            status=PhaseStatus(row["status"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            metadata_json=json.loads(row["metadata_json"]) if row["metadata_json"] else {},
        )

    def upsert(self, checkpoint: CheckpointInfo) -> None:
        self.conn.execute(
            """
            INSERT INTO phase_checkpoints (
                session_id, phase_name, chunk_cursor, completed_units, total_units,
                status, updated_at, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id, phase_name) DO UPDATE SET
                chunk_cursor = excluded.chunk_cursor,
                completed_units = excluded.completed_units,
                total_units = excluded.total_units,
                status = excluded.status,
                updated_at = excluded.updated_at,
                metadata_json = excluded.metadata_json
            """,
            (
                checkpoint.session_id,
                checkpoint.phase_name.value,
                checkpoint.chunk_cursor,
                checkpoint.completed_units,
                checkpoint.total_units,
                checkpoint.status.value,
                checkpoint.updated_at.isoformat(),
                json.dumps(checkpoint.metadata_json),
            ),
        )
        self.conn.commit()

    def list_for_session(self, session_id: str) -> List[CheckpointInfo]:
        rows = self.conn.execute(
            """
            SELECT * FROM phase_checkpoints
            WHERE session_id = ?
            ORDER BY updated_at ASC
            """,
            (session_id,),
        ).fetchall()
        return [
            CheckpointInfo(
                session_id=row["session_id"],
                phase_name=ScanPhase(row["phase_name"]),
                chunk_cursor=row["chunk_cursor"],
                completed_units=row["completed_units"],
                total_units=row["total_units"],
                status=PhaseStatus(row["status"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
                metadata_json=json.loads(row["metadata_json"]) if row["metadata_json"] else {},
            )
            for row in rows
        ]
