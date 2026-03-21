"""
Decision-state model and safety rail language (Master Plan Interaction Blueprint).

Decision states per group: unresolved | keep_selected | ready | warning | skipped.
Consistent copy for Keep, Preview, Execute, and warnings.
"""

from __future__ import annotations

from tkinter import ttk

from .badges import StatusBadge

# ---------------------------------------------------------------------------
# Decision states (per group)
# ---------------------------------------------------------------------------
STATE_UNRESOLVED = "unresolved"
STATE_KEEP_SELECTED = "keep_selected"
STATE_READY = "ready"
STATE_WARNING = "warning"
STATE_SKIPPED = "skipped"

DECISION_STATE_LABELS = {
    STATE_UNRESOLVED: "Unresolved",
    STATE_KEEP_SELECTED: "Keep selected",
    STATE_READY: "Ready",
    STATE_WARNING: "Warning",
    STATE_SKIPPED: "Skipped",
}

DECISION_STATE_VARIANT = {
    STATE_UNRESOLVED: "muted",
    STATE_KEEP_SELECTED: "info",
    STATE_READY: "success",
    STATE_WARNING: "warning",
    STATE_SKIPPED: "muted",
}

# ---------------------------------------------------------------------------
# Safety rail language (preview vs execute; no hidden destructive actions)
# ---------------------------------------------------------------------------
SAFETY_RAIL = {
    "keep": "Keep",
    "preview": "Preview",
    "preview_effects": "Preview effects",
    "execute": "Execute",
    "execute_deletion": "Execute deletion",
    "destructive_warning": "This will permanently remove the selected files.",
}


def get_decision_label(state: str) -> str:
    return DECISION_STATE_LABELS.get(state, state.replace("_", " ").title())


def get_decision_variant(state: str) -> str:
    return DECISION_STATE_VARIANT.get(state, "muted")


def get_group_decision_state(
    group_id: str,
    keep_selections: dict,
    has_risk: bool,
) -> str:
    """Derive decision state for a group: unresolved | keep_selected | ready | warning."""
    has_keep = group_id in keep_selections
    if has_risk:
        return STATE_WARNING
    if has_keep:
        return STATE_READY  # has keep and no risk = ready to delete
    return STATE_UNRESOLVED


class DecisionStateBadge(ttk.Frame):
    """Reusable badge showing one of: unresolved, keep_selected, ready, warning, skipped."""

    def __init__(self, parent, state: str = STATE_UNRESOLVED, **kwargs):
        super().__init__(parent, **kwargs)
        self._state = state
        self._badge = StatusBadge(
            self,
            text=get_decision_label(state),
            variant=get_decision_variant(state),
        )
        self._badge.pack(side="left")

    def set_state(self, state: str) -> None:
        self._state = state
        self._badge.set(get_decision_label(state), get_decision_variant(state))
