"""
UIStateStore — canonical UI-readable state for projected live scan surfaces.

Step 1: projected scan state and intent lifecycle.
Step 3: review state split into four explicit slices (index, selection, plan, preview).
Pages that consume live state read from the store (migrated incrementally).
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..projections.compatibility_projection import EMPTY_COMPAT, CompatibilityProjection
from ..projections.deletion_projection import EMPTY_DELETION, DeletionReadinessProjection
from ..projections.history_projection import EMPTY_HISTORY, HistoryProjection
from ..projections.metrics_projection import EMPTY_METRICS, MetricsProjection
from ..projections.phase_projection import PhaseProjection, initial_phase_map
from ..projections.session_projection import EMPTY_SESSION, SessionProjection

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
    last_intent: IntentLifecycle = field(default_factory=lambda: IntentLifecycle(status="idle"))


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
class UiDegradedFlags:
    """Published when theme or other shell paths fail — surfaces degraded mode in UI."""

    theme_apply_failed: bool = False
    theme_last_error: str = ""


@dataclass(frozen=True)
class MissionState:
    """Mission page slice: coordinator-sourced summary data."""

    last_scan: Optional[LastScanSummaryState] = None
    resumable_scan_ids: Tuple[str, ...] = ()
    recent_sessions: Tuple[Dict[str, Any], ...] = ()
    recent_folders: Tuple[str, ...] = ()


@dataclass(frozen=True)
class UIAppState:
    """App-wide UI state. Scan = projected live scan; review = four slices; mission = coordinator summary; history = session list."""

    scan: ProjectedScanState = field(default_factory=ProjectedScanState)
    review: ReviewState = field(default_factory=ReviewState)
    mission: MissionState = field(default_factory=MissionState)
    history: HistoryProjection = field(default_factory=lambda: EMPTY_HISTORY)
    # Mirrors AppSettings.advanced_mode: "simple" = reduced chrome, "advanced" = full controls.
    ui_mode: str = "simple"
    ui_degraded: UiDegradedFlags = field(default_factory=UiDegradedFlags)


class UIStateStore:
    """
    Central UI state store. Updates are applied on the Tk main thread.
    """

    def __init__(self, tk_root, initial: Optional[UIAppState] = None) -> None:
        self._root = tk_root
        self._state: UIAppState = initial or UIAppState()
        self._subs: List[Callable[[UIAppState], None]] = []
        self._main_thread_id = threading.get_ident()
        self._state_lock = threading.RLock()

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

    def set_history(self, history: HistoryProjection) -> None:
        self._set_state(replace(self._state, history=history))

    def set_review_selection(self, selection: ReviewSelectionState) -> None:
        """Update review selection slice (keep_selections, selected_group_id). Used by ReviewController."""
        self._set_state(replace(self._state, review=replace(self._state.review, selection=selection)))

    def set_review_index(self, index: ReviewIndexState) -> None:
        """Review navigator: group index, totals, current group id."""
        self._set_state(replace(self._state, review=replace(self._state.review, index=index)))

    def set_review_plan(self, plan: ReviewPlanState) -> None:
        """Deletion readiness / plan summary slice."""
        self._set_state(replace(self._state, review=replace(self._state.review, plan=plan)))

    def set_review_preview(self, preview: ReviewPreviewState) -> None:
        """Compare / hero preview targets."""
        self._set_state(replace(self._state, review=replace(self._state.review, preview=preview)))

    def set_ui_mode(self, mode: str) -> None:
        """Publish simple vs advanced UI mode for store subscribers (see docs/MODE_TOGGLE.md)."""
        m = mode if mode in ("simple", "advanced") else "simple"
        self._set_state(replace(self._state, ui_mode=m))

    def set_ui_degraded(self, flags: UiDegradedFlags) -> None:
        """Replace degraded-mode flags (theme failures, subscriber errors, etc.)."""
        self._set_state(replace(self._state, ui_degraded=flags))

    def clear_theme_degraded(self) -> None:
        """Clear theme-related degraded flags after a successful apply."""
        d = self._state.ui_degraded
        self._set_state(
            replace(
                self._state,
                ui_degraded=replace(d, theme_apply_failed=False, theme_last_error=""),
            )
        )

    def _set_state(self, new_state: UIAppState) -> None:
        if not self._is_main_thread():
            self.call_on_ui_thread(lambda ns=new_state: self._set_state(ns))
            return
        with self._state_lock:
            if new_state is self._state:
                return
            self._state = new_state
        self._notify_all()

    def _notify_all(self) -> None:
        if not self._is_main_thread():
            self.call_on_ui_thread(self._notify_all)
            return
        for cb in list(self._subs):
            self._safe_notify_one(cb, self._state)

    def call_on_ui_thread(self, fn: Callable[[], None]) -> None:
        """Run callable on Tk main thread (or now if already there)."""
        if self._is_main_thread():
            fn()
            return
        try:
            self._root.after_idle(fn)
        except Exception as e:
            _log.warning("UIStateStore failed to marshal callback: %s", e)

    def _is_main_thread(self) -> bool:
        return threading.get_ident() == self._main_thread_id

    @staticmethod
    def _safe_notify_one(cb: Callable[[UIAppState], None], state: UIAppState) -> None:
        try:
            cb(state)
        except Exception as e:
            _log.warning("UIStateStore subscriber failed: %s", e)
