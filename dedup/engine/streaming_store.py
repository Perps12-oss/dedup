"""
DEDUP Streaming Store - Temp SQLite storage for bounded-memory discovery.

Used by StreamingScanPipeline: discovery writes (path, size, mtime_ns, inode)
to SQLite instead of accumulating in RAM. After discovery, only size groups
with 2+ files are loaded for hashing - unique sizes never enter memory.

Design: true bounded memory for 1M+ file scans.
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from typing import List, Optional

from .models import FileMetadata


class StreamingStore:
    """
    Temporary SQLite store for discovered file metadata.

    Only stores path, size, mtime_ns, inode - no hash data.
    Enables streaming discovery with bounded memory.
    """

    def __init__(self, db_path: Optional[Path] = None):
        """
        Create or open a streaming store.

        Args:
            db_path: Path for SQLite DB. If None, uses a temp file.
        """
        if db_path is not None:
            self._path = Path(db_path)
        else:
            fd, path = tempfile.mkstemp(suffix=".db", prefix="dedup_streaming_")
            import os
            os.close(fd)
            self._path = Path(path)
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _init_db(self) -> None:
        """Create schema."""
        self._conn = sqlite3.connect(str(self._path))
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS files (
                path TEXT PRIMARY KEY,
                size INTEGER NOT NULL,
                mtime_ns INTEGER NOT NULL,
                inode INTEGER
            )
        """)
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_size ON files(size)")
        self._conn.commit()

    def insert_batch(self, files: List[FileMetadata]) -> None:
        """Insert a batch of files. Uses replace for idempotency."""
        if not files:
            return
        rows = [(f.path, f.size, f.mtime_ns, f.inode) for f in files]
        self._conn.executemany(
            "INSERT OR REPLACE INTO files (path, size, mtime_ns, inode) VALUES (?, ?, ?, ?)",
            rows,
        )
        self._conn.commit()

    def get_sizes_with_duplicates(self) -> List[int]:
        """Return sizes that have 2 or more files (potential duplicates)."""
        cursor = self._conn.execute("""
            SELECT size FROM files
            GROUP BY size
            HAVING COUNT(*) >= 2
            ORDER BY size
        """)
        return [row[0] for row in cursor.fetchall()]

    def get_files_by_size(self, size: int) -> List[FileMetadata]:
        """Load FileMetadata for all files with the given size."""
        cursor = self._conn.execute(
            "SELECT path, size, mtime_ns, inode FROM files WHERE size = ?",
            (size,),
        )
        return [
            FileMetadata(
                path=row[0],
                size=row[1],
                mtime_ns=row[2],
                inode=row[3],
            )
            for row in cursor.fetchall()
        ]

    def get_file_count(self) -> int:
        """Total number of files stored."""
        cursor = self._conn.execute("SELECT COUNT(*) FROM files")
        return cursor.fetchone()[0]

    def close(self) -> None:
        """Close connection and remove temp file if we created it."""
        if self._conn:
            self._conn.close()
            self._conn = None
        # Only unlink if it was auto-created (in system temp dir)
        try:
            if "dedup_streaming_" in self._path.name:
                self._path.unlink(missing_ok=True)
        except OSError:
            pass

    def __enter__(self) -> "StreamingStore":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
