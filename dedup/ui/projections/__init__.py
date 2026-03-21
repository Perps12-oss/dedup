"""
CEREBRO UI Projection Layer
============================
Canonical, immutable state contracts between the engine layer and page ViewModels.

Pattern:
  Engine events (EventBus)
    → ProjectionHub  (background-thread safe, throttled Tk delivery)
      → page ViewModels receive frozen projection snapshots
        → widgets update from VM

Import surface:
"""

from .compatibility_projection import (
    EMPTY_COMPAT,
    CompatibilityProjection,
    PhaseCompatibilityProjection,
    build_compat_from_event_payload,
    build_compat_from_resume_decision,
)
from .deletion_projection import (
    EMPTY_DELETION,
    DeletionReadinessProjection,
    build_deletion_from_review_vm,
    with_dry_run_result,
)
from .history_projection import (
    EMPTY_HISTORY,
    HistoryProjection,
    HistorySessionProjection,
    build_history_from_coordinator,
)
from .hub import ProjectionHub
from .metrics_projection import (
    EMPTY_METRICS,
    MetricsProjection,
    build_metrics_from_progress,
    merge_metrics,
)
from .phase_projection import (
    PHASE_LABELS,
    PHASE_ORDER,
    PhaseProjection,
    build_phase_from_checkpoint,
    canonical_phase,
    initial_phase_map,
)
from .review_projection import (
    ReviewGroupProjection,
    build_review_group_from_duplicate_group,
    build_review_groups_from_result,
)
from .session_projection import (
    EMPTY_SESSION,
    SessionProjection,
    build_session_from_event,
)

__all__ = [
    "SessionProjection",
    "EMPTY_SESSION",
    "build_session_from_event",
    "PhaseProjection",
    "PHASE_ORDER",
    "PHASE_LABELS",
    "canonical_phase",
    "initial_phase_map",
    "build_phase_from_checkpoint",
    "MetricsProjection",
    "EMPTY_METRICS",
    "build_metrics_from_progress",
    "merge_metrics",
    "PhaseCompatibilityProjection",
    "CompatibilityProjection",
    "EMPTY_COMPAT",
    "build_compat_from_resume_decision",
    "build_compat_from_event_payload",
    "ReviewGroupProjection",
    "build_review_group_from_duplicate_group",
    "build_review_groups_from_result",
    "DeletionReadinessProjection",
    "EMPTY_DELETION",
    "build_deletion_from_review_vm",
    "with_dry_run_result",
    "HistorySessionProjection",
    "HistoryProjection",
    "EMPTY_HISTORY",
    "build_history_from_coordinator",
    "ProjectionHub",
]
