"""
DEDUP Grouping Engine - File grouping and duplicate detection.

Groups files by content hash to identify duplicates.
Uses a two-phase approach:
1. Group by size (cheap, eliminates most non-duplicates)
2. Group by hash (confirms actual duplicates)
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Iterator, Optional, Callable, Set
import time

from .models import FileMetadata, DuplicateGroup, ScanProgress
from .hashing import HashEngine, group_by_partial_hash, confirm_duplicates


@dataclass
class GroupingEngine:
    """
    Groups files to identify duplicates.
    
    Uses a multi-phase approach for efficiency:
    1. Size grouping (eliminates unique sizes)
    2. Partial hash grouping (eliminates most non-duplicates)
    3. Full hash confirmation (confirms actual duplicates)
    """
    
    hash_engine: HashEngine
    progress_cb: Optional[Callable[[ScanProgress], None]] = None

    def _adaptive_refine_partial_groups(
        self,
        groups: Dict[str, List[FileMetadata]],
        scan_id: str,
    ) -> Dict[str, List[FileMetadata]]:
        """
        Refine large candidate groups with stronger partial hashing before full hash.
        This reduces expensive full hashes on very large files.
        """
        large_candidates: List[FileMetadata] = []
        passthrough: Dict[str, List[FileMetadata]] = {}

        for key, files in groups.items():
            if not files:
                continue
            file_size = files[0].size
            if len(files) >= 3 and file_size >= 32 * 1024 * 1024:
                large_candidates.extend(files)
            else:
                passthrough[key] = files

        if not large_candidates:
            return groups

        stronger_engine = HashEngine(
            algorithm=self.hash_engine.algorithm,
            partial_bytes=max(self.hash_engine.partial_bytes * 8, 64 * 1024),
            workers=self.hash_engine.workers,
            use_mmap=self.hash_engine.use_mmap,
            cache_getter=self.hash_engine.cache_getter,
            cache_setter=self.hash_engine.cache_setter,
        )

        if self.progress_cb:
            self.progress_cb(ScanProgress(
                scan_id=scan_id,
                phase="hashing_partial",
                phase_description="Refining large candidate groups with stronger partial hashing...",
            ))

        refined = group_by_partial_hash(
            large_candidates,
            stronger_engine,
            progress_cb=lambda n: self._on_hash_progress(scan_id, "hashing_partial", n),
        )

        combined: Dict[str, List[FileMetadata]] = {}
        combined.update(passthrough)
        combined.update(refined)
        return combined
    
    def group_by_size(
        self,
        files: Iterator[FileMetadata],
        scan_id: str
    ) -> Dict[int, List[FileMetadata]]:
        """
        Group files by size.
        
        Files with unique sizes cannot be duplicates, so they're filtered out.
        This is very fast and eliminates most files.
        """
        size_groups: Dict[int, List[FileMetadata]] = defaultdict(list)
        file_count = 0
        
        for file in files:
            size_groups[file.size].append(file)
            file_count += 1
            
            # Report progress periodically
            if file_count % 10000 == 0 and self.progress_cb:
                progress = ScanProgress(
                    scan_id=scan_id,
                    phase="grouping",
                    phase_description=f"Grouping by size: {file_count} files scanned",
                    files_found=file_count,
                )
                self.progress_cb(progress)
        
        # Filter to only sizes with 2+ files
        return {size: group for size, group in size_groups.items() if len(group) >= 2}
    
    def find_duplicates(
        self,
        files: Iterator[FileMetadata],
        scan_id: str,
        cancel_check: Optional[Callable[[], bool]] = None,
        persistence: Optional[Any] = None,
    ) -> List[DuplicateGroup]:
        """
        Find all duplicate groups from a stream of files.
        
        This is the main entry point for duplicate detection.
        Returns a list of DuplicateGroup objects.
        """
        # Phase 1: Group by size
        if self.progress_cb:
            self.progress_cb(ScanProgress(
                scan_id=scan_id,
                phase="grouping",
                phase_description="Grouping files by size...",
            ))
        
        if persistence is not None:
            return CandidateReducerFacade(self.hash_engine, self.progress_cb).reduce(
                files=files,
                scan_id=scan_id,
                cancel_check=cancel_check,
                persistence=persistence,
            )

        size_groups = self.group_by_size(files, scan_id)
        
        # Count files in size groups
        files_in_size_groups = sum(len(g) for g in size_groups.values())
        
        if self.progress_cb:
            self.progress_cb(ScanProgress(
                scan_id=scan_id,
                phase="grouping",
                phase_description=f"Found {len(size_groups)} size groups with {files_in_size_groups} potential duplicates",
                files_found=files_in_size_groups,
                groups_found=len(size_groups),
            ))
        
        # Phase 2: For each size group, compute partial hashes
        if self.progress_cb:
            self.progress_cb(ScanProgress(
                scan_id=scan_id,
                phase="hashing_partial",
                phase_description="Computing partial hashes...",
            ))
        
        # Flatten size groups for partial hashing
        size_group_files = []
        for group in size_groups.values():
            size_group_files.extend(group)
        
        # Group by partial hash
        partial_hash_groups = group_by_partial_hash(
            size_group_files,
            self.hash_engine,
            progress_cb=lambda n: self._on_hash_progress(scan_id, "hashing_partial", n)
        )
        partial_hash_groups = self._adaptive_refine_partial_groups(partial_hash_groups, scan_id)
        
        if self.progress_cb:
            self.progress_cb(ScanProgress(
                scan_id=scan_id,
                phase="hashing_partial",
                phase_description=f"Found {len(partial_hash_groups)} partial hash matches",
                groups_found=len(partial_hash_groups),
            ))
        
        # Phase 3: Confirm duplicates with full hashes
        if self.progress_cb:
            self.progress_cb(ScanProgress(
                scan_id=scan_id,
                phase="hashing_full",
                phase_description="Computing full hashes to confirm duplicates...",
            ))
        
        confirmed_groups = confirm_duplicates(
            partial_hash_groups,
            self.hash_engine,
            progress_cb=lambda n: self._on_hash_progress(scan_id, "hashing_full", n)
        )
        
        # Convert to DuplicateGroup objects
        duplicate_groups = []
        for hash_value, files in confirmed_groups.items():
            if cancel_check and cancel_check():
                break
            
            group = DuplicateGroup(
                group_id=f"",
                group_hash=hash_value,
                files=files,
            )
            duplicate_groups.append(group)
        
        if self.progress_cb:
            total_reclaimable = sum(g.reclaimable_size for g in duplicate_groups)
            self.progress_cb(ScanProgress(
                scan_id=scan_id,
                phase="complete",
                phase_description=f"Found {len(duplicate_groups)} duplicate groups",
                groups_found=len(duplicate_groups),
                duplicates_found=sum(len(g.files) - 1 for g in duplicate_groups),
            ))
        
        return duplicate_groups
    
    def _on_hash_progress(self, scan_id: str, phase: str, count: int):
        """Report hash progress."""
        if self.progress_cb:
            self.progress_cb(ScanProgress(
                scan_id=scan_id,
                phase=phase,
                phase_description=f"Computing {phase.replace('_', ' ')}: {count} files hashed",
                files_found=count,
            ))


def quick_group_by_hash(files: List[FileMetadata]) -> Dict[str, List[FileMetadata]]:
    """
    Quick grouping of files by their existing hash_full.
    
    Assumes files already have hash_full computed.
    """
    groups: Dict[str, List[FileMetadata]] = defaultdict(list)
    
    for file in files:
        if file.hash_full:
            groups[file.hash_full].append(file)
    
    return {k: v for k, v in groups.items() if len(v) >= 2}


@dataclass
class SizeReducer:
    """Persist size buckets while preserving the current grouping semantics."""

    progress_cb: Optional[Callable[[ScanProgress], None]] = None

    def reduce(self, files: List[FileMetadata], scan_id: str, persistence: Any) -> Dict[int, List[FileMetadata]]:
        grouped: Dict[int, List[FileMetadata]] = defaultdict(list)
        for file in files:
            grouped[file.size].append(file)

        candidate_groups = {size: group for size, group in grouped.items() if len(group) >= 2}
        for size, group in candidate_groups.items():
            file_ids = []
            for file in group:
                file_id = persistence.inventory_repo.get_file_id(scan_id, file.path)
                if file_id is not None:
                    file_ids.append(file_id)
            persistence.size_candidate_repo.replace_group(scan_id, size, file_ids)

        return candidate_groups


@dataclass
class PartialHashReducer:
    """Persist partial-hash artifacts for durable candidate reduction."""

    hash_engine: HashEngine
    progress_cb: Optional[Callable[[ScanProgress], None]] = None

    def reduce(
        self,
        size_groups: Dict[int, List[FileMetadata]],
        scan_id: str,
        persistence: Any,
    ) -> Dict[str, List[FileMetadata]]:
        size_group_files: List[FileMetadata] = []
        for group in size_groups.values():
            size_group_files.extend(group)

        partial_hash_groups = group_by_partial_hash(
            size_group_files,
            self.hash_engine,
            progress_cb=None,
        )

        for partial_hash, group in partial_hash_groups.items():
            file_ids = []
            for file in group:
                file_id = persistence.inventory_repo.get_file_id(scan_id, file.path)
                if file_id is None:
                    continue
                file_ids.append(file_id)
                persistence.partial_hash_repo.upsert(
                    session_id=scan_id,
                    file_id=file_id,
                    algorithm=self.hash_engine.algorithm.value,
                    strategy_version=self.hash_engine.partial_spec.version,
                    sample_spec=self.hash_engine.partial_spec.to_dict(),
                    partial_hash=partial_hash,
                )
            persistence.partial_candidate_repo.replace_group(scan_id, partial_hash, file_ids)

        return partial_hash_groups


@dataclass
class FullHashReducer:
    """Persist full-hash confirmation groups and durable duplicate groups."""

    hash_engine: HashEngine
    progress_cb: Optional[Callable[[ScanProgress], None]] = None

    def reduce(
        self,
        partial_hash_groups: Dict[str, List[FileMetadata]],
        scan_id: str,
        persistence: Any,
    ) -> List[DuplicateGroup]:
        confirmed_groups = confirm_duplicates(partial_hash_groups, self.hash_engine, progress_cb=None)
        duplicate_groups: List[DuplicateGroup] = []
        persistence.duplicate_group_repo.clear_session(scan_id)

        for hash_value, files in confirmed_groups.items():
            group = DuplicateGroup(group_id="", group_hash=hash_value, files=files)
            duplicate_groups.append(group)
            members = []
            keeper_path = files[0].path if files else None
            keeper_file_id = persistence.inventory_repo.get_file_id(scan_id, keeper_path) if keeper_path else None
            for file in files:
                file_id = persistence.inventory_repo.get_file_id(scan_id, file.path)
                if file_id is None:
                    continue
                persistence.full_hash_repo.upsert(
                    session_id=scan_id,
                    file_id=file_id,
                    algorithm=self.hash_engine.algorithm.value,
                    full_hash=hash_value,
                )
                members.append((file_id, "keeper" if file.path == keeper_path else "delete_candidate"))

            if members:
                persistence.duplicate_group_repo.create_group(
                    session_id=scan_id,
                    full_hash=hash_value,
                    keeper_file_id=keeper_file_id,
                    total_files=len(files),
                    reclaimable_bytes=group.reclaimable_size,
                    members=members,
                )

        return duplicate_groups


@dataclass
class CandidateReducerFacade:
    """Durable reducer facade mirroring the current grouping flow."""

    hash_engine: HashEngine
    progress_cb: Optional[Callable[[ScanProgress], None]] = None

    def reduce(
        self,
        files: Iterator[FileMetadata],
        scan_id: str,
        persistence: Any,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> List[DuplicateGroup]:
        file_list = list(files)
        size_groups = SizeReducer(progress_cb=self.progress_cb).reduce(file_list, scan_id, persistence)
        partial_hash_groups = PartialHashReducer(
            hash_engine=self.hash_engine,
            progress_cb=self.progress_cb,
        ).reduce(size_groups, scan_id, persistence)
        if cancel_check and cancel_check():
            return []
        return FullHashReducer(
            hash_engine=self.hash_engine,
            progress_cb=self.progress_cb,
        ).reduce(partial_hash_groups, scan_id, persistence)
