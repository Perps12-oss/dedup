"""
DEDUP Engine - Core duplicate file detection engine.

This module contains the pure scanning, analysis, and duplicate detection logic.
It has no UI dependencies and is designed for datasets up to 1,000,000 files.
"""

from .deletion import DeletionEngine, DeletionPolicy
from .discovery import DiscoveryOptions, FileDiscovery
from .grouping import GroupingEngine
from .hashing import HashEngine, HashStrategy
from .models import (
    DeletionPlan,
    DeletionResult,
    DuplicateGroup,
    FileMetadata,
    FileStatus,
    PipelineMode,
    ScanConfig,
    ScanProgress,
    ScanResult,
)
from .pipeline import ScanPipeline

__all__ = [
    # Models
    "FileMetadata",
    "DuplicateGroup",
    "ScanConfig",
    "ScanProgress",
    "ScanResult",
    "DeletionPlan",
    "DeletionResult",
    "PipelineMode",
    "FileStatus",
    # Engine components
    "FileDiscovery",
    "DiscoveryOptions",
    "HashEngine",
    "HashStrategy",
    "GroupingEngine",
    "DeletionEngine",
    "DeletionPolicy",
    "ScanPipeline",
]
