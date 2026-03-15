"""Repositories for cross-session incremental discovery artifacts."""

from __future__ import annotations

import sqlite3
from typing import Dict, Iterable, Tuple


class DiscoveryDirectoryRepository:
    """Persist directory mtimes for subtree reuse checks."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def insert_batch(self, session_id: str, rows: Iterable[Tuple[str, int]]) -> int:
        prepared = [(session_id, str(dir_path), int(dir_mtime_ns)) for dir_path, dir_mtime_ns in rows]
        if not prepared:
            return 0
        self.conn.executemany(
            """
            INSERT OR REPLACE INTO discovery_dir_mtimes (
                session_id, dir_path, dir_mtime_ns
            ) VALUES (?, ?, ?)
            """,
            prepared,
        )
        self.conn.commit()
        return len(prepared)

    def get_dir_mtimes(self, session_id: str) -> Dict[str, int]:
        rows = self.conn.execute(
            """
            SELECT dir_path, dir_mtime_ns
            FROM discovery_dir_mtimes
            WHERE session_id = ?
            """,
            (session_id,),
        ).fetchall()
        return {str(row["dir_path"]): int(row["dir_mtime_ns"]) for row in rows}
