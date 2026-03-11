"""
DEDUP Persistence - Data storage and retrieval.

Provides SQLite-based storage for:
- Scan history
- Hash cache (for faster re-scans)
- Settings
"""

from __future__ import annotations

import json
import sqlite3
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

from ..engine.models import ScanResult, FileMetadata


@dataclass
class Persistence:
    """Database persistence layer."""
    
    db_path: Path
    _connection: Optional[sqlite3.Connection] = None
    _lock: threading.Lock = None
    
    def __post_init__(self):
        if self._lock is None:
            self._lock = threading.Lock()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @property
    def checkpoint_dir(self) -> Path:
        """Directory for scan checkpoints (resume support)."""
        return self.db_path.parent / "checkpoints"

    def list_resumable_scan_ids(self) -> List[str]:
        """List scan_ids that have a checkpoint (can be resumed)."""
        try:
            cp_dir = self.checkpoint_dir
            if not cp_dir.exists():
                return []
            return [
                f.stem.replace("_checkpoint", "")
                for f in cp_dir.glob("*_checkpoint.json")
                if f.is_file()
            ]
        except Exception:
            return []
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get or create database connection."""
        if self._connection is None:
            self._connection = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._connection.row_factory = sqlite3.Row
        return self._connection
    
    def _init_db(self):
        """Initialize database schema."""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # Scan history table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS scan_history (
                    scan_id TEXT PRIMARY KEY,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    config TEXT NOT NULL,
                    result TEXT,
                    files_scanned INTEGER DEFAULT 0,
                    duplicates_found INTEGER DEFAULT 0,
                    reclaimable_bytes INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'in_progress'
                )
            """)
            
            # Hash cache table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS hash_cache (
                    path TEXT PRIMARY KEY,
                    size INTEGER NOT NULL,
                    mtime_ns INTEGER NOT NULL,
                    hash_partial TEXT,
                    hash_full TEXT,
                    cached_at REAL NOT NULL
                )
            """)
            
            # Deletion audit log
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS deletion_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scan_id TEXT NOT NULL,
                    deleted_at TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    policy TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    error_message TEXT
                )
            """)
            
            conn.commit()
    
    def save_scan(self, result: ScanResult) -> bool:
        """Save scan result to history."""
        try:
            with self._lock:
                conn = self._get_connection()
                cursor = conn.cursor()
                
                cursor.execute("""
                    INSERT OR REPLACE INTO scan_history
                    (scan_id, started_at, completed_at, config, result,
                     files_scanned, duplicates_found, reclaimable_bytes, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    result.scan_id,
                    result.started_at.isoformat(),
                    result.completed_at.isoformat() if result.completed_at else None,
                    json.dumps(result.config.to_dict()),
                    json.dumps(result.to_dict()),
                    result.files_scanned,
                    result.total_duplicates,
                    result.total_reclaimable_bytes,
                    'completed' if result.completed_at else 'in_progress',
                ))
                
                conn.commit()
                return True
        except sqlite3.Error:
            return False
    
    def get_scan(self, scan_id: str) -> Optional[ScanResult]:
        """Get scan result by ID."""
        try:
            with self._lock:
                conn = self._get_connection()
                cursor = conn.cursor()
                
                cursor.execute(
                    "SELECT result FROM scan_history WHERE scan_id = ?",
                    (scan_id,)
                )
                row = cursor.fetchone()
                
                if row and row['result']:
                    data = json.loads(row['result'])
                    return ScanResult.from_dict(data)
                return None
        except (sqlite3.Error, json.JSONDecodeError, KeyError):
            return None
    
    def list_scans(
        self,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """List scan history entries."""
        try:
            with self._lock:
                conn = self._get_connection()
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT scan_id, started_at, completed_at, config,
                           files_scanned, duplicates_found, reclaimable_bytes, status
                    FROM scan_history
                    ORDER BY started_at DESC
                    LIMIT ? OFFSET ?
                """, (limit, offset))
                
                rows = cursor.fetchall()
                out = []
                for row in rows:
                    r = dict(row)
                    roots = []
                    if r.get('config'):
                        try:
                            cfg = json.loads(r['config'])
                            roots = cfg.get('roots') or []
                        except (json.JSONDecodeError, TypeError):
                            pass
                    out.append({
                        "scan_id": r['scan_id'],
                        "started_at": r['started_at'],
                        "completed_at": r['completed_at'],
                        "files_scanned": r['files_scanned'],
                        "duplicates_found": r['duplicates_found'],
                        "reclaimable_bytes": r['reclaimable_bytes'],
                        "status": r['status'],
                        "roots": roots,
                    })
                return out
        except sqlite3.Error:
            return []
    
    def delete_scan(self, scan_id: str) -> bool:
        """Delete a scan from history."""
        try:
            with self._lock:
                conn = self._get_connection()
                cursor = conn.cursor()
                cursor.execute("DELETE FROM scan_history WHERE scan_id = ?", (scan_id,))
                conn.commit()
                return cursor.rowcount > 0
        except sqlite3.Error:
            return False
    
    def get_hash_cache(self, path: str) -> Optional[Dict[str, Any]]:
        """Get cached hash for a file."""
        try:
            with self._lock:
                conn = self._get_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM hash_cache WHERE path = ?",
                    (path,)
                )
                row = cursor.fetchone()
                
                if row:
                    return {
                        "path": row['path'],
                        "size": row['size'],
                        "mtime_ns": row['mtime_ns'],
                        "hash_partial": row['hash_partial'],
                        "hash_full": row['hash_full'],
                        "cached_at": row['cached_at'],
                    }
                return None
        except sqlite3.Error:
            return None
    
    def set_hash_cache(self, file: FileMetadata) -> bool:
        """Cache hash for a file."""
        try:
            with self._lock:
                conn = self._get_connection()
                cursor = conn.cursor()
                
                cursor.execute("""
                    INSERT OR REPLACE INTO hash_cache
                    (path, size, mtime_ns, hash_partial, hash_full, cached_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    file.path,
                    file.size,
                    file.mtime_ns,
                    file.hash_partial,
                    file.hash_full,
                    time.time(),
                ))
                
                conn.commit()
                return True
        except sqlite3.Error:
            return False
    
    def log_deletion(
        self,
        scan_id: str,
        file_path: str,
        policy: str,
        success: bool,
        error_message: Optional[str] = None
    ) -> bool:
        """Log a deletion operation."""
        try:
            with self._lock:
                conn = self._get_connection()
                cursor = conn.cursor()
                
                cursor.execute("""
                    INSERT INTO deletion_log
                    (scan_id, deleted_at, file_path, policy, success, error_message)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    scan_id,
                    datetime.now().isoformat(),
                    file_path,
                    policy,
                    1 if success else 0,
                    error_message,
                ))
                
                conn.commit()
                return True
        except sqlite3.Error:
            return False
    
    def cleanup_old_cache(self, max_age_days: int = 30) -> int:
        """Remove old hash cache entries."""
        try:
            cutoff = time.time() - (max_age_days * 24 * 60 * 60)
            
            with self._lock:
                conn = self._get_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "DELETE FROM hash_cache WHERE cached_at < ?",
                    (cutoff,)
                )
                conn.commit()
                return cursor.rowcount
        except sqlite3.Error:
            return 0
    
    def close(self):
        """Close database connection."""
        with self._lock:
            if self._connection:
                self._connection.close()
                self._connection = None


class ScanStore:
    """High-level interface for scan storage."""
    
    def __init__(self, persistence: Persistence):
        self.persistence = persistence
    
    def save(self, result: ScanResult) -> bool:
        """Save scan result."""
        return self.persistence.save_scan(result)
    
    def load(self, scan_id: str) -> Optional[ScanResult]:
        """Load scan result."""
        return self.persistence.get_scan(scan_id)
    
    def list_recent(self, limit: int = 10) -> List[Dict[str, Any]]:
        """List recent scans."""
        return self.persistence.list_scans(limit=limit)
    
    def delete(self, scan_id: str) -> bool:
        """Delete a scan."""
        return self.persistence.delete_scan(scan_id)


def get_default_persistence() -> Persistence:
    """Get default persistence instance."""
    if sys.platform == 'win32':
        data_dir = Path.home() / 'AppData' / 'Local' / 'dedup'
    elif sys.platform == 'darwin':
        data_dir = Path.home() / 'Library' / 'Application Support' / 'dedup'
    else:
        data_dir = Path.home() / '.local' / 'share' / 'dedup'
    
    return Persistence(db_path=data_dir / 'dedup.db')
