"""
DEDUP Scan Coordinator - High-level scan management.

Manages multiple scans, history, and provides a simplified interface
for the UI layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Callable
from pathlib import Path

from ..engine.models import ScanConfig, ScanResult, ScanProgress, DeletionPlan, DeletionResult, DeletionPolicy
from ..infrastructure.persistence import Persistence, ScanStore
from ..infrastructure.config import Config, load_config
from .worker import ScanWorker
from .events import EventBus, get_event_bus


@dataclass
class ScanCoordinator:
    """
    High-level coordinator for scan operations.
    
    Provides a simplified interface for the UI:
    - Start/stop scans
    - Access scan history
    - Manage deletion operations
    
    Usage:
        coordinator = ScanCoordinator()
        
        def on_progress(progress):
            print(f"{progress.phase}: {progress.files_found} files")
        
        scan_id = coordinator.start_scan(
            roots=[Path("/data")],
            on_progress=on_progress
        )
    """
    
    persistence: Persistence = field(default_factory=lambda: Persistence(
        db_path=Path.home() / '.local' / 'share' / 'dedup' / 'dedup.db'
    ))
    event_bus: EventBus = field(default_factory=get_event_bus)
    config: Config = field(default_factory=load_config)
    
    _active_worker: Optional[ScanWorker] = None
    _last_result: Optional[ScanResult] = None
    
    def start_scan(
        self,
        roots: List[Path],
        on_progress: Optional[Callable[[ScanProgress], None]] = None,
        on_complete: Optional[Callable[[ScanResult], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
        **scan_options
    ) -> str:
        """
        Start a new scan.
        
        Args:
            roots: Directories to scan
            on_progress: Progress callback
            on_complete: Completion callback
            on_error: Error callback
            **scan_options: Additional ScanConfig options
        
        Returns:
            Scan ID
        """
        # Cancel any existing scan
        if self._active_worker and self._active_worker.is_running:
            self._active_worker.cancel()
            self._active_worker.join(timeout=5.0)
        
        # Create config
        scan_config = ScanConfig(
            roots=roots,
            min_size_bytes=scan_options.get('min_size', self.config.default_min_size),
            include_hidden=scan_options.get('include_hidden', self.config.default_include_hidden),
            follow_symlinks=scan_options.get('follow_symlinks', self.config.default_follow_symlinks),
            hash_algorithm=scan_options.get('hash_algorithm', self.config.default_hash_algorithm),
            full_hash_workers=self.config.max_workers,
            batch_size=self.config.batch_size,
        )
        
        # Create and start worker
        worker = ScanWorker(scan_config, self.event_bus)
        worker.callbacks.on_progress = on_progress
        worker.callbacks.on_complete = self._on_scan_complete_wrapper(on_complete)
        worker.callbacks.on_error = on_error
        
        self._active_worker = worker
        scan_id = worker.start()
        
        return scan_id
    
    def _on_scan_complete_wrapper(
        self,
        user_callback: Optional[Callable[[ScanResult], None]]
    ) -> Callable[[ScanResult], None]:
        """Wrap user callback to save result."""
        def wrapper(result: ScanResult):
            self._last_result = result
            
            # Save to history
            try:
                self.persistence.save_scan(result)
            except Exception:
                pass
            
            # Call user callback
            if user_callback:
                user_callback(result)
        
        return wrapper
    
    def cancel_scan(self):
        """Cancel the active scan."""
        if self._active_worker:
            self._active_worker.cancel()
    
    @property
    def is_scanning(self) -> bool:
        """Check if a scan is in progress."""
        return self._active_worker is not None and self._active_worker.is_running
    
    def get_active_scan_id(self) -> Optional[str]:
        """Get the ID of the active scan."""
        return self._active_worker.scan_id if self._active_worker else None
    
    def get_last_result(self) -> Optional[ScanResult]:
        """Get the result of the last completed scan."""
        return self._last_result
    
    def get_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get scan history."""
        try:
            return self.persistence.list_scans(limit=limit)
        except Exception:
            return []
    
    def load_scan(self, scan_id: str) -> Optional[ScanResult]:
        """Load a scan result by ID."""
        try:
            return self.persistence.get_scan(scan_id)
        except Exception:
            return None
    
    def delete_scan(self, scan_id: str) -> bool:
        """Delete a scan from history."""
        try:
            return self.persistence.delete_scan(scan_id)
        except Exception:
            return False
    
    def create_deletion_plan(
        self,
        result: Optional[ScanResult] = None,
        keep_strategy: str = "first",
        group_keep_paths: Optional[Dict[str, str]] = None,
    ) -> Optional[DeletionPlan]:
        """
        Create a deletion plan from scan results.
        
        Args:
            result: Scan result (uses last result if None)
            keep_strategy: Which file to keep in each group (if group_keep_paths not set)
            group_keep_paths: Optional group_id -> path to keep (overrides strategy)
        
        Returns:
            DeletionPlan or None
        """
        result = result or self._last_result
        if not result:
            return None
        
        from ..engine.deletion import DeletionEngine
        engine = DeletionEngine()
        return engine.create_plan_from_groups(
            scan_id=result.scan_id,
            groups=result.duplicate_groups,
            policy=DeletionPolicy(self.config.default_deletion_policy),
            keep_strategy=keep_strategy,
            group_keep_paths=group_keep_paths,
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
            plan: DeletionPlan to execute
            dry_run: Preview mode (no actual deletion)
            progress_cb: Progress callback
        
        Returns:
            DeletionResult
        """
        from ..engine.deletion import DeletionEngine
        
        engine = DeletionEngine(dry_run=dry_run)
        result = engine.execute_plan(plan, progress_cb)
        
        # Log deletions
        for file_path in result.deleted_files:
            self.persistence.log_deletion(
                scan_id=plan.scan_id,
                file_path=file_path,
                policy=plan.policy.value,
                success=True,
            )
        
        for failure in result.failed_files:
            self.persistence.log_deletion(
                scan_id=plan.scan_id,
                file_path=failure['path'],
                policy=plan.policy.value,
                success=False,
                error_message=failure.get('error'),
            )
        
        return result
    
    def get_recent_folders(self) -> List[str]:
        """Get list of recently scanned folders."""
        return self.config.recent_folders
    
    def add_recent_folder(self, folder: Path):
        """Add a folder to recent folders."""
        from ..infrastructure.config import add_recent_folder, save_config
        
        self.config = add_recent_folder(self.config, folder)
        save_config(self.config)
