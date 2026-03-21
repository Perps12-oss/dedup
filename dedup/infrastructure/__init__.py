"""
DEDUP Infrastructure - Supporting services and utilities.

This module provides:
- Configuration management
- Logging
- Persistence / database
- Filesystem utilities
"""

from .config import Config, load_config, save_config
from .diagnostics import (
    CATEGORY_AUDIT_LOG,
    CATEGORY_CALLBACK,
    CATEGORY_CHECKPOINT,
    CATEGORY_DELETION,
    CATEGORY_HUB_DELIVERY,
    CATEGORY_REPOSITORY,
    DiagnosticEntry,
    DiagnosticsRecorder,
    get_diagnostics_recorder,
)
from .logger import Logger, get_logger
from .persistence import Persistence, ScanStore
from .utils import ensure_dir, format_bytes, format_duration

__all__ = [
    "Config",
    "load_config",
    "save_config",
    "get_logger",
    "Logger",
    "Persistence",
    "ScanStore",
    "format_bytes",
    "format_duration",
    "ensure_dir",
    "DiagnosticsRecorder",
    "DiagnosticEntry",
    "get_diagnostics_recorder",
    "CATEGORY_CHECKPOINT",
    "CATEGORY_REPOSITORY",
    "CATEGORY_CALLBACK",
    "CATEGORY_HUB_DELIVERY",
    "CATEGORY_AUDIT_LOG",
    "CATEGORY_DELETION",
]
