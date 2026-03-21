"""
DEDUP Orchestration - Scan lifecycle management.

Coordinates between the engine and UI:
- Scan lifecycle (start, pause, resume, cancel)
- Progress throttling and smoothing
- Background worker management
- Event flow
"""

from .coordinator import ScanCoordinator
from .events import EventBus, ScanEvent
from .worker import ScanWorker, ScanWorkerCallbacks

__all__ = [
    "ScanWorker",
    "ScanWorkerCallbacks",
    "ScanCoordinator",
    "EventBus",
    "ScanEvent",
]
