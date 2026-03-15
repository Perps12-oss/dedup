"""
DEDUP Infrastructure - Supporting services and utilities.

This module provides:
- Configuration management
- Logging
- Persistence / database
- Filesystem utilities
"""

from .config import Config, load_config, save_config
from .logger import get_logger, Logger
from .persistence import Persistence, ScanStore
from .utils import format_bytes, format_duration, ensure_dir
from .diagnostics import (
    DiagnosticsRecorder,
    DiagnosticEntry,
    get_diagnostics_recorder,
    CATEGORY_CHECKPOINT,
    CATEGORY_REPOSITORY,
    CATEGORY_CALLBACK,
    CATEGORY_HUB_DELIVERY,
    CATEGORY_AUDIT_LOG,
    CATEGORY_DELETION,
)

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
