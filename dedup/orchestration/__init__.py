"""
DEDUP Orchestration - Scan lifecycle management.

Coordinates between the engine and UI:
- Scan lifecycle (start, pause, resume, cancel)
- Progress throttling and smoothing
- Background worker management
- Event flow
"""

from .worker import ScanWorker, ScanWorkerCallbacks
from .coordinator import ScanCoordinator
from .events import EventBus, ScanEvent

__all__ = [
    "ScanWorker",
    "ScanWorkerCallbacks",
    "ScanCoordinator",
    "EventBus",
    "ScanEvent",
]
