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

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional, Callable, List, Dict
import threading

from .models import (
    FileMetadata, DuplicateGroup, ScanConfig, ScanProgress,
    ScanResult, DeletionPlan, DeletionResult, DeletionPolicy
)
from .discovery import FileDiscovery, DiscoveryOptions
from .hashing import HashEngine
from .grouping import GroupingEngine
from .deletion import DeletionEngine


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
    
    def __post_init__(self):
        # Initialize components
        discovery_options = DiscoveryOptions.from_config(self.config)
        self.discovery = FileDiscovery(discovery_options)
        self.hash_engine = HashEngine.from_config(self.config)
        self.grouping = GroupingEngine(
            hash_engine=self.hash_engine,
            progress_cb=None,
        )
    
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
        
        result = ScanResult(
            scan_id=self.scan_id,
            config=self.config,
            started_at=datetime.now(),
        )
        
        try:
            # Phase 1: Discovery
            if progress_cb:
                progress_cb(self._create_progress(
                    phase="discovering",
                    phase_description="Discovering files...",
                ))
            
            discovered_files = self._discover_files(progress_cb)
            
            if self._cancelled:
                result.errors.append("Scan cancelled by user")
                result.completed_at = datetime.now()
                return result
            
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
            if progress_cb:
                progress_cb(self._create_progress(
                    phase="error",
                    phase_description=f"Error: {str(e)}",
                    error_count=len(self._errors),
                    last_error=str(e),
                ))
        
        finally:
            result.completed_at = datetime.now()
            
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
        
        for file in self.discovery.discover():
            if self._cancelled:
                break
            
            files.append(file)
            self._files_found += 1
            self._bytes_found += file.size
            
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
        engine = DeletionEngine()
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
        engine = DeletionEngine(dry_run=dry_run)
        return engine.execute_plan(plan, progress_cb)


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
