"""
DEDUP - A minimal, high-performance duplicate file finder.

Features:
- Streaming file discovery for 1M+ file datasets
- Layered hashing (partial then full) for efficiency
- Memory-efficient processing
- Safe deletion with trash/recycle bin support
- Minimal, truthful UI

Usage:
    from dedup.engine import ScanConfig, ScanPipeline

    config = ScanConfig(roots=[Path("/data")])
    pipeline = ScanPipeline(config)
    result = pipeline.run()

    print(f"Found {len(result.duplicate_groups)} duplicate groups")
"""

__version__ = "3.0.0"
__author__ = "DEDUP Project"

from .engine import (
    DeletionEngine,
    DeletionPlan,
    DeletionPolicy,
    DeletionResult,
    DiscoveryOptions,
    DuplicateGroup,
    FileDiscovery,
    FileMetadata,
    FileStatus,
    GroupingEngine,
    HashEngine,
    HashStrategy,
    PipelineMode,
    ScanConfig,
    ScanPipeline,
    ScanProgress,
    ScanResult,
)

__all__ = [
    "FileMetadata",
    "DuplicateGroup",
    "ScanConfig",
    "ScanProgress",
    "ScanResult",
    "DeletionPlan",
    "DeletionResult",
    "PipelineMode",
    "FileStatus",
    "FileDiscovery",
    "DiscoveryOptions",
    "HashEngine",
    "HashStrategy",
    "GroupingEngine",
    "DeletionEngine",
    "DeletionPolicy",
    "ScanPipeline",
]
