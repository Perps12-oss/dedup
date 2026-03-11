"""
DEDUP File Discovery - Streaming file discovery with memory efficiency.

Designed for 1M+ file datasets:
- Uses generators for streaming (not loading all paths into memory)
- Parallel directory traversal with thread pool
- Respects exclusion patterns
- Handles permission errors gracefully
"""

from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Optional, Set, Callable, List, Dict
from queue import Queue
import threading

from .models import FileMetadata, ScanConfig

# Sentinel for result_queue: worker signals completion (not a FileMetadata)
_WORKER_DONE = object()


@dataclass(slots=True)
class DiscoveryOptions:
    """Options for file discovery."""
    roots: List[Path]
    min_size_bytes: int = 1
    max_size_bytes: Optional[int] = None
    include_hidden: bool = False
    follow_symlinks: bool = False
    allowed_extensions: Optional[Set[str]] = None
    exclude_dirs: Set[str] = field(default_factory=set)
    max_workers: int = 8
    
    @classmethod
    def from_config(cls, config: ScanConfig) -> DiscoveryOptions:
        """Create options from scan config."""
        return cls(
            roots=config.roots,
            min_size_bytes=config.min_size_bytes,
            max_size_bytes=config.max_size_bytes,
            include_hidden=config.include_hidden,
            follow_symlinks=config.follow_symlinks,
            allowed_extensions=config.allowed_extensions,
            exclude_dirs=config.exclude_dirs,
            max_workers=config.full_hash_workers,
        )


class FileDiscovery:
    """
    Streaming file discovery engine.
    
    Memory-efficient design for large datasets:
    - Uses generators to yield files as they're found
    - Parallel directory traversal
    - Respects cancellation via callback
    """
    
    def __init__(self, options: DiscoveryOptions):
        self.options = options
        self._cancelled = False
        self._stats = {
            "dirs_scanned": 0,
            "files_found": 0,
            "files_filtered": 0,
            "errors": 0,
        }
    
    def cancel(self):
        """Request cancellation of discovery."""
        self._cancelled = True
    
    @property
    def is_cancelled(self) -> bool:
        return self._cancelled
    
    def get_stats(self) -> Dict[str, int]:
        """Get discovery statistics."""
        return self._stats.copy()
    
    def discover(self, progress_cb: Optional[Callable[[FileMetadata], None]] = None) -> Iterator[FileMetadata]:
        """
        Discover files using parallel traversal.
        
        Yields FileMetadata objects as they are discovered.
        This is a generator - memory usage stays constant regardless of dataset size.
        """
        # Use a queue to collect results from worker threads
        result_queue: Queue[Optional[FileMetadata]] = Queue(maxsize=1000)
        work_queue: Queue[Optional[Path]] = Queue()
        
        # Add initial roots to work queue
        for root in self.options.roots:
            work_queue.put(root)
        # Signal workers to stop when no more work: one SENTINEL per worker
        WORK_SENTINEL = None
        num_workers = min(self.options.max_workers, 4)
        for _ in range(num_workers):
            work_queue.put(WORK_SENTINEL)
        
        # Track active workers
        active_workers = threading.Lock()
        worker_count = [0]
        
        def worker():
            """Worker thread that processes directories."""
            with active_workers:
                worker_count[0] += 1
            
            try:
                while not self._cancelled:
                    try:
                        directory = work_queue.get(timeout=0.1)
                        if directory is WORK_SENTINEL:
                            work_queue.put(WORK_SENTINEL)  # Propagate to other workers
                            break
                    except Exception:
                        continue
                    
                    try:
                        self._scan_directory(directory, work_queue, result_queue)
                    except Exception:
                        self._stats["errors"] += 1
            finally:
                with active_workers:
                    worker_count[0] -= 1
                result_queue.put(_WORKER_DONE)
        
        # Start worker threads
        threads = []
        for _ in range(num_workers):
            t = threading.Thread(target=worker)
            t.daemon = True
            t.start()
            threads.append(t)
        
        try:
            # Yield results as they come in
            finished_workers = 0
            while not self._cancelled:
                try:
                    metadata = result_queue.get(timeout=0.1)
                    if metadata is _WORKER_DONE:
                        finished_workers += 1
                        if finished_workers >= num_workers:
                            break
                    elif metadata is not None and metadata is not _WORKER_DONE:
                        self._stats["files_found"] += 1
                        if progress_cb:
                            try:
                                progress_cb(metadata)
                            except Exception:
                                pass
                        yield metadata
                except Exception:
                    if finished_workers >= num_workers:
                        break
        finally:
            # Wait for workers to finish (they received SENTINELs from initial queue)
            for t in threads:
                t.join(timeout=1.0)
    
    def _scan_directory(
        self,
        directory: Path,
        work_queue: Queue[Optional[Path]],
        result_queue: Queue[Optional[FileMetadata]]
    ):
        """Scan a single directory and queue results."""
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    if self._cancelled:
                        return
                    
                    try:
                        name = entry.name
                        
                        # Skip hidden files/directories
                        if not self.options.include_hidden and name.startswith('.'):
                            continue
                        
                        # Handle directories
                        if entry.is_dir(follow_symlinks=self.options.follow_symlinks):
                            if name not in self.options.exclude_dirs:
                                work_queue.put(Path(entry.path))
                            continue
                        
                        # Handle files
                        if not entry.is_file(follow_symlinks=self.options.follow_symlinks):
                            continue
                        
                        # Get file stats
                        st = entry.stat(follow_symlinks=self.options.follow_symlinks)
                        size = st.st_size
                        
                        # Size filters
                        if size < self.options.min_size_bytes:
                            continue
                        if self.options.max_size_bytes and size > self.options.max_size_bytes:
                            continue
                        
                        # Extension filter
                        if self.options.allowed_extensions:
                            ext = os.path.splitext(name)[1].lower().lstrip('.')
                            if ext not in self.options.allowed_extensions:
                                continue
                        
                        # Create metadata
                        mtime_ns = getattr(st, 'st_mtime_ns', int(st.st_mtime * 1_000_000_000))
                        metadata = FileMetadata(
                            path=str(Path(entry.path).resolve()),
                            size=size,
                            mtime_ns=mtime_ns,
                            inode=st.st_ino,
                        )
                        
                        result_queue.put(metadata)
                        
                    except (OSError, PermissionError) as e:
                        self._stats["errors"] += 1
                        continue
                        
        except (OSError, PermissionError):
            self._stats["errors"] += 1
        except Exception:
            self._stats["errors"] += 1
        
        self._stats["dirs_scanned"] += 1
    
    def discover_batch(
        self,
        batch_size: int = 1000,
        progress_cb: Optional[Callable[[int], None]] = None
    ) -> Iterator[List[FileMetadata]]:
        """
        Discover files in batches.
        
        Yields lists of FileMetadata objects.
        More efficient for downstream processing.
        """
        batch: List[FileMetadata] = []
        total = 0
        
        for metadata in self.discover():
            batch.append(metadata)
            
            if len(batch) >= batch_size:
                total += len(batch)
                if progress_cb:
                    progress_cb(total)
                yield batch
                batch = []
        
        # Yield remaining files
        if batch:
            total += len(batch)
            if progress_cb:
                progress_cb(total)
            yield batch


def quick_discover(
    path: Path,
    min_size: int = 1,
    progress_cb: Optional[Callable[[FileMetadata], None]] = None
) -> Iterator[FileMetadata]:
    """
    Quick file discovery with default options.
    
    Usage:
        for file in quick_discover(Path("/data"), min_size=1024):
            print(file.path)
    """
    options = DiscoveryOptions(
        roots=[path],
        min_size_bytes=min_size,
    )
    discovery = FileDiscovery(options)
    yield from discovery.discover(progress_cb)
