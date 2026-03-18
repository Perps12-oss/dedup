"""
Scan intents — user actions for the scan workflow.

Emitted by ScanPage (or app); handled by ScanController.
Drives store intent lifecycle (accepted / completed / failed).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict


@dataclass(frozen=True)
class StartScan:
    """User requested a new scan on a path."""
    path: Path
    options: Dict[str, Any]


@dataclass(frozen=True)
class StartResume:
    """User requested to resume an interrupted scan."""
    scan_id: str


@dataclass(frozen=True)
class CancelScan:
    """User requested to cancel the current scan."""
    pass
