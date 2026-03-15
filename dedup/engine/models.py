"""
DEDUP Engine Models - Core data structures for duplicate file detection.

All models are designed to be:
- Serializable for persistence
- Memory-efficient for 1M+ file datasets
- Immutable where possible for thread safety
"""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import Dict, List, Optional, Set, Any, Callable


class PipelineMode(str, Enum):
    """Scan mode - exact duplicates only (visual/fuzzy removed for simplicity)."""
    EXACT = "exact"


class FileStatus(str, Enum):
    """Status of a file in the duplicate detection process."""
    PENDING = "pending"
    SCANNED = "scanned"
    HASHED_PARTIAL = "hashed_partial"
    HASHED_FULL = "hashed_full"
    DUPLICATE = "duplicate"
    UNIQUE = "unique"
    ERROR = "error"


class DeletionPolicy(str, Enum):
    """Policy for file deletion."""
    TRASH = "trash"
    PERMANENT = "permanent"


class ScanPhase(str, Enum):
    """Durable pipeline phases."""
    DISCOVERY = "discovery"
    SIZE_REDUCTION = "size_reduction"
    PARTIAL_HASH = "partial_hash"
    FULL_HASH = "full_hash"
    RESULT_ASSEMBLY = "result_assembly"
    DELETE_PLAN = "delete_plan"


class PhaseStatus(str, Enum):
    """Status for phase checkpoint state."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(slots=True, frozen=True)
class FileRecord:
    """Durable inventory row used by the persistence-backed pipeline."""
    path: str
    size_bytes: int
    mtime_ns: int
    inode: Optional[int] = None
    device: Optional[str] = None
    extension: Optional[str] = None
    media_kind: Optional[str] = None
    discovery_status: str = "discovered"

    def to_file_metadata(self) -> "FileMetadata":
        return FileMetadata(
            path=self.path,
            size=self.size_bytes,
            mtime_ns=self.mtime_ns,
            inode=self.inode,
            status=FileStatus.SCANNED,
        )

    @classmethod
    def from_file_metadata(cls, file: "FileMetadata") -> "FileRecord":
        return cls(
            path=file.path,
            size_bytes=file.size,
            mtime_ns=file.mtime_ns,
            inode=file.inode,
            extension=file.extension or None,
        )


@dataclass(slots=True)
class CheckpointInfo:
    """Durable checkpoint metadata for resumable phase execution."""
    session_id: str
    phase_name: ScanPhase
    chunk_cursor: Optional[str] = None
    completed_units: int = 0
    total_units: Optional[int] = None
    status: PhaseStatus = PhaseStatus.PENDING
    updated_at: datetime = field(default_factory=datetime.now)
    metadata_json: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "phase_name": self.phase_name.value,
            "chunk_cursor": self.chunk_cursor,
            "completed_units": self.completed_units,
            "total_units": self.total_units,
            "status": self.status.value,
            "updated_at": self.updated_at.isoformat(),
            "metadata_json": self.metadata_json,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CheckpointInfo":
        return cls(
            session_id=data["session_id"],
            phase_name=ScanPhase(data["phase_name"]),
            chunk_cursor=data.get("chunk_cursor"),
            completed_units=data.get("completed_units", 0),
            total_units=data.get("total_units"),
            status=PhaseStatus(data.get("status", PhaseStatus.PENDING.value)),
            updated_at=datetime.fromisoformat(data["updated_at"])
            if data.get("updated_at")
            else datetime.now(),
            metadata_json=data.get("metadata_json") or {},
        )


@dataclass(slots=True, frozen=True)
class FileMetadata:
    """
    Lightweight, immutable file metadata record.
    
    Designed for memory efficiency with 1M+ files:
    - Uses __slots__ to reduce per-object overhead
    - Stores path as string to avoid Path object overhead in collections
    - Optional hash fields populated progressively
    """
    path: str  # Store as string for memory efficiency
    size: int
    mtime_ns: int  # Nanoseconds for precision
    inode: Optional[int] = None  # For hard link detection
    hash_partial: Optional[str] = None  # First N bytes hash
    hash_full: Optional[str] = None  # Complete file hash
    status: FileStatus = FileStatus.PENDING
    error_message: Optional[str] = None
    
    # Derived properties
    @property
    def path_obj(self) -> Path:
        return Path(self.path)
    
    @property
    def mtime(self) -> float:
        return self.mtime_ns / 1_000_000_000
    
    @property
    def extension(self) -> str:
        return Path(self.path).suffix.lower()
    
    @property
    def filename(self) -> str:
        return Path(self.path).name
    
    def with_hash_partial(self, hash_value: str) -> FileMetadata:
        """Return new instance with partial hash set."""
        return FileMetadata(
            path=self.path,
            size=self.size,
            mtime_ns=self.mtime_ns,
            inode=self.inode,
            hash_partial=hash_value,
            hash_full=self.hash_full,
            status=FileStatus.HASHED_PARTIAL,
        )
    
    def with_hash_full(self, hash_value: str) -> FileMetadata:
        """Return new instance with full hash set."""
        return FileMetadata(
            path=self.path,
            size=self.size,
            mtime_ns=self.mtime_ns,
            inode=self.inode,
            hash_partial=self.hash_partial,
            hash_full=hash_value,
            status=FileStatus.HASHED_FULL,
        )
    
    def with_error(self, error: str) -> FileMetadata:
        """Return new instance with error status."""
        return FileMetadata(
            path=self.path,
            size=self.size,
            mtime_ns=self.mtime_ns,
            inode=self.inode,
            hash_partial=self.hash_partial,
            hash_full=self.hash_full,
            status=FileStatus.ERROR,
            error_message=error,
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "path": self.path,
            "size": self.size,
            "mtime_ns": self.mtime_ns,
            "inode": self.inode,
            "hash_partial": self.hash_partial,
            "hash_full": self.hash_full,
            "status": self.status.value,
            "error_message": self.error_message,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> FileMetadata:
        """Deserialize from dictionary."""
        return cls(
            path=data["path"],
            size=data["size"],
            mtime_ns=data["mtime_ns"],
            inode=data.get("inode"),
            hash_partial=data.get("hash_partial"),
            hash_full=data.get("hash_full"),
            status=FileStatus(data.get("status", "pending")),
            error_message=data.get("error_message"),
        )
    
    @classmethod
    def from_path(cls, path: Path | str, follow_symlinks: bool = False) -> Optional[FileMetadata]:
        """Create FileMetadata from filesystem path."""
        try:
            p = Path(path)
            if not p.exists() or not p.is_file():
                return None
            
            st = p.stat(follow_symlinks=follow_symlinks)
            
            return cls(
                path=str(p.resolve()),
                size=st.st_size,
                mtime_ns=getattr(st, 'st_mtime_ns', int(st.st_mtime * 1_000_000_000)),
                inode=st.st_ino,
            )
        except (OSError, ValueError, PermissionError):
            return None


@dataclass(slots=True)
class DuplicateGroup:
    """
    A group of duplicate files (2 or more files with identical content).
    
    The group_hash is the canonical identifier for this duplicate set.
    """
    group_id: str
    group_hash: str  # The hash that defines this group
    files: List[FileMetadata] = field(default_factory=list)
    total_size: int = 0  # Total bytes if all duplicates were removed
    reclaimable_size: int = 0  # Bytes that can be reclaimed (total - one copy)
    
    def __post_init__(self):
        if not self.group_id:
            self.group_id = str(uuid.uuid4())[:8]
        self._recalculate_sizes()
    
    def _recalculate_sizes(self):
        """Recalculate size metrics."""
        if self.files:
            file_size = self.files[0].size
            self.total_size = file_size * len(self.files)
            self.reclaimable_size = file_size * (len(self.files) - 1)
    
    def add_file(self, file: FileMetadata):
        """Add a file to this duplicate group."""
        self.files.append(file)
        self._recalculate_sizes()
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "group_id": self.group_id,
            "group_hash": self.group_hash,
            "files": [f.to_dict() for f in self.files],
            "total_size": self.total_size,
            "reclaimable_size": self.reclaimable_size,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> DuplicateGroup:
        """Deserialize from dictionary."""
        group = cls(
            group_id=data["group_id"],
            group_hash=data["group_hash"],
        )
        group.files = [FileMetadata.from_dict(f) for f in data.get("files", [])]
        group.total_size = data.get("total_size", 0)
        group.reclaimable_size = data.get("reclaimable_size", 0)
        return group


@dataclass(slots=True)
class ScanConfig:
    """
    Configuration for a duplicate file scan.
    
    All parameters have sensible defaults for immediate use.
    """
    # Required
    roots: List[Path] = field(default_factory=list)
    
    # Discovery options
    min_size_bytes: int = 1  # No minimum by default
    max_size_bytes: Optional[int] = None
    include_hidden: bool = False
    follow_symlinks: bool = False
    scan_subfolders: bool = True  # Recurse into subfolders (default: scan entire tree)
    allowed_extensions: Optional[Set[str]] = None
    exclude_dirs: Set[str] = field(default_factory=lambda: {
        '.git', '.svn', '.hg',  # Version control
        'node_modules', '__pycache__', '.pytest_cache',  # Build artifacts
        '.venv', 'venv', 'env',  # Virtual environments
        '$RECYCLE.BIN', 'System Volume Information',  # Windows system
    })
    
    # Hashing options
    hash_algorithm: str = "xxhash64"  # Fast, non-cryptographic
    partial_hash_bytes: int = 4096  # First 4KB for initial comparison
    full_hash_workers: int = 4  # Parallel hash workers
    
    # Performance options
    batch_size: int = 1000  # Process files in batches
    progress_interval_ms: int = 100  # Progress update interval
    
    # Mode
    mode: PipelineMode = PipelineMode.EXACT
    
    def __post_init__(self):
        # Normalize paths: resolve all, prefer existing; never drop all roots
        # (exists() can be False on network/OneDrive paths; discovery will still try)
        resolved = [Path(r).resolve() for r in self.roots]
        existing = [r for r in resolved if r.exists()]
        self.roots = existing if existing else resolved

        # Normalize extensions to lowercase
        if self.allowed_extensions:
            self.allowed_extensions = {e.lower().lstrip('.') for e in self.allowed_extensions}
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "roots": [str(r) for r in self.roots],
            "min_size_bytes": self.min_size_bytes,
            "max_size_bytes": self.max_size_bytes,
            "include_hidden": self.include_hidden,
            "follow_symlinks": self.follow_symlinks,
            "scan_subfolders": self.scan_subfolders,
            "allowed_extensions": list(self.allowed_extensions) if self.allowed_extensions else None,
            "exclude_dirs": list(self.exclude_dirs),
            "hash_algorithm": self.hash_algorithm,
            "partial_hash_bytes": self.partial_hash_bytes,
            "full_hash_workers": self.full_hash_workers,
            "batch_size": self.batch_size,
            "progress_interval_ms": self.progress_interval_ms,
            "mode": self.mode.value,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ScanConfig:
        """Deserialize from dictionary."""
        config = cls(
            roots=[Path(r) for r in data.get("roots", [])],
            min_size_bytes=data.get("min_size_bytes", 1),
            max_size_bytes=data.get("max_size_bytes"),
            include_hidden=data.get("include_hidden", False),
            follow_symlinks=data.get("follow_symlinks", False),
            scan_subfolders=data.get("scan_subfolders", True),
            allowed_extensions=set(data["allowed_extensions"]) if data.get("allowed_extensions") else None,
            exclude_dirs=set(data.get("exclude_dirs", [])),
            hash_algorithm=data.get("hash_algorithm", "xxhash64"),
            partial_hash_bytes=data.get("partial_hash_bytes", 4096),
            full_hash_workers=data.get("full_hash_workers", 4),
            batch_size=data.get("batch_size", 1000),
            progress_interval_ms=data.get("progress_interval_ms", 100),
            mode=PipelineMode(data.get("mode", "exact")),
        )
        return config


@dataclass(slots=True)
class ScanProgress:
    """
    Immutable snapshot of scan progress.
    
    All numeric values are actual measured data, never estimates presented as fact.
    If a value is unknown, it is None (not a fabricated number).
    """
    scan_id: str
    
    # Phase information
    phase: str = "idle"  # idle, discovering, grouping, hashing_partial, hashing_full, complete, error
    phase_description: str = ""
    
    # Progress (only show percent if we know the total)
    files_found: int = 0
    files_total: Optional[int] = None  # None until discovery completes
    bytes_found: int = 0
    bytes_total: Optional[int] = None
    groups_found: int = 0
    duplicates_found: int = 0
    
    # Timing (all in seconds)
    elapsed_seconds: float = 0.0
    estimated_remaining_seconds: Optional[float] = None  # Only if we have enough data
    
    # Throughput (measured, not estimated)
    files_per_second: Optional[float] = None
    bytes_per_second: Optional[float] = None
    
    # Current operation
    current_file: Optional[str] = None
    current_operation: str = ""
    
    # Errors and warnings
    error_count: int = 0
    warning_count: int = 0
    last_error: Optional[str] = None
    
    # Timestamp
    timestamp: float = field(default_factory=time.time)
    
    @property
    def percent_complete(self) -> Optional[float]:
        """Return percent complete only if we know the total."""
        if self.files_total and self.files_total > 0:
            return min(100.0, (self.files_found / self.files_total) * 100)
        return None
    
    @property
    def is_complete(self) -> bool:
        return self.phase == "complete"
    
    @property
    def is_active(self) -> bool:
        return self.phase not in ("idle", "complete", "error", "cancelled")
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "scan_id": self.scan_id,
            "phase": self.phase,
            "phase_description": self.phase_description,
            "files_found": self.files_found,
            "files_total": self.files_total,
            "bytes_found": self.bytes_found,
            "bytes_total": self.bytes_total,
            "groups_found": self.groups_found,
            "duplicates_found": self.duplicates_found,
            "elapsed_seconds": self.elapsed_seconds,
            "estimated_remaining_seconds": self.estimated_remaining_seconds,
            "files_per_second": self.files_per_second,
            "bytes_per_second": self.bytes_per_second,
            "current_file": self.current_file,
            "current_operation": self.current_operation,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "last_error": self.last_error,
            "timestamp": self.timestamp,
        }


@dataclass(slots=True)
class ScanResult:
    """
    Complete result of a duplicate file scan.
    
    Contains all discovered duplicate groups and scan statistics.
    """
    scan_id: str
    config: ScanConfig
    
    # Timing
    started_at: datetime
    completed_at: Optional[datetime] = None
    
    # Discovery results
    files_scanned: int = 0
    bytes_scanned: int = 0
    unique_files: int = 0
    
    # Duplicate results
    duplicate_groups: List[DuplicateGroup] = field(default_factory=list)
    total_duplicates: int = 0
    total_reclaimable_bytes: int = 0
    
    # Errors
    errors: List[str] = field(default_factory=list)
    
    @property
    def duration_seconds(self) -> float:
        """Calculate scan duration."""
        if self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return 0.0
    
    @property
    def duplicate_count(self) -> int:
        """Total number of duplicate files (not counting originals)."""
        return sum(len(g.files) - 1 for g in self.duplicate_groups)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "scan_id": self.scan_id,
            "config": self.config.to_dict(),
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "files_scanned": self.files_scanned,
            "bytes_scanned": self.bytes_scanned,
            "unique_files": self.unique_files,
            "duplicate_groups": [g.to_dict() for g in self.duplicate_groups],
            "total_duplicates": self.total_duplicates,
            "total_reclaimable_bytes": self.total_reclaimable_bytes,
            "errors": self.errors,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ScanResult:
        """Deserialize from dictionary."""
        return cls(
            scan_id=data["scan_id"],
            config=ScanConfig.from_dict(data["config"]),
            started_at=datetime.fromisoformat(data["started_at"]),
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
            files_scanned=data.get("files_scanned", 0),
            bytes_scanned=data.get("bytes_scanned", 0),
            unique_files=data.get("unique_files", 0),
            duplicate_groups=[DuplicateGroup.from_dict(g) for g in data.get("duplicate_groups", [])],
            total_duplicates=data.get("total_duplicates", 0),
            total_reclaimable_bytes=data.get("total_reclaimable_bytes", 0),
            errors=data.get("errors", []),
        )


@dataclass(slots=True)
class DeletionPlan:
    """
    A plan for deleting duplicate files.
    
    Each group specifies which file to keep and which to delete.
    """
    scan_id: str
    policy: DeletionPolicy = DeletionPolicy.TRASH
    groups: List[Dict[str, Any]] = field(default_factory=list)
    
    @property
    def total_files_to_delete(self) -> int:
        return sum(len(g.get("delete", [])) for g in self.groups)
    
    @property
    def total_bytes_to_reclaim(self) -> int:
        total = 0
        for group in self.groups:
            for file_path in group.get("delete", []):
                try:
                    total += Path(file_path).stat().st_size
                except (OSError, ValueError):
                    pass
        return total
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "scan_id": self.scan_id,
            "policy": self.policy.value,
            "groups": self.groups,
        }


@dataclass(slots=True)
class DeletionResult:
    """
    Result of executing a deletion plan.
    """
    scan_id: str
    policy: DeletionPolicy
    deleted_files: List[str] = field(default_factory=list)
    failed_files: List[Dict[str, str]] = field(default_factory=list)
    bytes_reclaimed: int = 0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    @property
    def success_count(self) -> int:
        return len(self.deleted_files)
    
    @property
    def failure_count(self) -> int:
        return len(self.failed_files)
    
    @property
    def duration_seconds(self) -> float:
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "scan_id": self.scan_id,
            "policy": self.policy.value,
            "deleted_files": self.deleted_files,
            "failed_files": self.failed_files,
            "bytes_reclaimed": self.bytes_reclaimed,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
