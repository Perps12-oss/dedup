"""
UI state package.

UIStateStore is the canonical consumer of ProjectionHub for currently projected
live state. Review state is split into four slices (index, selection, plan, preview).
Non-projected pages may continue refresh-based loading until migrated.
"""

from .store import (
    IntentLifecycle,
    LastScanSummaryState,
    MissionState,
    ProjectedScanState,
    ReviewIndexState,
    ReviewPlanState,
    ReviewPreviewState,
    ReviewSelectionState,
    ReviewState,
    UIAppState,
    UIStateStore,
)

__all__ = [
    "IntentLifecycle",
    "LastScanSummaryState",
    "MissionState",
    "ProjectedScanState",
    "ReviewIndexState",
    "ReviewPlanState",
    "ReviewPreviewState",
    "ReviewSelectionState",
    "ReviewState",
    "UIAppState",
    "UIStateStore",
]
