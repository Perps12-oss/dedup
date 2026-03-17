"""
DEDUP Scan Worker - Background scan execution.

Runs scans in a background thread to keep the UI responsive.
Provides progress callbacks and cancellation support.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from ..engine.models import ScanConfig, ScanProgress, ScanResult
from ..engine.pipeline import ResumableScanPipeline, ScanPipeline
from .events import EventBus, ScanEvent, ScanEventType, get_event_bus

_log = logging.getLogger(__name__)


@dataclass
class ScanWorkerCallbacks:
    """Callbacks for scan progress."""
    on_progress: Optional[Callable[[ScanProgress], None]] = None
    on_complete: Optional[Callable[[ScanResult], None]] = None
    on_error: Optional[Callable[[str], None]] = None
    on_cancel: Optional[Callable[[], None]] = None


class CancellationToken:
    """Cooperative cancellation token shared with the worker pipeline."""

    def __init__(self):
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    def is_cancelled(self) -> bool:
        return self._event.is_set()


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
        persistence: Optional[Any] = None,
        hash_cache_getter: Optional[Callable[[str], Optional[Dict[str, Any]]]] = None,
        hash_cache_setter: Optional[Callable[[Any], bool]] = None,
        checkpoint_dir: Optional[Any] = None,
        resume_scan_id: Optional[str] = None,
    ):
        self.config = config
        self.event_bus = event_bus or get_event_bus()
        self.callbacks = ScanWorkerCallbacks()
        self.persistence = persistence
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
        self.cancellation_token = CancellationToken()
    
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

            # Use resumable pipeline when checkpoint_dir is set (save checkpoint on cancel)
            from pathlib import Path
            if self._checkpoint_dir:
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
                        persistence=self.persistence,
                        hash_cache_getter=self._hash_cache_getter,
                        hash_cache_setter=self._hash_cache_setter,
                    )
                else:
                    self._pipeline = ResumableScanPipeline(
                        self.config,
                        checkpoint_dir=cp_path,
                        persistence=self.persistence,
                        hash_cache_getter=self._hash_cache_getter,
                        hash_cache_setter=self._hash_cache_setter,
                    )
            else:
                self._pipeline = ScanPipeline(
                    self.config,
                    persistence=self.persistence,
                    hash_cache_getter=self._hash_cache_getter,
                    hash_cache_setter=self._hash_cache_setter,
                )
            scan_id = self._pipeline.scan_id
            
            # Start thread
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
            
            # Publish event
            self.event_bus.publish(ScanEvent(
                event_type=ScanEventType.SESSION_STARTED,
                scan_id=scan_id,
            ))

            self.event_bus.publish(ScanEvent(
                event_type=ScanEventType.SCAN_STARTED,
                scan_id=scan_id,
            ))
            
            return scan_id
    
    def _run(self):
        """Internal run method (executed in background thread)."""
        try:
            self._last_phase = None

            def on_progress(progress: ScanProgress):
                # Throttle progress updates (max 10 per second)
                current_time = time.time()
                if not hasattr(self, '_last_progress_time'):
                    self._last_progress_time = 0
                
                if current_time - self._last_progress_time >= 0.1:
                    self._last_progress_time = current_time
                    if progress.phase != self._last_phase:
                        if self._last_phase is not None:
                            self.event_bus.publish(ScanEvent(
                                event_type=ScanEventType.PHASE_COMPLETED,
                                scan_id=progress.scan_id,
                                payload={"phase": self._last_phase},
                            ))
                        self._last_phase = progress.phase
                        self.event_bus.publish(ScanEvent(
                            event_type=ScanEventType.PHASE_STARTED,
                            scan_id=progress.scan_id,
                            payload={"phase": progress.phase, "description": progress.phase_description},
                        ))
                    
                    # Call user callback
                    self._safe_callback("Progress", self.callbacks.on_progress, progress)
                    
                    # Publish event
                    self.event_bus.publish(ScanEvent(
                        event_type=ScanEventType.SCAN_PROGRESS,
                        scan_id=progress.scan_id,
                        payload=progress.to_dict(),
                    ))
                    self.event_bus.publish(ScanEvent(
                        event_type=ScanEventType.PHASE_PROGRESS,
                        scan_id=progress.scan_id,
                        payload=progress.to_dict(),
                    ))
                    self.event_bus.publish(ScanEvent(
                        event_type=ScanEventType.PHASE_CHECKPOINTED,
                        scan_id=progress.scan_id,
                        payload={"phase": progress.phase, "files_found": progress.files_found},
                    ))
            
            # Run the scan
            self._result = self._pipeline.run(
                progress_cb=on_progress,
                event_bus=self.event_bus,
            )
            
            # Check if cancelled
            if self._cancelled:
                self._safe_callback("Cancel", self.callbacks.on_cancel)

                self.event_bus.publish(ScanEvent(
                    event_type=ScanEventType.SESSION_CANCELLED,
                    scan_id=self._pipeline.scan_id,
                ))

                self.event_bus.publish(ScanEvent(
                    event_type=ScanEventType.SCAN_CANCELLED,
                    scan_id=self._pipeline.scan_id,
                ))
            elif self._result and self._result.errors:
                self._error = "; ".join(self._result.errors)
                self._safe_callback("Error", self.callbacks.on_error, self._error)
                self.event_bus.publish(ScanEvent(
                    event_type=ScanEventType.SESSION_FAILED,
                    scan_id=self._pipeline.scan_id,
                    payload={"error": self._error, "result": self._result.to_dict()},
                ))
                self.event_bus.publish(ScanEvent(
                    event_type=ScanEventType.SCAN_ERROR,
                    scan_id=self._pipeline.scan_id,
                    payload={"error": self._error, "result": self._result.to_dict()},
                ))
            else:
                # Success
                self._safe_callback("Complete", self.callbacks.on_complete, self._result)

                self.event_bus.publish(ScanEvent(
                    event_type=ScanEventType.SESSION_COMPLETED,
                    scan_id=self._pipeline.scan_id,
                    payload={"result": self._result.to_dict()},
                ))

                self.event_bus.publish(ScanEvent(
                    event_type=ScanEventType.SCAN_COMPLETED,
                    scan_id=self._pipeline.scan_id,
                    payload={"result": self._result.to_dict()},
                ))
        
        except Exception as e:
            self._error = str(e)
            _log.exception("Worker run failed: %s", e)
            self._safe_callback("Error", self.callbacks.on_error, self._error)

            self.event_bus.publish(ScanEvent(
                event_type=ScanEventType.SESSION_FAILED,
                scan_id=self._pipeline.scan_id if self._pipeline else "unknown",
                payload={"error": self._error},
            ))

            self.event_bus.publish(ScanEvent(
                event_type=ScanEventType.SCAN_ERROR,
                scan_id=self._pipeline.scan_id if self._pipeline else "unknown",
                payload={"error": self._error},
            ))
    
    def cancel(self):
        """Request cancellation of the scan."""
        with self._lock:
            self._cancelled = True
            self.cancellation_token.cancel()
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

    @staticmethod
    def _safe_callback(
        name: str,
        callback: Optional[Callable[..., None]],
        *args: Any,
    ) -> None:
        """Invoke a user callback; log and record diagnostics on failure without raising."""
        if callback is None:
            return
        try:
            callback(*args)
        except Exception as e:
            _log.warning("%s callback failed: %s", name, e, exc_info=True)
            try:
                from ..infrastructure.diagnostics import (
                    CATEGORY_CALLBACK,
                    get_diagnostics_recorder,
                )
                get_diagnostics_recorder().record(
                    CATEGORY_CALLBACK, f"{name} callback failed", str(e)
                )
            except Exception as diag_err:
                _log.debug("Diagnostics record failed: %s", diag_err)
