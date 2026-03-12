"""
DEDUP Scan Worker - Background scan execution.

Runs scans in a background thread to keep the UI responsive.
Provides progress callbacks and cancellation support.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Dict, Any

from ..engine.models import ScanConfig, ScanProgress, ScanResult, FileMetadata
from ..engine.pipeline import ScanPipeline, ResumableScanPipeline, StreamingScanPipeline
from .events import EventBus, ScanEvent, ScanEventType, get_event_bus


@dataclass
class ScanWorkerCallbacks:
    """Callbacks for scan progress."""
    on_progress: Optional[Callable[[ScanProgress], None]] = None
    on_complete: Optional[Callable[[ScanResult], None]] = None
    on_error: Optional[Callable[[str], None]] = None
    on_cancel: Optional[Callable[[], None]] = None


class ScanWorker:
    """
    Background worker for scan execution.
    
    Usage:
        worker = ScanWorker(config)
        worker.callbacks.on_progress = lambda p: print(f"{p.percent}%")
        worker.start()
        
        # Later...
        worker.cancel()
        worker.join()
    """
    
    def __init__(
        self,
        config: ScanConfig,
        event_bus: Optional[EventBus] = None,
        hash_cache_getter: Optional[Callable[[str], Optional[Dict[str, Any]]]] = None,
        hash_cache_setter: Optional[Callable[[FileMetadata], bool]] = None,
        checkpoint_dir: Optional[Path] = None,
        resume_scan_id: Optional[str] = None,
    ):
        self.config = config
        self.event_bus = event_bus or get_event_bus()
        self.callbacks = ScanWorkerCallbacks()
        self._hash_cache_getter = hash_cache_getter
        self._hash_cache_setter = hash_cache_setter
        self._checkpoint_dir = checkpoint_dir
        self._resume_scan_id = resume_scan_id

        self._pipeline: Optional[ScanPipeline] = None
        self._thread: Optional[threading.Thread] = None
        self._result: Optional[ScanResult] = None
        self._error: Optional[str] = None
        self._cancelled = False
        self._lock = threading.Lock()
    
    @property
    def is_running(self) -> bool:
        """Check if scan is running."""
        return self._thread is not None and self._thread.is_alive()
    
    @property
    def scan_id(self) -> Optional[str]:
        """Get the scan ID if started."""
        return self._pipeline.scan_id if self._pipeline else None
    
    def start(self) -> str:
        """
        Start the scan in a background thread.
        
        Returns:
            Scan ID
        """
        with self._lock:
            if self.is_running:
                raise RuntimeError("Scan already running")
            
            self._cancelled = False
            self._result = None
            self._error = None

            # Use streaming pipeline when use_streaming=True (bounded memory, no checkpoint)
            if self.config.use_streaming:
                self._pipeline = StreamingScanPipeline(
                    self.config,
                    hash_cache_getter=self._hash_cache_getter,
                    hash_cache_setter=self._hash_cache_setter,
                )
            # Use resumable pipeline when checkpoint_dir is set (save checkpoint on cancel)
            elif self._checkpoint_dir:
                cp_path = Path(self._checkpoint_dir)
                if self._resume_scan_id:
                    resume_config = ResumableScanPipeline.load_checkpoint_config(
                        cp_path, self._resume_scan_id
                    )
                    if resume_config is None:
                        raise ValueError(f"Checkpoint not found for scan {self._resume_scan_id}")
                    self._pipeline = ResumableScanPipeline(
                        resume_config,
                        scan_id=self._resume_scan_id,
                        checkpoint_dir=cp_path,
                        hash_cache_getter=self._hash_cache_getter,
                        hash_cache_setter=self._hash_cache_setter,
                    )
                else:
                    self._pipeline = ResumableScanPipeline(
                        self.config,
                        checkpoint_dir=cp_path,
                        hash_cache_getter=self._hash_cache_getter,
                        hash_cache_setter=self._hash_cache_setter,
                    )
            else:
                self._pipeline = ScanPipeline(
                    self.config,
                    hash_cache_getter=self._hash_cache_getter,
                    hash_cache_setter=self._hash_cache_setter,
                )
            scan_id = self._pipeline.scan_id
            
            # Start thread
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
            
            # Publish event
            self.event_bus.publish(ScanEvent(
                event_type=ScanEventType.SCAN_STARTED,
                scan_id=scan_id,
            ))
            
            return scan_id
    
    def _run(self):
        """Internal run method (executed in background thread)."""
        try:
            def on_progress(progress: ScanProgress):
                # Throttle progress updates (max 10 per second)
                current_time = time.time()
                if not hasattr(self, '_last_progress_time'):
                    self._last_progress_time = 0
                
                if current_time - self._last_progress_time >= 0.1:
                    self._last_progress_time = current_time
                    
                    # Call user callback
                    if self.callbacks.on_progress:
                        try:
                            self.callbacks.on_progress(progress)
                        except Exception:
                            pass
                    
                    # Publish event
                    self.event_bus.publish(ScanEvent(
                        event_type=ScanEventType.SCAN_PROGRESS,
                        scan_id=progress.scan_id,
                        payload=progress.to_dict(),
                    ))
            
            # Run the scan
            self._result = self._pipeline.run(progress_cb=on_progress)
            
            # Check if cancelled
            if self._cancelled:
                if self.callbacks.on_cancel:
                    try:
                        self.callbacks.on_cancel()
                    except Exception:
                        pass
                
                self.event_bus.publish(ScanEvent(
                    event_type=ScanEventType.SCAN_CANCELLED,
                    scan_id=self._pipeline.scan_id,
                ))
            else:
                # Success
                if self.callbacks.on_complete:
                    try:
                        self.callbacks.on_complete(self._result)
                    except Exception:
                        pass
                
                self.event_bus.publish(ScanEvent(
                    event_type=ScanEventType.SCAN_COMPLETED,
                    scan_id=self._pipeline.scan_id,
                    payload={"result": self._result.to_dict()},
                ))
        
        except Exception as e:
            self._error = str(e)
            
            if self.callbacks.on_error:
                try:
                    self.callbacks.on_error(self._error)
                except Exception:
                    pass
            
            self.event_bus.publish(ScanEvent(
                event_type=ScanEventType.SCAN_ERROR,
                scan_id=self._pipeline.scan_id if self._pipeline else "unknown",
                payload={"error": self._error},
            ))
    
    def cancel(self):
        """Request cancellation of the scan."""
        with self._lock:
            self._cancelled = True
            if self._pipeline:
                self._pipeline.cancel()
    
    def join(self, timeout: Optional[float] = None) -> bool:
        """
        Wait for the scan to complete.
        
        Args:
            timeout: Maximum time to wait (None = forever)
        
        Returns:
            True if scan completed, False if timed out
        """
        if self._thread:
            self._thread.join(timeout)
            return not self._thread.is_alive()
        return True
    
    def get_result(self) -> Optional[ScanResult]:
        """Get the scan result (if completed)."""
        return self._result
    
    def get_error(self) -> Optional[str]:
        """Get error message (if failed)."""
        return self._error
