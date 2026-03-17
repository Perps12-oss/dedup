"""
UIStateStore — canonical UI-readable state for projected live scan surfaces.

Step 1: projected scan state and intent lifecycle.
Step 3: review state split into four explicit slices (index, selection, plan, preview).
Pages that consume live state read from the store (migrated incrementally).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..projections.session_projection import SessionProjection, EMPTY_SESSION
from ..projections.phase_projection import PhaseProjection, initial_phase_map
from ..projections.metrics_projection import MetricsProjection, EMPTY_METRICS
from ..projections.compatibility_projection import CompatibilityProjection, EMPTY_COMPAT
from ..projections.deletion_projection import DeletionReadinessProjection, EMPTY_DELETION

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class IntentLifecycle:
    """
    Non-optimistic intent lifecycle signal for scan (and later review) actions.
    Shown in UI so users see accepted/failed/completed without fake optimistic state.
    """
    status: str  # "idle" | "accepted" | "failed" | "completed"
    intent_type: str = ""
    message: str = ""


@dataclass(frozen=True)
class ProjectedScanState:
    """Currently projected scan state (canonical consumer of ProjectionHub)."""

    session: SessionProjection = EMPTY_SESSION
    phases: Dict[str, PhaseProjection] = field(default_factory=initial_phase_map)
    metrics: MetricsProjection = EMPTY_METRICS
    compat: CompatibilityProjection = EMPTY_COMPAT
    events_log: List[str] = field(default_factory=list)
    terminal: Optional[SessionProjection] = None
    last_intent: IntentLifecycle = field(
        default_factory=lambda: IntentLifecycle(status="idle")
    )


# ---------------------------------------------------------------------------
# Review state: four explicit slices (Step 3). Store-only; no page refactor yet.
# Boundaries: index = navigator/list, selection = keep/selected, plan = deletion
# readiness, preview = compare/thumbnail/view-mode preview.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReviewIndexState:
    """Group navigator / list position and metadata."""
    current_group_index: int = 0
    groups_total: int = 0
    current_group_id: Optional[str] = None
    filter_text: str = ""


@dataclass(frozen=True)
class ReviewSelectionState:
    """Keep selections and selected group; clear/override state."""
    keep_selections: Dict[str, str] = field(default_factory=dict)  # group_id -> keep path
    selected_group_id: Optional[str] = None


@dataclass(frozen=True)
class ReviewPlanState:
    """Deletion plan summary, safety counts, reclaimable bytes, risk flags."""
    deletion_readiness: DeletionReadinessProjection = EMPTY_DELETION
    reclaimable_bytes: int = 0
    risk_flags: int = 0
    plan_summary: str = ""


@dataclass(frozen=True)
class ReviewPreviewState:
    """Preview/compare targets and view-mode-specific preview metadata."""
    preview_target_path: Optional[str] = None
    compare_target_path: Optional[str] = None
    view_mode: str = "table"  # "table" | "gallery" | "compare"
    preview_metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ReviewState:
    """All four review slices. Populated by adapter/page when review is migrated."""
    index: ReviewIndexState = field(default_factory=ReviewIndexState)
    selection: ReviewSelectionState = field(default_factory=ReviewSelectionState)
    plan: ReviewPlanState = field(default_factory=ReviewPlanState)
    preview: ReviewPreviewState = field(default_factory=ReviewPreviewState)


# ---------------------------------------------------------------------------
# Mission state: last scan summary, resumable IDs, recent sessions (Step 8).
# Updated by app when navigating to Mission or after scan complete.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LastScanSummaryState:
    """Last scan summary for Mission page."""
    files_scanned: int = 0
    duplicate_groups: int = 0
    reclaimable_bytes: int = 0
    duration_s: float = 0.0


@dataclass(frozen=True)
class MissionState:
    """Mission page slice: coordinator-sourced summary data."""
    last_scan: Optional[LastScanSummaryState] = None
    resumable_scan_ids: Tuple[str, ...] = ()
    recent_sessions: Tuple[Dict[str, Any], ...] = ()
    recent_folders: Tuple[str, ...] = ()


@dataclass(frozen=True)
class UIAppState:
    """App-wide UI state. Scan = projected live scan; review = four slices; mission = coordinator summary."""

    scan: ProjectedScanState = field(default_factory=ProjectedScanState)
    review: ReviewState = field(default_factory=ReviewState)
    mission: MissionState = field(default_factory=MissionState)


class UIStateStore:
    """
    Central UI state store. Updates are applied on the Tk main thread.
    """

    def __init__(self, tk_root, initial: Optional[UIAppState] = None) -> None:
        self._root = tk_root
        self._state: UIAppState = initial or UIAppState()
        self._subs: List[Callable[[UIAppState], None]] = []

    @property
    def state(self) -> UIAppState:
        return self._state

    def subscribe(
        self,
        callback: Callable[[UIAppState], None],
        *,
        fire_immediately: bool = True,
    ) -> Callable[[], None]:
        self._subs.append(callback)
        if fire_immediately:
            self._safe_notify_one(callback, self._state)

        def unsub() -> None:
            try:
                self._subs.remove(callback)
            except ValueError:
                pass

        return unsub

    def set_session(self, proj: SessionProjection) -> None:
        self._set_state(replace(self._state, scan=replace(self._state.scan, session=proj)))

    def set_phases(self, phases: Dict[str, PhaseProjection]) -> None:
        self._set_state(replace(self._state, scan=replace(self._state.scan, phases=dict(phases))))

    def set_metrics(self, proj: MetricsProjection) -> None:
        self._set_state(replace(self._state, scan=replace(self._state.scan, metrics=proj)))

    def set_compat(self, proj: CompatibilityProjection) -> None:
        self._set_state(replace(self._state, scan=replace(self._state.scan, compat=proj)))

    def set_events_log(self, entries: List[str]) -> None:
        bounded = list(entries[:500])
        self._set_state(replace(self._state, scan=replace(self._state.scan, events_log=bounded)))

    def set_terminal(self, proj: SessionProjection) -> None:
        self._set_state(replace(self._state, scan=replace(self._state.scan, terminal=proj)))

    def set_intent_lifecycle(self, lifecycle: IntentLifecycle) -> None:
        self._set_state(replace(self._state, scan=replace(self._state.scan, last_intent=lifecycle)))

    def set_mission(self, mission: MissionState) -> None:
        self._set_state(replace(self._state, mission=mission))

    def _set_state(self, new_state: UIAppState) -> None:
        if new_state is self._state:
            return
        self._state = new_state
        self._notify_all()

    def _notify_all(self) -> None:
        for cb in list(self._subs):
            self._safe_notify_one(cb, self._state)

    @staticmethod
    def _safe_notify_one(cb: Callable[[UIAppState], None], state: UIAppState) -> None:
        try:
            cb(state)
        except Exception as e:
            _log.warning("UIStateStore subscriber failed: %s", e)
