"""Repository for durable discovery inventory rows."""

from __future__ import annotations

import sqlite3
import os
from typing import Dict, Iterable, Iterator, List, Optional

from ...engine.models import FileMetadata, FileRecord


class InventoryRepository:
    """Read and write discovery inventory rows."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def insert_batch(self, session_id: str, rows: Iterable[FileRecord | FileMetadata | Dict[str, object]]) -> int:
        prepared: List[tuple] = []
        for row in rows:
            if isinstance(row, FileMetadata):
                record = FileRecord.from_file_metadata(row)
            elif isinstance(row, FileRecord):
                record = row
            else:
                record = FileRecord(
                    path=str(row["path"]),
                    size_bytes=int(row["size_bytes"]),
                    mtime_ns=int(row["mtime_ns"]),
                    inode=int(row["inode"]) if row.get("inode") is not None else None,
                    device=str(row["device"]) if row.get("device") is not None else None,
                    extension=str(row["extension"]) if row.get("extension") is not None else None,
                    media_kind=str(row["media_kind"]) if row.get("media_kind") is not None else None,
                    discovery_status=str(row.get("discovery_status", "discovered")),
                )

            prepared.append(
                (
                    session_id,
                    record.path,
                    record.size_bytes,
                    record.mtime_ns,
                    str(record.inode) if record.inode is not None else None,
                    record.device,
                    record.extension,
                    record.media_kind,
                    record.discovery_status,
                )
            )

        if not prepared:
            return 0

        self.conn.executemany(
            """
            INSERT OR REPLACE INTO inventory_files (
                session_id, path, size_bytes, mtime_ns, inode, device,
                extension, media_kind, discovery_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            prepared,
        )
        self.conn.commit()
        return len(prepared)

    def count(self, session_id: str) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) AS count FROM inventory_files WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return int(row["count"]) if row else 0

    def iter_by_session(self, session_id: str, offset: int = 0, limit: Optional[int] = None) -> Iterator[FileMetadata]:
        sql = """
            SELECT path, size_bytes, mtime_ns, inode
            FROM inventory_files
            WHERE session_id = ?
            ORDER BY file_id ASC
        """
        params: List[object] = [session_id]
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])

        rows = self.conn.execute(sql, tuple(params)).fetchall()
        for row in rows:
            yield FileMetadata(
                path=row["path"],
                size=row["size_bytes"],
                mtime_ns=row["mtime_ns"],
                inode=int(row["inode"]) if row["inode"] is not None else None,
            )

    def iter_under_directory(self, session_id: str, dir_path: str) -> Iterator[FileMetadata]:
        norm = os.path.normpath(dir_path)
        slash = norm.replace("\\", "/")
        backslash = norm.replace("/", "\\")
        eq1 = slash
        eq2 = backslash
        p1 = f"{slash}/%"
        p2 = f"{backslash}\\%"
        p3 = f"{slash}\\%"
        p4 = f"{backslash}/%"
        rows = self.conn.execute(
            """
            SELECT path, size_bytes, mtime_ns, inode
            FROM inventory_files
            WHERE session_id = ?
              AND (
                    path = ?
                 OR path = ?
                 OR path LIKE ?
                 OR path LIKE ?
                 OR path LIKE ?
                 OR path LIKE ?
              )
            ORDER BY file_id ASC
            """,
            (session_id, eq1, eq2, p1, p2, p3, p4),
        ).fetchall()
        for row in rows:
            yield FileMetadata(
                path=row["path"],
                size=row["size_bytes"],
                mtime_ns=row["mtime_ns"],
                inode=int(row["inode"]) if row["inode"] is not None else None,
            )

    def iter_by_session_and_size(self, session_id: str) -> Iterator[tuple[int, FileMetadata]]:
        rows = self.conn.execute(
            """
            SELECT size_bytes, path, mtime_ns, inode
            FROM inventory_files
            WHERE session_id = ?
            ORDER BY size_bytes ASC, file_id ASC
            """,
            (session_id,),
        ).fetchall()
        for row in rows:
            yield (
                row["size_bytes"],
                FileMetadata(
                    path=row["path"],
                    size=row["size_bytes"],
                    mtime_ns=row["mtime_ns"],
                    inode=int(row["inode"]) if row["inode"] is not None else None,
                ),
            )

    def get_file_id(self, session_id: str, path: str) -> Optional[int]:
        row = self.conn.execute(
            """
            SELECT file_id FROM inventory_files
            WHERE session_id = ? AND path = ?
            """,
            (session_id, path),
        ).fetchone()
        return int(row["file_id"]) if row else None

    def get_metadata_by_id(self, session_id: str, file_id: int) -> Optional[FileMetadata]:
        row = self.conn.execute(
            """
            SELECT path, size_bytes, mtime_ns, inode
            FROM inventory_files
            WHERE session_id = ? AND file_id = ?
            """,
            (session_id, file_id),
        ).fetchone()
        if not row:
            return None
        return FileMetadata(
            path=row["path"],
            size=row["size_bytes"],
            mtime_ns=row["mtime_ns"],
            inode=int(row["inode"]) if row["inode"] is not None else None,
        )

    def load_metadata_for_file_ids(
        self, session_id: str, file_ids: List[int]
    ) -> List[FileMetadata]:
        """Load FileMetadata for given file_ids in one query. Order not preserved."""
        if not file_ids:
            return []
        placeholders = ",".join("?" * len(file_ids))
        rows = self.conn.execute(
            f"""
            SELECT path, size_bytes, mtime_ns, inode
            FROM inventory_files
            WHERE session_id = ? AND file_id IN ({placeholders})
            """,
            [session_id] + file_ids,
        ).fetchall()
        return [
            FileMetadata(
                path=row["path"],
                size=row["size_bytes"],
                mtime_ns=row["mtime_ns"],
                inode=int(row["inode"]) if row["inode"] is not None else None,
            )
            for row in rows
        ]
