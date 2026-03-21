"""
DEDUP Metric Semantics - Explicit definitions for all reported metrics.

All UI and logs must use these semantics. No metric may be shown as "confirmed"
or "reclaimable" until full-hash confirmation. No fake progress or ETA.

Semantics:
- files_discovered: Count of file paths yielded by discovery (before any hash).
- files_scanned: Same as files_discovered for a completed discovery phase.
- files_total: Only set when discovery has completed; otherwise None.
- candidate_files: Files that share size with at least one other (potential duplicates).
- candidate_groups: Size groups with 2+ files; not yet confirmed duplicates.
- confirmed_duplicate_files: Files that are in a group with 2+ files sharing full hash.
- confirmed_duplicate_groups: Groups where all members have identical full hash.
- reclaimable_bytes: Sum over confirmed duplicate groups of (group_size * (n-1)); only after full hash.
- skipped_files: Files excluded by filters (size, extension, etc.); not necessarily counted.
- errored_files: Files that could not be read or hashed; counted in discovery/hashing.
- active_phase: One of idle, discovering, grouping, hashing_partial, hashing_full, complete, error, cancelled.
- ETA_available: True only when we have stable measured throughput and a known total (e.g. hashing phase with total).
- percent_complete: Only shown when files_total is known and > 0; otherwise indeterminate.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional


class MetricSemantics:
    """Documented semantics for each metric; use for UI and validation."""

    FILES_DISCOVERED = "files_discovered"  # From discovery phase
    FILES_SCANNED = "files_scanned"  # Same as discovered at end of discovery
    FILES_TOTAL = "files_total"  # Set only after discovery completes; None during discovery
    CANDIDATE_FILES = "candidate_files"  # In size groups with 2+; not confirmed
    CANDIDATE_GROUPS = "candidate_groups"  # Size groups; not confirmed
    CONFIRMED_DUPLICATE_FILES = "confirmed_duplicate_files"  # After full hash
    CONFIRMED_DUPLICATE_GROUPS = "confirmed_duplicate_groups"
    RECLAIMABLE_BYTES = "reclaimable_bytes"  # Only from confirmed groups
    SKIPPED_FILES = "skipped_files"
    ERRORED_FILES = "errored_files"
    ACTIVE_PHASE = "active_phase"
    ETA_AVAILABLE = "eta_available"  # Only if stable throughput + known total
    PERCENT_COMPLETE_AVAILABLE = "percent_complete_available"


class Phase(str, Enum):
    IDLE = "idle"
    DISCOVERING = "discovering"
    GROUPING = "grouping"
    HASHING_PARTIAL = "hashing_partial"
    HASHING_FULL = "hashing_full"
    COMPLETE = "complete"
    ERROR = "error"
    CANCELLED = "cancelled"


def should_show_percent(files_total: Optional[int]) -> bool:
    """Return True only when percent progress is truthful (known total)."""
    return files_total is not None and files_total > 0


def should_show_eta(
    estimated_remaining_seconds: Optional[float],
    phase: str,
) -> bool:
    """Return True only when ETA is based on stable measured throughput."""
    if estimated_remaining_seconds is None:
        return False
    # Only phases with deterministic work (e.g. hashing N files) can have valid ETA
    return phase in (Phase.HASHING_PARTIAL.value, Phase.HASHING_FULL.value, Phase.GROUPING.value)
