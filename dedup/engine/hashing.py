"""
DEDUP Hashing Engine - Layered hash computation with performance optimization.

Strategy:
1. Partial hash: Sample first + middle + last chunks (size-aware) for candidate reduction only.
   Never used alone for duplicate confirmation.
2. Full hash: Complete file hash; required to confirm duplicates. Safe for deletion decisions.

Partial hash is only for narrowing candidates; confirmation always uses full hash.
"""

from __future__ import annotations

import hashlib
import logging
import mmap
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

from .models import FileMetadata, ScanConfig

_log = logging.getLogger(__name__)


class HashStrategy(Enum):
    """Hash algorithm selection."""

    XXHASH64 = "xxhash64"  # Fastest, requires xxhash
    MD5 = "md5"  # Standard library, good speed
    SHA256 = "sha256"  # Cryptographic, slower
    BLAKE3 = "blake3"  # Fast cryptographic, requires blake3


@dataclass(slots=True, frozen=True)
class PartialHashSpec:
    """Sampling description for partial-hash candidate reduction."""

    strategy_name: str = "first_middle_last"
    bytes_sampled: int = 4096
    version: str = "v1"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategy_name": self.strategy_name,
            "bytes_sampled": self.bytes_sampled,
            "version": self.version,
        }


@dataclass(slots=True, frozen=True)
class FullHashSpec:
    """Confirmation-hash spec used for duplicate confirmation."""

    algorithm: str
    version: str = "v1"


@dataclass(slots=True, frozen=True)
class HashCacheKey:
    """Normalized key for durable hash-cache lookups."""

    path: str
    size: int
    mtime_ns: int
    algorithm: str
    strategy_version: str
    hash_kind: str


@dataclass(slots=True)
class HashPolicy:
    """Policy object that separates scheduling choices from hash execution."""

    algorithm: HashStrategy = HashStrategy.XXHASH64
    partial_spec: PartialHashSpec = field(default_factory=PartialHashSpec)
    full_workers: int = 4

    @classmethod
    def from_config(cls, config: ScanConfig) -> "HashPolicy":
        try:
            algorithm = HashStrategy(config.hash_algorithm)
        except ValueError:
            algorithm = HashStrategy.XXHASH64
        return cls(
            algorithm=algorithm,
            partial_spec=PartialHashSpec(bytes_sampled=config.partial_hash_bytes),
            full_workers=config.full_hash_workers,
        )


def _default_hash_metrics() -> Dict[str, int]:
    return {
        "hash_cache_hits": 0,
        "hash_cache_misses": 0,
        "partial_hash_computed": 0,
        "full_hash_computed": 0,
    }


@dataclass
class HashEngine:
    """
    Hash computation engine with layered strategy.

    For 1M+ files:
    - Uses memory-mapped files for large files (avoids loading into RAM)
    - Parallel hash workers
    - Caching to avoid re-hashing unchanged files
    """

    algorithm: HashStrategy = HashStrategy.XXHASH64
    partial_bytes: int = 4096
    workers: int = 4
    use_mmap: bool = True
    cache_getter: Optional[Callable[[str], Optional[Dict[str, Any]]]] = None
    cache_setter: Optional[Callable[[FileMetadata], bool]] = None
    policy: Optional[HashPolicy] = None

    # path -> (mtime_ns, size, hash); partial and full kept separate
    _partial_cache: Dict[str, Tuple[int, int, str]] = field(default_factory=dict, init=False, repr=False)
    _full_cache: Dict[str, Tuple[int, int, str]] = field(default_factory=dict, init=False, repr=False)
    _cache_lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _metrics: Dict[str, int] = field(default_factory=_default_hash_metrics, init=False, repr=False)
    # Resolved once: avoid import + branch on every _get_hasher() call (hot path).
    _hasher_factory: Callable[[], Any] = field(init=False, repr=False)
    progress_interval_ms: float = 500.0
    _last_progress_at_ms: float = field(default=0.0, init=False, repr=False)

    def __post_init__(self):
        if self.policy is None:
            self.policy = HashPolicy(
                algorithm=self.algorithm,
                partial_spec=PartialHashSpec(bytes_sampled=self.partial_bytes),
                full_workers=self.workers,
            )
        self._hasher_factory = self._resolve_hasher_factory()

    def _resolve_hasher_factory(self) -> Callable[[], Any]:
        """Select hasher constructor once at startup (partial + full hashing)."""
        algo = self.policy.algorithm if self.policy else self.algorithm
        if algo == HashStrategy.XXHASH64:
            try:
                import xxhash

                _log.debug("Using xxhash64 for hashing")
                return lambda: xxhash.xxh64()
            except ImportError:
                _log.warning("xxhash not available; falling back to MD5 for hashing")
                return hashlib.md5
        if algo == HashStrategy.BLAKE3:
            try:
                import blake3

                _log.debug("Using blake3 for hashing")
                return lambda: blake3.blake3()
            except ImportError:
                _log.warning("blake3 not available; falling back to MD5 for hashing")
                return hashlib.md5
        if algo == HashStrategy.SHA256:
            return hashlib.sha256
        # MD5 and any unknown value
        return hashlib.md5

    @classmethod
    def from_config(cls, config: ScanConfig) -> HashEngine:
        """Create hash engine from scan config."""
        policy = HashPolicy.from_config(config)
        return cls(
            algorithm=policy.algorithm,
            partial_bytes=config.partial_hash_bytes,
            workers=config.full_hash_workers,
            policy=policy,
        )

    @property
    def partial_spec(self) -> PartialHashSpec:
        return self.policy.partial_spec if self.policy else PartialHashSpec(bytes_sampled=self.partial_bytes)

    def _get_hasher(self):
        """Return a fresh hasher instance (factory resolved in __post_init__)."""
        return self._hasher_factory()

    def _check_partial_cache(self, path: str, mtime_ns: int, size: int) -> Optional[str]:
        """In-memory cache for partial hashes only."""
        with self._cache_lock:
            cached = self._partial_cache.get(path)
            if cached and cached[0] == mtime_ns and cached[1] == size:
                self._metrics["hash_cache_hits"] += 1
                return cached[2]
        return None

    def _update_partial_cache(self, path: str, mtime_ns: int, size: int, hash_value: str) -> None:
        with self._cache_lock:
            self._partial_cache[path] = (mtime_ns, size, hash_value)

    def _check_full_cache(self, path: str, mtime_ns: int, size: int) -> Optional[str]:
        """In-memory cache for full hashes only."""
        with self._cache_lock:
            cached = self._full_cache.get(path)
            if cached and cached[0] == mtime_ns and cached[1] == size:
                self._metrics["hash_cache_hits"] += 1
                return cached[2]
        return None

    def _update_full_cache(self, path: str, mtime_ns: int, size: int, hash_value: str) -> None:
        with self._cache_lock:
            self._full_cache[path] = (mtime_ns, size, hash_value)

    def _check_external_partial_cache(self, file: FileMetadata) -> Optional[str]:
        """Check persistence-backed cache for a valid partial hash."""
        if not self.cache_getter:
            return None
        try:
            cached = self.cache_getter(file.path)
            if not cached:
                return None
            if cached.get("size") != file.size or cached.get("mtime_ns") != file.mtime_ns:
                return None
            if cached.get("algorithm") not in (None, self.algorithm.value, "legacy"):
                return None
            if cached.get("strategy_version") not in (None, self.partial_spec.version, "v1"):
                return None
            return cached.get("hash_partial")
        except Exception:
            return None

    def _check_external_full_cache(self, file: FileMetadata) -> Optional[str]:
        """Check persistence-backed cache for a valid full hash."""
        if not self.cache_getter:
            return None
        try:
            cached = self.cache_getter(file.path)
            if not cached:
                return None
            if cached.get("size") != file.size or cached.get("mtime_ns") != file.mtime_ns:
                return None
            if cached.get("algorithm") not in (None, self.algorithm.value, "legacy"):
                return None
            return cached.get("hash_full")
        except Exception:
            return None

    def hash_partial(self, file: FileMetadata) -> Optional[str]:
        """
        Compute partial hash (first + middle + last chunks) for candidate reduction only.
        Not used for confirmation; full hash is required for that.
        Returns None if file cannot be read.
        """
        # Check cache first
        cached = self._check_partial_cache(file.path, file.mtime_ns, file.size)
        if cached:
            return cached
        cached_external = self._check_external_partial_cache(file)
        if cached_external:
            with self._cache_lock:
                self._metrics["hash_cache_hits"] += 1
            self._update_partial_cache(file.path, file.mtime_ns, file.size, cached_external)
            return cached_external
        with self._cache_lock:
            self._metrics["hash_cache_misses"] += 1

        try:
            path = Path(file.path)
            if not path.exists():
                return None

            hasher = self._get_hasher()
            size = file.size
            chunk = min(self.partial_spec.bytes_sampled, size)

            with open(path, "rb") as f:
                if size <= self.partial_spec.bytes_sampled:
                    data = f.read(size)
                    hasher.update(data)
                else:
                    # First chunk
                    data = f.read(chunk)
                    hasher.update(data)
                    # Middle chunk
                    if size > 2 * self.partial_spec.bytes_sampled:
                        f.seek((size - self.partial_spec.bytes_sampled) // 2)
                        data = f.read(self.partial_spec.bytes_sampled)
                        hasher.update(data)
                    # Last chunk
                    if size > self.partial_spec.bytes_sampled:
                        f.seek(max(0, size - self.partial_spec.bytes_sampled))
                        data = f.read(self.partial_spec.bytes_sampled)
                        hasher.update(data)

            hash_value = hasher.hexdigest()
            with self._cache_lock:
                self._metrics["partial_hash_computed"] += 1
            self._update_partial_cache(file.path, file.mtime_ns, file.size, hash_value)
            if self.cache_setter:
                try:
                    self.cache_setter(file.with_hash_partial(hash_value))
                except Exception:
                    pass
            return hash_value

        except (OSError, PermissionError, IOError):
            return None

    def hash_full(self, file: FileMetadata) -> Optional[str]:
        """
        Compute full hash of a file.

        Uses memory-mapped I/O for large files to avoid loading entire file into RAM.
        Returns None if file cannot be read.
        """
        try:
            path = Path(file.path)
            if not path.exists():
                return None
            mem_full = self._check_full_cache(file.path, file.mtime_ns, file.size)
            if mem_full:
                return mem_full
            cached_external = self._check_external_full_cache(file)
            if cached_external:
                with self._cache_lock:
                    self._metrics["hash_cache_hits"] += 1
                self._update_full_cache(file.path, file.mtime_ns, file.size, cached_external)
                return cached_external
            with self._cache_lock:
                self._metrics["hash_cache_misses"] += 1

            hasher = self._get_hasher()
            file_size = file.size

            with open(path, "rb") as f:
                # Use mmap for files larger than 1MB
                if self.use_mmap and file_size > 1024 * 1024:
                    try:
                        with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                            hasher.update(mm)
                    except (OSError, ValueError):
                        # Fallback to regular read
                        while True:
                            chunk = f.read(8192)
                            if not chunk:
                                break
                            hasher.update(chunk)
                else:
                    # Regular chunked read for smaller files
                    while True:
                        chunk = f.read(8192)
                        if not chunk:
                            break
                        hasher.update(chunk)

            hash_value = hasher.hexdigest()
            with self._cache_lock:
                self._metrics["full_hash_computed"] += 1
            self._update_full_cache(file.path, file.mtime_ns, file.size, hash_value)
            if self.cache_setter:
                try:
                    self.cache_setter(file.with_hash_full(hash_value))
                except Exception:
                    pass
            return hash_value

        except (OSError, PermissionError, IOError):
            return None

    def metrics_snapshot(self) -> Dict[str, int]:
        with self._cache_lock:
            return dict(self._metrics)

    def reset_metrics(self) -> None:
        with self._cache_lock:
            for key in self._metrics:
                self._metrics[key] = 0

    def _parallel_hash_batch(
        self,
        files: List[FileMetadata],
        progress_cb: Optional[Callable[[int], None]],
        transform: Callable[[FileMetadata], FileMetadata],
        pool_exception_message: str,
    ) -> Iterator[FileMetadata]:
        """Run per-file transforms in a thread pool; shared by partial and full batch hashers."""
        completed = 0
        lock = threading.Lock()

        def work(file: FileMetadata) -> FileMetadata:
            nonlocal completed
            result = transform(file)
            with lock:
                completed += 1
                if progress_cb:
                    now_ms = time.monotonic() * 1000.0
                    if now_ms - self._last_progress_at_ms >= self.progress_interval_ms:
                        progress_cb(completed)
                        self._last_progress_at_ms = now_ms
            return result

        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            futures = {executor.submit(work, f): f for f in files}
            for future in as_completed(futures):
                try:
                    yield future.result()
                except Exception:
                    file = futures[future]
                    yield file.with_error(pool_exception_message)

    def hash_batch_partial(
        self, files: List[FileMetadata], progress_cb: Optional[Callable[[int], None]] = None
    ) -> Iterator[FileMetadata]:
        """
        Compute partial hashes for a batch of files in parallel.

        Yields FileMetadata objects with hash_partial set.

        Args:
            files: Inputs to hash (partial layer).
            progress_cb: Receives completed count (throttled by ``progress_interval_ms``, default 500ms).

        Note:
            Tune ``HashEngine.progress_interval_ms`` to change how often the UI or pipeline is notified.
        """

        def transform(file: FileMetadata) -> FileMetadata:
            hash_value = self.hash_partial(file)
            if hash_value:
                return file.with_hash_partial(hash_value)
            return file.with_error("Failed to compute partial hash")

        yield from self._parallel_hash_batch(files, progress_cb, transform, "Hash computation failed")

    def hash_batch_full(
        self, files: List[FileMetadata], progress_cb: Optional[Callable[[int], None]] = None
    ) -> Iterator[FileMetadata]:
        """
        Compute full hashes for a batch of files in parallel.

        Yields FileMetadata objects with hash_full set.

        Args:
            files: Inputs to hash (full layer).
            progress_cb: Receives completed count (throttled by ``progress_interval_ms``).
        """

        def transform(file: FileMetadata) -> FileMetadata:
            hash_value = self.hash_full(file)
            if hash_value:
                return file.with_hash_full(hash_value)
            return file.with_error("Failed to compute full hash")

        yield from self._parallel_hash_batch(files, progress_cb, transform, "Full hash computation failed")


def group_by_partial_hash(
    files: List[FileMetadata], engine: HashEngine, progress_cb: Optional[Callable[[int], None]] = None
) -> Dict[str, List[FileMetadata]]:
    """
    Group files by partial hash.

    Returns only groups with 2+ files (potential duplicates).
    Singletons are filtered out as they cannot be duplicates.
    """
    # Compute partial hashes
    hashed_files = list(engine.hash_batch_partial(files, progress_cb))

    groups: Dict[str, List[FileMetadata]] = defaultdict(list)
    for file in hashed_files:
        if file.hash_partial:
            groups[file.hash_partial].append(file)

    return {k: v for k, v in groups.items() if len(v) >= 2}


def confirm_duplicates(
    candidate_groups: Dict[str, List[FileMetadata]],
    engine: HashEngine,
    progress_cb: Optional[Callable[[int], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> Dict[str, List[FileMetadata]]:
    """
    Confirm duplicates by computing full hashes.

    Takes groups with matching partial hashes and computes full hashes
    to eliminate false positives.
    """
    confirmed: Dict[str, List[FileMetadata]] = {}

    # Flatten all candidates
    all_candidates = []
    for group in candidate_groups.values():
        all_candidates.extend(group)

    if cancel_check and cancel_check():
        _log.info("Cancellation requested before full-hash confirmation")
        return {}

    # Compute full hashes
    hashed_files = list(engine.hash_batch_full(all_candidates, progress_cb))

    # Group by full hash
    for file in hashed_files:
        if file.hash_full:
            key = file.hash_full
            if key not in confirmed:
                confirmed[key] = []
            confirmed[key].append(file)

    # Filter to only true duplicates
    return {k: v for k, v in confirmed.items() if len(v) >= 2}
