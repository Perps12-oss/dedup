"""
DEDUP File Discovery - Streaming file discovery with memory efficiency.

Designed for 1M+ file datasets:
- Uses generators for streaming (not loading all paths into memory)
- Parallel directory traversal with thread pool
- Respects exclusion patterns
- Handles permission errors gracefully
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from queue import Empty, Queue
from typing import Callable, Dict, Iterator, List, Optional, Set, Tuple

_log = logging.getLogger(__name__)

from .discovery_compat import normalize_discovery_path
from .models import FileMetadata, FileRecord, ScanConfig

try:
    from ..infrastructure.profiler import measure
except ImportError:
    from contextlib import nullcontext as _nc

    def measure(_name: str):
        return _nc()


@dataclass(slots=True)
class DiscoveryOptions:
    """
    Options for file discovery.
    resolve_paths=False (default) keeps the discovery hot path minimal; paths
    are used as returned by the OS. Set True only when canonical paths are required.
    """

    roots: List[Path]
    min_size_bytes: int = 1
    max_size_bytes: Optional[int] = None
    include_hidden: bool = False
    follow_symlinks: bool = False
    scan_subfolders: bool = True
    allowed_extensions: Optional[Set[str]] = None
    # Matches directory *names* only (last path segment), not full paths — e.g.
    # {'Downloads'} excludes every folder named Downloads under the scan roots.
    exclude_dirs: Set[str] = field(default_factory=set)
    # Absolute or project-root paths; resolved and normalized at discovery start. Skips files
    # under those paths and does not recurse into excluded directories.
    exclude_paths: Set[str] = field(default_factory=set)
    max_workers: int = 8
    resolve_paths: bool = False

    @classmethod
    def from_config(cls, config: ScanConfig) -> DiscoveryOptions:
        """Create options from scan config."""
        discovery_workers = getattr(config, "discovery_max_workers", None)
        if discovery_workers is None or discovery_workers <= 0:
            discovery_workers = config.full_hash_workers
        return cls(
            roots=config.roots,
            min_size_bytes=config.min_size_bytes,
            max_size_bytes=config.max_size_bytes,
            include_hidden=config.include_hidden,
            follow_symlinks=config.follow_symlinks,
            scan_subfolders=config.scan_subfolders,
            allowed_extensions=config.allowed_extensions,
            exclude_dirs=config.exclude_dirs,
            exclude_paths=getattr(config, "exclude_paths", None) or set(),
            max_workers=discovery_workers,
            resolve_paths=getattr(config, "resolve_paths", False),
        )


@dataclass(slots=True)
class DiscoveryCursor:
    """Chunk cursor for durable discovery ingestion."""

    files_emitted: int = 0


@dataclass(slots=True)
class DiscoveryStats:
    """Summary counters emitted by chunked discovery."""

    files_found: int = 0
    bytes_found: int = 0


class FileDiscovery:
    """
    Streaming file discovery engine.

    Memory-efficient design for large datasets:
    - Uses generators to yield files as they're found
    - Parallel directory traversal
    - Respects cancellation via callback
    """

    def __init__(
        self,
        options: DiscoveryOptions,
        *,
        prior_session_id: Optional[str] = None,
        prior_dir_mtimes: Optional[Dict[str, int]] = None,
        get_prior_files_under_dir: Optional[Callable[[str], Iterator[FileMetadata]]] = None,
        dir_mtimes_sink: Optional[Dict[str, int]] = None,
    ):
        self.options = options
        self._cancelled = False
        self._stats_lock = threading.Lock()
        self._stats = {
            "dirs_scanned": 0,
            "dirs_reused": 0,
            "dirs_skipped_via_manifest": 0,
            "files_found": 0,
            "files_discovered_fresh": 0,
            "files_reused_from_prior_inventory": 0,
            "files_filtered": 0,
            "stat_calls": 0,
            "resolve_calls": 0,
            "errors": 0,
        }
        self._prior_session_id = prior_session_id
        self._prior_dir_mtimes = (
            {normalize_discovery_path(path): mtime for path, mtime in prior_dir_mtimes.items()}
            if prior_dir_mtimes
            else None
        )
        self._get_prior_files_under_dir = get_prior_files_under_dir
        self._dir_mtimes_sink = dir_mtimes_sink if dir_mtimes_sink is not None else {}
        self._dir_mtimes_lock = threading.Lock()
        self._exclude_paths_normalized: Set[str] = set()
        for raw in self.options.exclude_paths:
            try:
                self._exclude_paths_normalized.add(normalize_discovery_path(str(Path(raw).resolve())))
            except OSError:
                self._exclude_paths_normalized.add(normalize_discovery_path(str(raw)))

    def _path_excluded(self, path_str: str) -> bool:
        """True if path matches a configured exclude_paths entry (after resolve + normalize)."""
        if not self._exclude_paths_normalized:
            return False
        try:
            key = normalize_discovery_path(str(Path(path_str).resolve()))
        except OSError:
            key = normalize_discovery_path(path_str)
        return key in self._exclude_paths_normalized

    def cancel(self):
        """Request cancellation of discovery."""
        self._cancelled = True

    def _inc_stat(self, key: str, delta: int = 1) -> None:
        with self._stats_lock:
            self._stats[key] += delta

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled

    def get_stats(self) -> Dict[str, int]:
        """Get discovery statistics."""
        with self._stats_lock:
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

        # Add initial roots
        for root in self.options.roots:
            work_queue.put(root)

        WORK_SENTINEL = None
        configured = getattr(self.options, "max_workers", 4)
        cpu_count = os.cpu_count() or 4
        if configured is None or configured <= 0:
            num_workers = min(8, max(2, cpu_count))
        else:
            num_workers = configured
        done_event = threading.Event()

        def worker():
            while not self._cancelled:
                try:
                    directory = work_queue.get(timeout=0.1)
                except Empty:
                    continue

                try:
                    if directory is WORK_SENTINEL:
                        return
                    self._scan_directory(directory, work_queue, result_queue)
                except Exception:
                    self._inc_stat("errors")
                finally:
                    work_queue.task_done()

        # Start workers
        threads = []
        for _ in range(num_workers):
            t = threading.Thread(target=worker, daemon=True)
            t.start()
            threads.append(t)

        # Monitor queue completion (all discovered subdirs processed too)
        def monitor_done():
            try:
                work_queue.join()
            finally:
                done_event.set()

        monitor = threading.Thread(target=monitor_done, daemon=True)
        monitor.start()

        try:
            while not self._cancelled:
                try:
                    metadata = result_queue.get(timeout=0.1)
                    if metadata is not None:
                        self._inc_stat("files_found")
                        if progress_cb:
                            try:
                                progress_cb(metadata)
                            except Exception:
                                pass
                        yield metadata
                except Empty:
                    if done_event.is_set() and result_queue.empty():
                        break
        finally:
            # Stop workers cleanly
            for _ in range(num_workers):
                work_queue.put(WORK_SENTINEL)
            # Ensure sentinels are consumed when not cancelled.
            # If cancelled, workers may exit before draining the queue.
            if not self._cancelled:
                work_queue.join()
            for t in threads:
                t.join(timeout=1.0)

    def _scan_directory(
        self, directory: Path, work_queue: Queue[Optional[Path]], result_queue: Queue[Optional[FileMetadata]]
    ):
        """Scan a single directory and queue results."""
        try:
            if self._path_excluded(str(directory)):
                self._inc_stat("dirs_scanned")
                return

            dir_mtime_ns: Optional[int] = None
            try:
                dir_stat = directory.stat(follow_symlinks=self.options.follow_symlinks)
                dir_mtime_ns = getattr(
                    dir_stat,
                    "st_mtime_ns",
                    int(dir_stat.st_mtime * 1_000_000_000),
                )
                with self._dir_mtimes_lock:
                    self._dir_mtimes_sink[str(directory)] = dir_mtime_ns
            except (OSError, PermissionError):
                dir_mtime_ns = None

            dir_key = normalize_discovery_path(str(directory))
            if (
                self._prior_session_id
                and self._prior_dir_mtimes is not None
                and self._get_prior_files_under_dir is not None
                and dir_mtime_ns is not None
            ):
                prior_mtime_ns = self._prior_dir_mtimes.get(dir_key)
                if prior_mtime_ns is not None and prior_mtime_ns == dir_mtime_ns:
                    for metadata in self._get_prior_files_under_dir(str(directory)):
                        if self._cancelled:
                            return
                        self._inc_stat("files_reused_from_prior_inventory")
                        result_queue.put(metadata)
                    self._inc_stat("dirs_reused")
                    self._inc_stat("dirs_skipped_via_manifest")
                    return

            # Use str() for Windows/long-path compatibility with os.scandir
            with os.scandir(str(directory)) as entries:
                for entry in entries:
                    if self._cancelled:
                        return

                    try:
                        name = entry.name

                        # Skip hidden files/directories
                        if not self.options.include_hidden and name.startswith("."):
                            continue

                        # Handle directories (recurse only if scan_subfolders)
                        if entry.is_dir(follow_symlinks=self.options.follow_symlinks):
                            if (
                                self.options.scan_subfolders
                                and name not in self.options.exclude_dirs
                                and not self._path_excluded(entry.path)
                            ):
                                work_queue.put(Path(entry.path))
                            continue

                        # Handle files
                        if not entry.is_file(follow_symlinks=self.options.follow_symlinks):
                            continue

                        # Get file stats
                        self._inc_stat("stat_calls")
                        with measure("discovery.stat"):
                            st = entry.stat(follow_symlinks=self.options.follow_symlinks)
                        size = st.st_size

                        # Size filters
                        if size < self.options.min_size_bytes:
                            continue
                        if self.options.max_size_bytes and size > self.options.max_size_bytes:
                            continue

                        # Extension filter
                        if self.options.allowed_extensions:
                            ext = os.path.splitext(name)[1].lower().lstrip(".")
                            if ext not in self.options.allowed_extensions:
                                continue

                        # Create metadata; avoid resolve/measure when not needed (hot path).
                        mtime_ns = getattr(st, "st_mtime_ns", int(st.st_mtime * 1_000_000_000))
                        if self.options.resolve_paths:
                            self._inc_stat("resolve_calls")
                            with measure("discovery.resolve"):
                                path_str = str(Path(entry.path).resolve())
                        else:
                            path_str = entry.path
                        if self._path_excluded(path_str):
                            continue
                        metadata = FileMetadata(
                            path=path_str,
                            size=size,
                            mtime_ns=mtime_ns,
                            inode=st.st_ino,
                        )

                        self._inc_stat("files_discovered_fresh")
                        result_queue.put(metadata)

                    except (OSError, PermissionError):
                        self._inc_stat("errors")
                        continue

        except (OSError, PermissionError):
            self._inc_stat("errors")
        except Exception:
            self._inc_stat("errors")
        finally:
            self._inc_stat("dirs_scanned")

    def discover_batch(
        self, batch_size: int = 1000, progress_cb: Optional[Callable[[int], None]] = None
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
    path: Path, min_size: int = 1, progress_cb: Optional[Callable[[FileMetadata], None]] = None
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


class DiscoveryService:
    """
    Chunked wrapper over FileDiscovery for persistence-backed pipeline phases.

    A single long-lived instance keeps a streaming iterator across ``discover_chunk``
    calls so each chunk continues where the last left off (linear total work).

    If the service is **recreated** while resuming with ``cursor.files_emitted > 0``,
    the new instance will re-advance the iterator by skipping that many files from
    the start of a fresh walk — worst-case O(files_emitted) work per chunk until the
    cursor catches up. Prefer reusing one ``DiscoveryService`` for a session, or
    persist enough state to rebuild the same iterator.
    """

    def __init__(self, options: DiscoveryOptions):
        self.options = options
        self.discovery = FileDiscovery(options)
        # Single streaming iterator across chunk calls — avoids O(n²) re-walk per chunk.
        self._chunk_iter: Optional[Iterator[FileMetadata]] = None

    def cancel(self) -> None:
        self.discovery.cancel()
        self._chunk_iter = None

    def discover_chunk(
        self,
        cursor: Optional[DiscoveryCursor] = None,
        max_items: int = 1000,
    ) -> Tuple[List[FileRecord], Optional[DiscoveryCursor], DiscoveryStats]:
        cursor = cursor or DiscoveryCursor()
        batch: List[FileRecord] = []
        stats = DiscoveryStats()

        if self._chunk_iter is None:
            if cursor.files_emitted > 0:
                _log.warning(
                    "Resuming discovery with files_emitted=%d on a new or reset iterator; "
                    "skipping that many entries from the start of the walk",
                    cursor.files_emitted,
                )
            self._chunk_iter = self.discovery.discover()
            for _ in range(cursor.files_emitted):
                try:
                    next(self._chunk_iter)
                except StopIteration:
                    self._chunk_iter = None
                    return [], None, stats

        while len(batch) < max_items:
            try:
                file = next(self._chunk_iter)  # type: ignore[arg-type]
            except StopIteration:
                self._chunk_iter = None
                if not batch:
                    return [], None, stats
                return batch, None, stats
            batch.append(FileRecord.from_file_metadata(file))
            stats.files_found += 1
            stats.bytes_found += file.size
            cursor.files_emitted += 1

        return batch, cursor, stats
