"""
DEDUP Scan Pipeline - Orchestrates the complete duplicate detection workflow.

Pipeline phases:
1. Discovery - Find all files in specified directories
2. Size Grouping - Group by size (eliminates unique sizes)
3. Partial Hashing - Hash first N bytes (fast elimination)
4. Full Hashing - Confirm duplicates with complete hash
5. Result Assembly - Build duplicate groups

All phases support cancellation and progress reporting.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Protocol
import threading

from .models import (
    CheckpointInfo,
    DeletionPlan,
    DeletionPolicy,
    DeletionResult,
    FileMetadata,
    PhaseStatus,
    ScanConfig,
    ScanPhase,
    ScanProgress,
    ScanResult,
)
from .discovery import DiscoveryOptions, FileDiscovery
from .hashing import HashEngine
from .grouping import GroupingEngine
from .deletion import DeletionEngine


@dataclass
class PhaseChunkResult:
    """Result metadata for a single phase execution step."""
    completed_units: int = 0
    total_units: Optional[int] = None
    next_cursor: Optional[str] = None
    events: List[Dict[str, Any]] = field(default_factory=list)
    artifacts_written: List[str] = field(default_factory=list)
    is_complete: bool = True
    payload: Any = None


@dataclass
class PhaseSummary:
    """Small phase completion summary."""
    phase_name: ScanPhase
    completed_units: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


class PhaseRunner(Protocol):
    """Protocol for persistence-aware pipeline phases."""

    phase_name: ScanPhase

    def can_resume(self, pipeline: "ScanPipeline", checkpoint: Optional[CheckpointInfo]) -> bool: ...
    def run_chunk(
        self,
        pipeline: "ScanPipeline",
        checkpoint: Optional[CheckpointInfo],
        progress_cb: Optional[Callable[[ScanProgress], None]] = None,
    ) -> PhaseChunkResult: ...
    def finalize(self, pipeline: "ScanPipeline", result: PhaseChunkResult) -> PhaseSummary: ...


@dataclass
class DiscoveryPhaseRunner:
    """Discovery phase with optional durable inventory shadow writes."""

    phase_name: ScanPhase = ScanPhase.DISCOVERY

    def can_resume(self, pipeline: "ScanPipeline", checkpoint: Optional[CheckpointInfo]) -> bool:
        return checkpoint is not None and checkpoint.status == PhaseStatus.COMPLETED

    def run_chunk(
        self,
        pipeline: "ScanPipeline",
        checkpoint: Optional[CheckpointInfo],
        progress_cb: Optional[Callable[[ScanProgress], None]] = None,
    ) -> PhaseChunkResult:
        files = pipeline._discover_files(progress_cb)
        return PhaseChunkResult(
            completed_units=len(files),
            total_units=len(files),
            artifacts_written=["inventory_files"] if pipeline.persistence else [],
            payload=files,
        )

    def finalize(self, pipeline: "ScanPipeline", result: PhaseChunkResult) -> PhaseSummary:
        return PhaseSummary(
            phase_name=self.phase_name,
            completed_units=result.completed_units,
            metadata={"bytes_found": pipeline._bytes_found},
        )


@dataclass
class GroupingPhaseRunner:
    """Grouping/hash confirmation phase with durable artifact persistence."""

    phase_name: ScanPhase = ScanPhase.RESULT_ASSEMBLY

    def can_resume(self, pipeline: "ScanPipeline", checkpoint: Optional[CheckpointInfo]) -> bool:
        return checkpoint is not None and checkpoint.status == PhaseStatus.COMPLETED

    def run_chunk(
        self,
        pipeline: "ScanPipeline",
        checkpoint: Optional[CheckpointInfo],
        progress_cb: Optional[Callable[[ScanProgress], None]] = None,
    ) -> PhaseChunkResult:
        if progress_cb:
            progress_cb(pipeline._create_progress(
                phase="grouping",
                phase_description="Finding duplicates...",
                files_found=pipeline._files_found,
                bytes_found=pipeline._bytes_found,
            ))
        duplicate_groups = pipeline.grouping.find_duplicates(
            iter(pipeline._discovered_files),
            pipeline.scan_id,
            cancel_check=lambda: pipeline._cancelled,
            persistence=pipeline.persistence,
        )
        return PhaseChunkResult(
            completed_units=len(duplicate_groups),
            total_units=len(duplicate_groups),
            artifacts_written=[
                "size_candidates",
                "partial_hashes",
                "partial_candidates",
                "full_hashes",
                "duplicate_groups",
            ] if pipeline.persistence else [],
            payload=duplicate_groups,
        )

    def finalize(self, pipeline: "ScanPipeline", result: PhaseChunkResult) -> PhaseSummary:
        return PhaseSummary(
            phase_name=self.phase_name,
            completed_units=result.completed_units,
        )


@dataclass
class ScanPipeline:
    """
    Main scan pipeline that orchestrates duplicate detection.
    
    Usage:
        config = ScanConfig(roots=[Path("/data")])
        pipeline = ScanPipeline(config)
        
        def on_progress(progress: ScanProgress):
            print(f"{progress.phase}: {progress.files_found} files")
        
        result = pipeline.run(progress_cb=on_progress)
    """
    
    config: ScanConfig
    scan_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    hash_cache_getter: Optional[Callable[[str], Optional[Dict[str, Any]]]] = None
    hash_cache_setter: Optional[Callable[[FileMetadata], bool]] = None
    persistence: Optional[Any] = None
    
    # Components
    discovery: FileDiscovery = field(init=False)
    hash_engine: HashEngine = field(init=False)
    grouping: GroupingEngine = field(init=False)
    
    # State
    _cancelled: bool = field(default=False, repr=False)
    _start_time: float = field(default=0, repr=False)
    _files_found: int = field(default=0, repr=False)
    _bytes_found: int = field(default=0, repr=False)
    _errors: List[str] = field(default_factory=list, repr=False)
    _discovered_files: List[FileMetadata] = field(default_factory=list, repr=False)
    phase_runners: List[PhaseRunner] = field(default_factory=list, init=False, repr=False)
    
    def __post_init__(self):
        # Initialize components
        discovery_options = DiscoveryOptions.from_config(self.config)
        self.discovery = FileDiscovery(discovery_options)
        self.hash_engine = HashEngine.from_config(self.config)
        self.hash_engine.cache_getter = self.hash_cache_getter
        self.hash_engine.cache_setter = self.hash_cache_setter
        self.grouping = GroupingEngine(
            hash_engine=self.hash_engine,
            progress_cb=None,
        )
        self.phase_runners = [
            DiscoveryPhaseRunner(),
            GroupingPhaseRunner(),
        ]
    
    def cancel(self):
        """Request cancellation of the scan."""
        self._cancelled = True
        self.discovery.cancel()
    
    @property
    def is_cancelled(self) -> bool:
        return self._cancelled
    
    def _elapsed(self) -> float:
        """Get elapsed time in seconds."""
        return time.time() - self._start_time
    
    def _create_progress(self, **kwargs) -> ScanProgress:
        """Create a progress snapshot with common fields."""
        return ScanProgress(
            scan_id=self.scan_id,
            elapsed_seconds=self._elapsed(),
            timestamp=time.time(),
            **kwargs
        )

    def _config_hash(self) -> str:
        payload = json.dumps(self.config.to_dict(), sort_keys=True).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def _initialize_durable_session(self) -> None:
        if not self.persistence:
            return
        roots = [str(root) for root in self.config.roots]
        root_fingerprint = hashlib.sha256("|".join(sorted(roots)).encode("utf-8")).hexdigest()
        self.persistence.shadow_write_session(
            session_id=self.scan_id,
            config_json=json.dumps(self.config.to_dict()),
            config_hash=self._config_hash(),
            root_fingerprint=root_fingerprint,
            status="running",
            current_phase=ScanPhase.DISCOVERY.value,
        )

    def _update_phase_checkpoint(
        self,
        phase_name: ScanPhase,
        completed_units: int,
        total_units: Optional[int],
        status: PhaseStatus,
        metadata_json: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not self.persistence:
            return
        self.persistence.shadow_write_checkpoint(
            session_id=self.scan_id,
            phase_name=phase_name,
            completed_units=completed_units,
            total_units=total_units,
            status=status,
            metadata_json=metadata_json or {},
        )
        self.persistence.shadow_update_session(
            session_id=self.scan_id,
            status="running" if status != PhaseStatus.FAILED else "failed",
            current_phase=phase_name.value,
            failure_reason=(metadata_json or {}).get("error"),
        )
    
    def run(
        self,
        progress_cb: Optional[Callable[[ScanProgress], None]] = None
    ) -> ScanResult:
        """
        Run the complete scan pipeline.
        
        Args:
            progress_cb: Called with progress updates
        
        Returns:
            ScanResult containing all duplicate groups
        """
        self._start_time = time.time()
        self.grouping.progress_cb = progress_cb
        self._initialize_durable_session()
        
        result = ScanResult(
            scan_id=self.scan_id,
            config=self.config,
            started_at=datetime.now(),
        )
        
        try:
            duplicate_groups = []
            for runner in self.phase_runners:
                checkpoint = None
                if self.persistence:
                    checkpoint = self.persistence.checkpoint_repo.get(self.scan_id, runner.phase_name)
                if checkpoint and runner.can_resume(self, checkpoint):
                    if runner.phase_name == ScanPhase.DISCOVERY and self.persistence:
                        self._discovered_files = list(self.persistence.inventory_repo.iter_by_session(self.scan_id))
                        self._files_found = len(self._discovered_files)
                        self._bytes_found = sum(file.size for file in self._discovered_files)
                    continue

                phase_status = PhaseStatus.RUNNING
                self._update_phase_checkpoint(runner.phase_name, 0, None, phase_status)
                phase_result = runner.run_chunk(self, checkpoint, progress_cb)
                summary = runner.finalize(self, phase_result)
                self._update_phase_checkpoint(
                    runner.phase_name,
                    phase_result.completed_units,
                    phase_result.total_units,
                    PhaseStatus.COMPLETED,
                    metadata_json=summary.metadata,
                )

                if runner.phase_name == ScanPhase.DISCOVERY:
                    self._discovered_files = phase_result.payload or []
                    if not self._discovered_files and self.config.roots:
                        result.errors.append(
                            "No files were found. Check that the folder path is correct, "
                            "readable, and contains files (check filters: min size, extensions)."
                        )
                else:
                    duplicate_groups = phase_result.payload or []

                if self._cancelled:
                    result.errors.append("Scan cancelled by user")
                    result.completed_at = datetime.now()
                    if self.persistence:
                        self.persistence.shadow_update_session(
                            session_id=self.scan_id,
                            status="cancelled",
                            current_phase=runner.phase_name.value,
                            completed=True,
                        )
                    return result
            
            # Build result
            result.files_scanned = self._files_found
            result.bytes_scanned = self._bytes_found
            result.duplicate_groups = duplicate_groups
            result.total_duplicates = sum(len(g.files) - 1 for g in duplicate_groups)
            result.total_reclaimable_bytes = sum(g.reclaimable_size for g in duplicate_groups)
            result.errors = self._errors
            
            if self._cancelled:
                result.errors.append("Scan cancelled by user")
            
        except Exception as e:
            self._errors.append(str(e))
            result.errors = self._errors
            if self.persistence:
                self.persistence.shadow_update_session(
                    session_id=self.scan_id,
                    status="failed",
                    current_phase=ScanPhase.RESULT_ASSEMBLY.value,
                    failure_reason=str(e),
                    completed=True,
                )
            if progress_cb:
                progress_cb(self._create_progress(
                    phase="error",
                    phase_description=f"Error: {str(e)}",
                    error_count=len(self._errors),
                    last_error=str(e),
                ))
        
        finally:
            result.completed_at = datetime.now()
            if self.persistence and not self._cancelled and not result.errors:
                self.persistence.shadow_update_session(
                    session_id=self.scan_id,
                    status="completed",
                    current_phase=ScanPhase.RESULT_ASSEMBLY.value,
                    metrics={
                        "files_scanned": result.files_scanned,
                        "duplicates_found": result.total_duplicates,
                        "reclaimable_bytes": result.total_reclaimable_bytes,
                    },
                    completed=True,
                )
            
            if progress_cb:
                progress_cb(self._create_progress(
                    phase="complete" if not self._cancelled else "cancelled",
                    phase_description=f"Scan complete. Found {len(result.duplicate_groups)} duplicate groups.",
                    files_found=result.files_scanned,
                    groups_found=len(result.duplicate_groups),
                    duplicates_found=result.total_duplicates,
                ))
        
        return result
    
    def _discover_files(
        self,
        progress_cb: Optional[Callable[[ScanProgress], None]] = None
    ) -> List[FileMetadata]:
        """
        Discover all files.
        
        For 1M+ files, we collect into a list but could stream for even lower memory.
        """
        files = []
        last_progress_time = 0
        progress_interval = self.config.progress_interval_ms / 1000
        
        batch: List[FileMetadata] = []
        for file in self.discovery.discover():
            if self._cancelled:
                break
            
            files.append(file)
            batch.append(file)
            self._files_found += 1
            self._bytes_found += file.size

            if self.persistence and len(batch) >= self.config.batch_size:
                self.persistence.shadow_write_inventory(self.scan_id, batch)
                self._update_phase_checkpoint(
                    ScanPhase.DISCOVERY,
                    completed_units=self._files_found,
                    total_units=None,
                    status=PhaseStatus.RUNNING,
                    metadata_json={"bytes_found": self._bytes_found},
                )
                batch = []
            
            # Throttle progress updates
            current_time = time.time()
            if progress_cb and (current_time - last_progress_time) >= progress_interval:
                progress_cb(self._create_progress(
                    phase="discovering",
                    phase_description=f"Discovering files: {self._files_found} found...",
                    files_found=self._files_found,
                    bytes_found=self._bytes_found,
                    current_file=file.path,
                ))
                last_progress_time = current_time

        if self.persistence and batch:
            self.persistence.shadow_write_inventory(self.scan_id, batch)
            self._update_phase_checkpoint(
                ScanPhase.DISCOVERY,
                completed_units=self._files_found,
                total_units=self._files_found,
                status=PhaseStatus.RUNNING,
                metadata_json={"bytes_found": self._bytes_found},
            )
        
        return files
    
    def create_deletion_plan(
        self,
        result: ScanResult,
        policy: DeletionPolicy = DeletionPolicy.TRASH,
        keep_strategy: str = "first"
    ) -> DeletionPlan:
        """
        Create a deletion plan from scan results.
        
        Args:
            result: The scan result
            policy: Deletion policy (trash or permanent)
            keep_strategy: Which file to keep (first, oldest, newest, largest, smallest)
        
        Returns:
            DeletionPlan
        """
        engine = DeletionEngine(persistence=self.persistence)
        return engine.create_plan_from_groups(
            scan_id=result.scan_id,
            groups=result.duplicate_groups,
            policy=policy,
            keep_strategy=keep_strategy,
        )
    
    def execute_deletion(
        self,
        plan: DeletionPlan,
        dry_run: bool = False,
        progress_cb: Optional[Callable[[int, int, str], bool]] = None
    ) -> DeletionResult:
        """
        Execute a deletion plan.
        
        Args:
            plan: The deletion plan
            dry_run: If True, don't actually delete (preview mode)
            progress_cb: Progress callback(current, total, filename) -> bool (continue?)
        
        Returns:
            DeletionResult
        """
        engine = DeletionEngine(dry_run=dry_run, persistence=self.persistence)
        return engine.execute_plan(plan, progress_cb)


@dataclass
class ResumableScanPipeline(ScanPipeline):
    """
    Scan pipeline with persistence for resumability.
    
    Saves scan state to disk at checkpoints, allowing recovery
    from interruptions for very large scans.
    """
    
    checkpoint_interval: int = 10000  # Files between checkpoints
    checkpoint_dir: Optional[Path] = None
    
    def __post_init__(self):
        super().__post_init__()
        if self.checkpoint_dir:
            self.checkpoint_dir = Path(self.checkpoint_dir)
            self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
    
    def _save_checkpoint(self, files: List[FileMetadata]):
        """Save current state to disk."""
        if not self.checkpoint_dir:
            return
        
        try:
            import json
            checkpoint_file = self.checkpoint_dir / f"{self.scan_id}_checkpoint.json"
            
            data = {
                "scan_id": self.scan_id,
                "config": self.config.to_dict(),
                "files": [f.to_dict() for f in files],
                "timestamp": time.time(),
            }
            
            with open(checkpoint_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        
        except Exception:
            pass  # Checkpoint failure should not stop the scan
    
    def _load_checkpoint(self) -> Optional[List[FileMetadata]]:
        """Load state from disk if available."""
        if not self.checkpoint_dir:
            return None
        
        try:
            import json
            checkpoint_file = self.checkpoint_dir / f"{self.scan_id}_checkpoint.json"
            
            if not checkpoint_file.exists():
                return None
            
            with open(checkpoint_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            return [FileMetadata.from_dict(f) for f in data.get("files", [])]
        
        except Exception:
            return None

    @staticmethod
    def load_checkpoint_config(checkpoint_dir: Path, scan_id: str) -> Optional[ScanConfig]:
        """Load ScanConfig from a checkpoint file (for resume). Returns None if missing or invalid."""
        try:
            import json
            path = Path(checkpoint_dir) / f"{scan_id}_checkpoint.json"
            if not path.exists():
                return None
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return ScanConfig.from_dict(data.get("config", {}))
        except Exception:
            return None

    def _clear_checkpoint(self) -> None:
        """Remove checkpoint file after successful completion."""
        if not self.checkpoint_dir:
            return
        try:
            checkpoint_file = self.checkpoint_dir / f"{self.scan_id}_checkpoint.json"
            if checkpoint_file.exists():
                checkpoint_file.unlink()
        except Exception:
            pass

    def run(
        self,
        progress_cb: Optional[Callable[[ScanProgress], None]] = None
    ) -> ScanResult:
        """
        Run the scan pipeline with checkpoint support.
        If a checkpoint exists for this scan_id, discovery is skipped and the
        cached file list is used. After discovery, state is saved so that
        cancel/interrupt can be resumed later.
        """
        self._start_time = time.time()
        self.grouping.progress_cb = progress_cb

        result = ScanResult(
            scan_id=self.scan_id,
            config=self.config,
            started_at=datetime.now(),
        )

        try:
            # Try resume from checkpoint
            discovered_files = self._load_checkpoint()
            if discovered_files:
                if progress_cb:
                    progress_cb(self._create_progress(
                        phase="resuming",
                        phase_description="Resuming from checkpoint...",
                        files_found=len(discovered_files),
                        bytes_found=sum(f.size for f in discovered_files),
                    ))
                self._files_found = len(discovered_files)
                self._bytes_found = sum(f.size for f in discovered_files)
            else:
                # Phase 1: Discovery
                if progress_cb:
                    progress_cb(self._create_progress(
                        phase="discovering",
                        phase_description="Discovering files...",
                    ))

                discovered_files = self._discover_files(progress_cb)
                if self.checkpoint_dir and discovered_files:
                    self._save_checkpoint(discovered_files)

            if self._cancelled:
                result.errors.append("Scan cancelled by user")
                result.completed_at = datetime.now()
                return result

            if not discovered_files and self.config.roots:
                result.errors.append(
                    "No files were found. Check that the folder path is correct, "
                    "readable, and contains files (check filters: min size, extensions)."
                )

            # Phase 2-4: Grouping and hashing
            if progress_cb:
                progress_cb(self._create_progress(
                    phase="grouping",
                    phase_description="Finding duplicates...",
                    files_found=self._files_found,
                    bytes_found=self._bytes_found,
                ))

            duplicate_groups = self.grouping.find_duplicates(
                iter(discovered_files),
                self.scan_id,
                cancel_check=lambda: self._cancelled
            )

            result.files_scanned = self._files_found
            result.bytes_scanned = self._bytes_found
            result.duplicate_groups = duplicate_groups
            result.total_duplicates = sum(len(g.files) - 1 for g in duplicate_groups)
            result.total_reclaimable_bytes = sum(g.reclaimable_size for g in duplicate_groups)
            result.errors = self._errors

            if self._cancelled:
                result.errors.append("Scan cancelled by user")

        except Exception as e:
            self._errors.append(str(e))
            result.errors = self._errors
            if progress_cb:
                progress_cb(self._create_progress(
                    phase="error",
                    phase_description=f"Error: {str(e)}",
                    error_count=len(self._errors),
                    last_error=str(e),
                ))

        finally:
            result.completed_at = datetime.now()
            if not self._cancelled and result.errors == []:
                self._clear_checkpoint()
            if progress_cb:
                progress_cb(self._create_progress(
                    phase="complete" if not self._cancelled else "cancelled",
                    phase_description=f"Scan complete. Found {len(result.duplicate_groups)} duplicate groups.",
                    files_found=result.files_scanned,
                    groups_found=len(result.duplicate_groups),
                    duplicates_found=result.total_duplicates,
                ))

        return result


def quick_scan(
    path: Path | str,
    min_size: int = 1,
    progress_cb: Optional[Callable[[ScanProgress], None]] = None
) -> ScanResult:
    """
    Quick scan with default settings.
    
    Usage:
        result = quick_scan("/data", min_size=1024)
        print(f"Found {len(result.duplicate_groups)} duplicate groups")
    """
    config = ScanConfig(
        roots=[Path(path)],
        min_size_bytes=min_size,
    )
    
    pipeline = ScanPipeline(config)
    return pipeline.run(progress_cb)
