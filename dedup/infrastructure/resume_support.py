"""
Resume support: phase completion and artifact validation for authoritative durable resume.

Provides:
- is_phase_complete(session_id, phase)
- get_phase_artifact_stats(session_id, phase)
- validate_artifact_integrity(session_id, phase, session_config_hash, schema_version)
"""

from __future__ import annotations

from typing import Any, Dict, Tuple

from ..engine.models import PhaseStatus, ScanPhase
from .repositories.checkpoint_repo import CheckpointRepository
from .repositories.hash_repo import (
    DuplicateGroupRepository,
    FullHashRepository,
    PartialCandidateRepository,
    PartialHashRepository,
    SizeCandidateRepository,
)
from .repositories.inventory_repo import InventoryRepository

# Canonical phase order for resume.
PHASE_ORDER = [
    ScanPhase.DISCOVERY,
    ScanPhase.SIZE_REDUCTION,
    ScanPhase.PARTIAL_HASH,
    ScanPhase.FULL_HASH,
    ScanPhase.RESULT_ASSEMBLY,
]


def is_phase_complete(
    checkpoint_repo: CheckpointRepository,
    session_id: str,
    phase: ScanPhase,
) -> bool:
    """True if this phase has a completed and finalized checkpoint."""
    cp = checkpoint_repo.get(session_id, phase)
    if cp is None:
        return False
    if cp.status != PhaseStatus.COMPLETED:
        return False
    return cp.is_finalized


def get_phase_artifact_stats(
    session_id: str,
    phase: ScanPhase,
    inventory_repo: InventoryRepository,
    size_candidate_repo: SizeCandidateRepository,
    partial_hash_repo: PartialHashRepository,
    partial_candidate_repo: PartialCandidateRepository,
    full_hash_repo: FullHashRepository,
    duplicate_group_repo: DuplicateGroupRepository,
) -> Dict[str, Any]:
    """Return artifact row counts and fingerprints for the given phase."""
    stats: Dict[str, Any] = {}
    inv_count = inventory_repo.count(session_id)
    stats["inventory_count"] = inv_count

    if phase == ScanPhase.DISCOVERY:
        stats["output_count"] = inv_count
        return stats

    size_groups = size_candidate_repo.iter_groups(session_id)
    size_candidate_count = sum(len(ids) for ids in size_groups.values())
    stats["size_candidate_count"] = size_candidate_count
    stats["size_group_count"] = len(size_groups)

    if phase == ScanPhase.SIZE_REDUCTION:
        stats["output_count"] = size_candidate_count
        return stats

    partial_groups = partial_candidate_repo.iter_groups(session_id)
    partial_candidate_count = sum(len(ids) for ids in partial_groups.values())
    stats["partial_candidate_count"] = partial_candidate_count
    stats["partial_group_count"] = len(partial_groups)

    if phase == ScanPhase.PARTIAL_HASH:
        stats["output_count"] = partial_candidate_count
        return stats

    # FULL_HASH / RESULT_ASSEMBLY: count from duplicate_groups
    stats["duplicate_group_count"] = duplicate_group_repo.count_groups(session_id)
    stats["duplicate_member_count"] = duplicate_group_repo.sum_member_count(session_id)
    stats["output_count"] = stats["duplicate_group_count"]
    return stats


def validate_artifact_integrity(
    session_id: str,
    phase: ScanPhase,
    checkpoint_repo: CheckpointRepository,
    inventory_repo: InventoryRepository,
    size_candidate_repo: SizeCandidateRepository,
    partial_candidate_repo: PartialCandidateRepository,
    duplicate_group_repo: DuplicateGroupRepository,
) -> Tuple[bool, str]:
    """
    Verify that persisted artifacts match checkpoint counters.
    Returns (valid, reason_string).
    """
    cp = checkpoint_repo.get(session_id, phase)
    if cp is None:
        return False, "no_checkpoint"

    if phase == ScanPhase.DISCOVERY:
        count = inventory_repo.count(session_id)
        if cp.completed_units != count:
            return False, f"artifact_count_mismatch: checkpoint={cp.completed_units} inventory={count}"
        return True, "ok"

    if phase == ScanPhase.SIZE_REDUCTION:
        size_groups = size_candidate_repo.iter_groups(session_id)
        count = sum(len(ids) for ids in size_groups.values())
        if cp.completed_units is not None and cp.completed_units != count:
            return False, f"artifact_count_mismatch: checkpoint={cp.completed_units} size_candidates={count}"
        return True, "ok"

    if phase == ScanPhase.PARTIAL_HASH:
        partial_groups = partial_candidate_repo.iter_groups(session_id)
        count = sum(len(ids) for ids in partial_groups.values())
        if cp.completed_units is not None and cp.completed_units != count:
            return False, f"artifact_count_mismatch: checkpoint={cp.completed_units} partial_candidates={count}"
        return True, "ok"

    if phase in (ScanPhase.FULL_HASH, ScanPhase.RESULT_ASSEMBLY):
        count = duplicate_group_repo.count_groups(session_id)
        if cp.completed_units is not None and cp.completed_units != count:
            return False, f"artifact_count_mismatch: checkpoint={cp.completed_units} duplicate_groups={count}"
        return True, "ok"

    return True, "ok"
