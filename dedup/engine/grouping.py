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
from typing import Dict, List, Iterator, Optional, Callable, Set
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
        cancel_check: Optional[Callable[[], bool]] = None
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
