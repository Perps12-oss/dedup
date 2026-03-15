"""Repositories for durable scan session state."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional


class SessionRepository:
    """CRUD access for durable scan sessions."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(
        self,
        session_id: str,
        config_json: str,
        config_hash: str,
        root_fingerprint: Optional[str] = None,
        status: str = "pending",
        current_phase: str = "discovery",
    ) -> None:
        now = datetime.now().isoformat()
        self.conn.execute(
            """
            INSERT OR REPLACE INTO scan_sessions (
                session_id, created_at, updated_at, status, current_phase,
                config_json, config_hash, root_fingerprint, started_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                now,
                now,
                status,
                current_phase,
                config_json,
                config_hash,
                root_fingerprint,
                now,
            ),
        )
        self.conn.commit()

    def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        row = self.conn.execute(
            "SELECT * FROM scan_sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return dict(row) if row else None

    def update_status(
        self,
        session_id: str,
        status: str,
        current_phase: Optional[str] = None,
        failure_reason: Optional[str] = None,
        metrics: Optional[Dict[str, Any]] = None,
        completed: bool = False,
    ) -> None:
        now = datetime.now().isoformat()
        row = self.get(session_id)
        if not row:
            return
        self.conn.execute(
            """
            UPDATE scan_sessions
            SET updated_at = ?,
                status = ?,
                current_phase = ?,
                failure_reason = ?,
                completed_at = ?,
                metrics_json = ?
            WHERE session_id = ?
            """,
            (
                now,
                status,
                current_phase or row["current_phase"],
                failure_reason,
                now if completed else row["completed_at"],
                json.dumps(metrics) if metrics is not None else row["metrics_json"],
                session_id,
            ),
        )
        self.conn.commit()

    def list_by_status(self, status: str) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM scan_sessions WHERE status = ? ORDER BY updated_at DESC",
            (status,),
        ).fetchall()
        return [dict(row) for row in rows]
