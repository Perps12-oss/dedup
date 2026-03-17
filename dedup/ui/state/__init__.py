"""
UI state package.

UIStateStore is the canonical consumer of ProjectionHub for currently projected
live state. Non-projected pages may continue refresh-based loading until migrated.
"""

from .store import (
    IntentLifecycle,
    ProjectedScanState,
    UIAppState,
    UIStateStore,
)

__all__ = [
    "IntentLifecycle",
    "ProjectedScanState",
    "UIAppState",
    "UIStateStore",
]
