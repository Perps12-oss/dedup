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


class ResumeOutcome(str, Enum):
    """Result of resume compatibility check. No vague middle state."""
    SAFE_RESUME = "safe_resume"
    REBUILD_CURRENT_PHASE = "rebuild_current_phase"
    RESTART_REQUIRED = "restart_required"


class ResumeReason(str, Enum):
    """Why a given resume outcome was chosen."""
    NO_SESSION = "no_session"
    SESSION_NOT_RESUMABLE = "session_not_resumable"
    SCHEMA_VERSION_MISMATCH = "schema_version_mismatch"
    CONFIG_HASH_MISMATCH = "config_hash_mismatch"
    ROOT_SET_CHANGED = "root_set_changed"
    HASH_STRATEGY_CHANGED = "hash_strategy_changed"
    PHASE_NOT_FINALIZED = "phase_not_finalized"
    ARTIFACT_INCOMPLETE = "artifact_incomplete"
    ARTIFACT_COUNT_MISMATCH = "artifact_count_mismatch"
    COMPATIBLE = "compatible"
    NEW_SCAN = "new_scan"


class DeletionVerificationTargetStatus(str, Enum):
    """Verification outcome for an individual delete target."""
    DELETED = "deleted"
    STILL_PRESENT = "still_present"
    CHANGED_AFTER_PLAN = "changed_after_plan"
    VERIFICATION_FAILED = "verification_failed"


class DeletionVerificationGroupStatus(str, Enum):
    """Verification outcome for a duplicate group after deletion."""
    RESOLVED = "resolved"
    PARTIALLY_RESOLVED = "partially_resolved"
    UNRESOLVED = "unresolved"
    VERIFICATION_INCOMPLETE = "verification_incomplete"


@dataclass(slots=True)
class PhaseCompatibilityReport:
    """Per-phase compatibility result for resume decision."""
    phase: ScanPhase
    compatible: bool
    reasons: List[str] = field(default_factory=list)
    artifact_stats: Optional[Dict[str, Any]] = None


@dataclass(slots=True)
class ResumeDecision:
    """Authoritative resume decision: outcome, first runnable phase, and reason."""
    outcome: ResumeOutcome
    first_runnable_phase: ScanPhase
    reason: str
    compatibility_reports: List[PhaseCompatibilityReport] = field(default_factory=list)
    cursor_or_context: Optional[Dict[str, Any]] = None

    def log_message(self) -> str:
        return f"Resume decision: {self.outcome.value} from phase {self.first_runnable_phase.value}; reason={self.reason}"


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
    # Compatibility fields (stored in metadata_json if columns missing)
    schema_version: Optional[int] = None
    phase_version: Optional[str] = None
    config_hash: Optional[str] = None
    input_artifact_fingerprint: Optional[str] = None
    output_artifact_fingerprint: Optional[str] = None
    is_finalized: bool = False
    resume_policy: str = "safe"

    def to_dict(self) -> Dict[str, Any]:
        meta = dict(self.metadata_json)
        meta.setdefault("schema_version", self.schema_version)
        meta.setdefault("phase_version", self.phase_version)
        meta.setdefault("config_hash", self.config_hash)
        meta.setdefault("input_artifact_fingerprint", self.input_artifact_fingerprint)
        meta.setdefault("output_artifact_fingerprint", self.output_artifact_fingerprint)
        meta.setdefault("is_finalized", self.is_finalized)
        meta.setdefault("resume_policy", self.resume_policy)
        return {
            "session_id": self.session_id,
            "phase_name": self.phase_name.value,
            "chunk_cursor": self.chunk_cursor,
            "completed_units": self.completed_units,
            "total_units": self.total_units,
            "status": self.status.value,
            "updated_at": self.updated_at.isoformat(),
            "metadata_json": meta,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CheckpointInfo":
        meta = data.get("metadata_json") or {}
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
            metadata_json=meta,
            schema_version=meta.get("schema_version"),
            phase_version=meta.get("phase_version"),
            config_hash=meta.get("config_hash"),
            input_artifact_fingerprint=meta.get("input_artifact_fingerprint"),
            output_artifact_fingerprint=meta.get("output_artifact_fingerprint"),
            is_finalized=bool(meta.get("is_finalized", False)),
            resume_policy=str(meta.get("resume_policy", "safe")),
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
    batch_size: int = 5000  # Process files in batches (inventory writes)
    progress_interval_ms: int = 100  # Progress update interval
    resolve_paths: bool = False  # Path.resolve() per file; expensive on Windows/OneDrive
    checkpoint_every_files: int = 5000  # Checkpoint write cadence during discovery
    discovery_max_workers: Optional[int] = None  # Discovery threads (None = auto, 4 default)
    sqlite_wal: bool = True  # Use WAL mode for faster writes
    sqlite_synchronous: str = "NORMAL"  # OFF | NORMAL | FULL
    incremental_discovery: bool = True  # Reuse compatible prior discovery state when safe

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
            "resolve_paths": self.resolve_paths,
            "checkpoint_every_files": self.checkpoint_every_files,
            "discovery_max_workers": self.discovery_max_workers,
            "sqlite_wal": self.sqlite_wal,
            "sqlite_synchronous": self.sqlite_synchronous,
            "incremental_discovery": self.incremental_discovery,
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
            batch_size=data.get("batch_size", 5000),
            progress_interval_ms=data.get("progress_interval_ms", 100),
            resolve_paths=data.get("resolve_paths", False),
            checkpoint_every_files=data.get("checkpoint_every_files", 5000),
            discovery_max_workers=data.get("discovery_max_workers"),
            sqlite_wal=data.get("sqlite_wal", True),
            sqlite_synchronous=data.get("sqlite_synchronous", "NORMAL"),
            incremental_discovery=data.get("incremental_discovery", True),
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
    incremental_discovery_report: Optional[Dict[str, Any]] = None
    benchmark_report: Optional[Dict[str, Any]] = None
    
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
            "incremental_discovery_report": self.incremental_discovery_report,
            "benchmark_report": self.benchmark_report,
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
            incremental_discovery_report=data.get("incremental_discovery_report"),
            benchmark_report=data.get("benchmark_report"),
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
    verification_summary: Optional[Dict[str, int]] = None
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
            "verification_summary": self.verification_summary,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


@dataclass(slots=True)
class DeletionVerificationTarget:
    """Verification result for one delete target."""
    path: str
    status: DeletionVerificationTargetStatus
    group_id: str = ""
    detail: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "status": self.status.value,
            "group_id": self.group_id,
            "detail": self.detail,
        }


@dataclass(slots=True)
class DeletionVerificationGroup:
    """Verification result for one duplicate group."""
    group_id: str
    status: DeletionVerificationGroupStatus
    keep_path: str = ""
    detail: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "group_id": self.group_id,
            "status": self.status.value,
            "keep_path": self.keep_path,
            "detail": self.detail,
        }


@dataclass(slots=True)
class DeletionVerificationResult:
    """Summary of post-delete verification without running a rescan."""
    scan_id: str
    plan_id: str
    target_results: List[DeletionVerificationTarget] = field(default_factory=list)
    group_results: List[DeletionVerificationGroup] = field(default_factory=list)
    summary: Dict[str, int] = field(default_factory=dict)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scan_id": self.scan_id,
            "plan_id": self.plan_id,
            "target_results": [item.to_dict() for item in self.target_results],
            "group_results": [item.to_dict() for item in self.group_results],
            "summary": dict(self.summary),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
