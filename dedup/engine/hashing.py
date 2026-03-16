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
import mmap
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Iterator, List, Optional, Callable, Dict, Set, Tuple, Any
import threading

from .models import FileMetadata, ScanConfig


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
    
    # Cache: path -> (mtime_ns, size, hash) to avoid re-hashing
    _hash_cache: Dict[str, Tuple[int, int, str]] = None
    _cache_lock: threading.Lock = None
    _metrics: Dict[str, int] = None
    
    def __post_init__(self):
        if self._hash_cache is None:
            self._hash_cache = {}
        if self._cache_lock is None:
            self._cache_lock = threading.Lock()
        if self._metrics is None:
            self._metrics = {
                "hash_cache_hits": 0,
                "hash_cache_misses": 0,
                "partial_hash_computed": 0,
                "full_hash_computed": 0,
            }
        if self.policy is None:
            self.policy = HashPolicy(
                algorithm=self.algorithm,
                partial_spec=PartialHashSpec(bytes_sampled=self.partial_bytes),
                full_workers=self.workers,
            )
    
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
        """Get a hash object based on the selected algorithm."""
        if self.algorithm == HashStrategy.XXHASH64:
            try:
                import xxhash
                return xxhash.xxh64()
            except ImportError:
                pass
        elif self.algorithm == HashStrategy.BLAKE3:
            try:
                import blake3
                return blake3.blake3()
            except ImportError:
                pass
        
        # Fallback to MD5 (always available)
        return hashlib.md5()
    
    def _check_cache(self, path: str, mtime_ns: int, size: int) -> Optional[str]:
        """Check if we have a cached hash for this file."""
        with self._cache_lock:
            cached = self._hash_cache.get(path)
            if cached and cached[0] == mtime_ns and cached[1] == size:
                self._metrics["hash_cache_hits"] += 1
                return cached[2]
        return None
    
    def _update_cache(self, path: str, mtime_ns: int, size: int, hash_value: str):
        """Update the hash cache."""
        with self._cache_lock:
            self._hash_cache[path] = (mtime_ns, size, hash_value)

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
        cached = self._check_cache(file.path, file.mtime_ns, file.size)
        if cached:
            return cached
        cached_external = self._check_external_partial_cache(file)
        if cached_external:
            with self._cache_lock:
                self._metrics["hash_cache_hits"] += 1
            self._update_cache(file.path, file.mtime_ns, file.size, cached_external)
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
            
            with open(path, 'rb') as f:
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
            self._update_cache(file.path, file.mtime_ns, file.size, hash_value)
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
            cached_external = self._check_external_full_cache(file)
            if cached_external:
                with self._cache_lock:
                    self._metrics["hash_cache_hits"] += 1
                return cached_external
            with self._cache_lock:
                self._metrics["hash_cache_misses"] += 1
            
            hasher = self._get_hasher()
            file_size = file.size
            
            with open(path, 'rb') as f:
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
    
    def hash_batch_partial(
        self,
        files: List[FileMetadata],
        progress_cb: Optional[Callable[[int], None]] = None
    ) -> Iterator[FileMetadata]:
        """
        Compute partial hashes for a batch of files in parallel.
        
        Yields FileMetadata objects with hash_partial set.
        """
        results: List[FileMetadata] = []
        completed = [0]
        lock = threading.Lock()
        
        def hash_one(file: FileMetadata) -> FileMetadata:
            hash_value = self.hash_partial(file)
            if hash_value:
                result = file.with_hash_partial(hash_value)
            else:
                result = file.with_error("Failed to compute partial hash")
            
            with lock:
                completed[0] += 1
                if progress_cb and completed[0] % 10 == 0:
                    progress_cb(completed[0])
            
            return result
        
        # Use thread pool with bounded batches to avoid large future fan-out
        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            for batch in self._iter_batches(files, max(self.workers * 64, 256)):
                futures = {executor.submit(hash_one, f): f for f in batch}
                for future in as_completed(futures):
                    try:
                        result = future.result()
                        yield result
                    except Exception:
                        file = futures[future]
                        yield file.with_error("Hash computation failed")
    
    def hash_batch_full(
        self,
        files: List[FileMetadata],
        progress_cb: Optional[Callable[[int], None]] = None
    ) -> Iterator[FileMetadata]:
        """
        Compute full hashes for a batch of files in parallel.
        
        Yields FileMetadata objects with hash_full set.
        """
        completed = [0]
        lock = threading.Lock()
        
        def hash_one(file: FileMetadata) -> FileMetadata:
            hash_value = self.hash_full(file)
            if hash_value:
                result = file.with_hash_full(hash_value)
            else:
                result = file.with_error("Failed to compute full hash")
            
            with lock:
                completed[0] += 1
                if progress_cb and completed[0] % 10 == 0:
                    progress_cb(completed[0])
            
            return result
        
        # Use thread pool with bounded batches to avoid large future fan-out
        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            for batch in self._iter_batches(files, max(self.workers * 64, 256)):
                futures = {executor.submit(hash_one, f): f for f in batch}
                for future in as_completed(futures):
                    try:
                        result = future.result()
                        yield result
                    except Exception:
                        file = futures[future]
                        yield file.with_error("Full hash computation failed")

    @staticmethod
    def _iter_batches(files: List[FileMetadata], batch_size: int) -> Iterator[List[FileMetadata]]:
        """Yield bounded-size batches for async submission control."""
        for i in range(0, len(files), batch_size):
            yield files[i:i + batch_size]


def group_by_partial_hash(
    files: List[FileMetadata],
    engine: HashEngine,
    progress_cb: Optional[Callable[[int], None]] = None
) -> Dict[str, List[FileMetadata]]:
    """
    Group files by partial hash.
    
    Returns only groups with 2+ files (potential duplicates).
    Singletons are filtered out as they cannot be duplicates.
    """
    # Compute partial hashes
    hashed_files = list(engine.hash_batch_partial(files, progress_cb))
    
    # Group by partial hash
    groups: Dict[str, List[FileMetadata]] = {}
    for file in hashed_files:
        if file.hash_partial:
            key = file.hash_partial
            if key not in groups:
                groups[key] = []
            groups[key].append(file)
    
    # Filter to only groups with 2+ files
    return {k: v for k, v in groups.items() if len(v) >= 2}


def confirm_duplicates(
    candidate_groups: Dict[str, List[FileMetadata]],
    engine: HashEngine,
    progress_cb: Optional[Callable[[int], None]] = None
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
