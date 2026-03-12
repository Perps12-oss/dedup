"""
DEDUP Engine - Core duplicate file detection engine.

This module contains the pure scanning, analysis, and duplicate detection logic.
It has no UI dependencies and is designed for datasets up to 1,000,000 files.
"""

from .models import (
    FileMetadata,
    DuplicateGroup,
    ScanConfig,
    ScanProgress,
    ScanResult,
    DeletionPlan,
    DeletionResult,
    PipelineMode,
    FileStatus,
)

from .discovery import FileDiscovery, DiscoveryOptions
from .hashing import HashEngine, HashStrategy
from .grouping import GroupingEngine
from .deletion import DeletionEngine, DeletionPolicy
from .pipeline import ScanPipeline, StreamingScanPipeline

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
    "StreamingScanPipeline",
]
