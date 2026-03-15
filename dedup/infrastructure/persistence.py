"""
DEDUP Persistence - Data storage and retrieval.

Provides SQLite-based storage for:
- Scan history
- Hash cache (for faster re-scans)
- Settings
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

from ..engine.models import (
    CheckpointInfo,
    FileMetadata,
    FileRecord,
    PhaseStatus,
    ScanPhase,
    ScanResult,
)
from .migrations import get_schema_version, run_migrations
from .repositories import (
    CheckpointRepository,
    DiscoveryDirectoryRepository,
    DeletionAuditRepository,
    DeletionPlanRepository,
    DeletionVerificationRepository,
    DuplicateGroupRepository,
    FullHashRepository,
    HashCacheRepository,
    InventoryRepository,
    PartialCandidateRepository,
    PartialHashRepository,
    SessionRepository,
    SizeCandidateRepository,
)


@dataclass
class Persistence:
    """Database persistence layer."""
    
    db_path: Path
    _connection: Optional[sqlite3.Connection] = None
    _lock: threading.Lock = None
    _schema_version: int = 0
    _sqlite_wal: bool = True
    _sqlite_synchronous: str = "NORMAL"
    
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
            import logging
            _log = logging.getLogger(__name__)
            self._connection = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._connection.row_factory = sqlite3.Row
            wal = getattr(self, "_sqlite_wal", True)
            sync = getattr(self, "_sqlite_synchronous", "NORMAL")
            if wal:
                try:
                    self._connection.execute("PRAGMA journal_mode=WAL;")
                except sqlite3.DatabaseError as e:
                    _log.warning("Could not enable WAL mode for %s: %s", self.db_path, e)
            self._connection.execute(f"PRAGMA synchronous={sync};")
            self._connection.execute("PRAGMA foreign_keys=ON;")
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
            migrations_dir = Path(__file__).with_name("migrations")
            if migrations_dir.exists():
                self._schema_version = run_migrations(conn, migrations_dir)

    @property
    def schema_version(self) -> int:
        """Current durable schema version."""
        with self._lock:
            conn = self._get_connection()
            self._schema_version = max(self._schema_version, get_schema_version(conn))
            return self._schema_version

    @property
    def session_repo(self) -> SessionRepository:
        return SessionRepository(self._get_connection())

    @property
    def checkpoint_repo(self) -> CheckpointRepository:
        return CheckpointRepository(self._get_connection())

    @property
    def inventory_repo(self) -> InventoryRepository:
        return InventoryRepository(self._get_connection())

    @property
    def size_candidate_repo(self) -> SizeCandidateRepository:
        return SizeCandidateRepository(self._get_connection())

    @property
    def partial_hash_repo(self) -> PartialHashRepository:
        return PartialHashRepository(self._get_connection())

    @property
    def partial_candidate_repo(self) -> PartialCandidateRepository:
        return PartialCandidateRepository(self._get_connection())

    @property
    def full_hash_repo(self) -> FullHashRepository:
        return FullHashRepository(self._get_connection())

    @property
    def duplicate_group_repo(self) -> DuplicateGroupRepository:
        return DuplicateGroupRepository(self._get_connection())

    @property
    def hash_cache_repo(self) -> HashCacheRepository:
        return HashCacheRepository(self._get_connection())

    @property
    def deletion_plan_repo(self) -> DeletionPlanRepository:
        return DeletionPlanRepository(self._get_connection())

    @property
    def deletion_audit_repo(self) -> DeletionAuditRepository:
        return DeletionAuditRepository(self._get_connection())

    @property
    def discovery_dir_repo(self) -> DiscoveryDirectoryRepository:
        return DiscoveryDirectoryRepository(self._get_connection())

    @property
    def deletion_verification_repo(self) -> DeletionVerificationRepository:
        return DeletionVerificationRepository(self._get_connection())

    def shadow_write_session(
        self,
        session_id: str,
        config_json: str,
        config_hash: str,
        root_fingerprint: Optional[str] = None,
        discovery_config_hash: Optional[str] = None,
        status: str = "running",
        current_phase: str = ScanPhase.DISCOVERY.value,
    ) -> None:
        """Persist a v2 session row without changing legacy callers."""
        with self._lock:
            self.session_repo.create(
                session_id=session_id,
                config_json=config_json,
                config_hash=config_hash,
                root_fingerprint=root_fingerprint,
                discovery_config_hash=discovery_config_hash,
                status=status,
                current_phase=current_phase,
            )

    def shadow_update_session(
        self,
        session_id: str,
        status: str,
        current_phase: Optional[str] = None,
        failure_reason: Optional[str] = None,
        metrics: Optional[Dict[str, Any]] = None,
        completed: bool = False,
    ) -> None:
        with self._lock:
            self.session_repo.update_status(
                session_id=session_id,
                status=status,
                current_phase=current_phase,
                failure_reason=failure_reason,
                metrics=metrics,
                completed=completed,
            )

    def shadow_write_checkpoint(
        self,
        session_id: str,
        phase_name: ScanPhase,
        completed_units: int,
        total_units: Optional[int] = None,
        chunk_cursor: Optional[str] = None,
        status: PhaseStatus = PhaseStatus.RUNNING,
        metadata_json: Optional[Dict[str, Any]] = None,
    ) -> None:
        with self._lock:
            self.checkpoint_repo.upsert(
                CheckpointInfo(
                    session_id=session_id,
                    phase_name=phase_name,
                    chunk_cursor=chunk_cursor,
                    completed_units=completed_units,
                    total_units=total_units,
                    status=status,
                    metadata_json=metadata_json or {},
                )
            )

    def shadow_write_inventory(self, session_id: str, files: List[FileMetadata]) -> int:
        with self._lock:
            if self.session_repo.get(session_id) is None:
                self.session_repo.create(
                    session_id=session_id,
                    config_json=json.dumps({"roots": []}),
                    config_hash="shadow",
                    discovery_config_hash="shadow",
                )
            return self.inventory_repo.insert_batch(session_id, files)
    
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
                    SELECT h.scan_id, h.started_at, h.completed_at, h.config,
                           h.files_scanned, h.duplicates_found, h.reclaimable_bytes, h.status,
                           s.config_hash, s.root_fingerprint, s.discovery_config_hash, s.metrics_json,
                           dv.summary_json AS deletion_verification_summary
                    FROM scan_history h
                    LEFT JOIN scan_sessions s
                      ON s.session_id = h.scan_id
                    LEFT JOIN deletion_verifications dv
                      ON dv.session_id = h.scan_id
                    ORDER BY h.started_at DESC
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
                        "config_hash": r.get("config_hash") or "",
                        "root_fingerprint": r.get("root_fingerprint") or "",
                        "discovery_config_hash": r.get("discovery_config_hash") or "",
                        "benchmark_summary": (
                            (json.loads(r["metrics_json"]) or {}).get("benchmark", {})
                            if r.get("metrics_json")
                            else {}
                        ),
                        "deletion_verification_summary": (
                            json.loads(r["deletion_verification_summary"])
                            if r.get("deletion_verification_summary")
                            else {}
                        ),
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
                if file.hash_partial:
                    self.hash_cache_repo.upsert(
                        path=file.path,
                        size_bytes=file.size,
                        mtime_ns=file.mtime_ns,
                        algorithm="legacy",
                        strategy_version="v1",
                        hash_kind="partial",
                        hash_value=file.hash_partial,
                    )
                if file.hash_full:
                    self.hash_cache_repo.upsert(
                        path=file.path,
                        size_bytes=file.size,
                        mtime_ns=file.mtime_ns,
                        algorithm="legacy",
                        strategy_version="v1",
                        hash_kind="full",
                        hash_value=file.hash_full,
                    )
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
