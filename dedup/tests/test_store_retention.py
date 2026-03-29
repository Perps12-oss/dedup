"""UIStateStore reset helpers — session boundaries and review slice cleanup."""

from __future__ import annotations

from dataclasses import replace

from dedup.ui.projections.session_projection import EMPTY_SESSION
from dedup.ui.state.store import (
    ReviewSelectionState,
    UIStateStore,
)


def test_reset_live_scan_projection_clears_session_metrics(tk_root):
    store = UIStateStore(tk_root)
    store.set_session(replace(EMPTY_SESSION, session_id="prior-scan", status="completed"))
    store.reset_live_scan_projection()
    assert store.state.scan.session.session_id == ""


def test_reset_review_state_clears_keep_selections(tk_root):
    store = UIStateStore(tk_root)
    store.set_review_selection(ReviewSelectionState(keep_selections={"g1": "/a"}, selected_group_id="g1"))
    store.reset_review_state()
    assert store.state.review.selection.keep_selections == {}
    assert store.state.review.selection.selected_group_id is None
