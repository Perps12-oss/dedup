"""Persistence repositories for durable pipeline artifacts."""

from .checkpoint_repo import CheckpointRepository
from .discovery_repo import DiscoveryDirectoryRepository
from .hash_repo import (
    DeletionAuditRepository,
    DeletionPlanRepository,
    DeletionVerificationRepository,
    DuplicateGroupRepository,
    FullHashRepository,
    HashCacheRepository,
    PartialCandidateRepository,
    PartialHashRepository,
    SizeCandidateRepository,
)
from .inventory_repo import InventoryRepository
from .session_repo import SessionRepository

__all__ = [
    "CheckpointRepository",
    "DiscoveryDirectoryRepository",
    "DeletionAuditRepository",
    "DeletionPlanRepository",
    "DeletionVerificationRepository",
    "DuplicateGroupRepository",
    "FullHashRepository",
    "HashCacheRepository",
    "InventoryRepository",
    "PartialCandidateRepository",
    "PartialHashRepository",
    "SessionRepository",
    "SizeCandidateRepository",
]
