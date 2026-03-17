"""
Selectors — pure functions to read from UIAppState.

Pages and components should prefer selectors over raw nested state access.
Keeps components clean and centralizes derived/optional paths.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .store import UIAppState


def scan_session(state: UIAppState):
    """Active session projection for scan. Safe if missing."""
    scan = getattr(state, "scan", None)
    if scan is None:
        return None
    return getattr(scan, "session", None)


def scan_phases(state: UIAppState) -> Dict[str, Any]:
    """Phase map for scan. Returns dict; empty if missing."""
    scan = getattr(state, "scan", None)
    if scan is None:
        return {}
    return getattr(scan, "phases", {}) or {}


def scan_metrics(state: UIAppState):
    """Metrics projection for scan. Safe if missing."""
    scan = getattr(state, "scan", None)
    if scan is None:
        return None
    return getattr(scan, "metrics", None)


def scan_compat(state: UIAppState):
    """Compatibility projection for scan. Safe if missing."""
    scan = getattr(state, "scan", None)
    if scan is None:
        return None
    return getattr(scan, "compat", None)


def scan_events_log(state: UIAppState) -> List[str]:
    """Events log for scan. Returns list; empty if missing."""
    scan = getattr(state, "scan", None)
    if scan is None:
        return []
    return getattr(scan, "events_log", []) or []


def scan_last_intent(state: UIAppState):
    """Intent lifecycle for scan. Safe if missing."""
    scan = getattr(state, "scan", None)
    if scan is None:
        return None
    return getattr(scan, "last_intent", None)


def scan_terminal(state: UIAppState):
    """Terminal session projection. Safe if missing."""
    scan = getattr(state, "scan", None)
    if scan is None:
        return None
    return getattr(scan, "terminal", None)


def review_index(state: UIAppState):
    """Review index slice. Safe if missing."""
    review = getattr(state, "review", None)
    if review is None:
        return None
    return getattr(review, "index", None)


def review_selection(state: UIAppState):
    """Review selection slice (keep selections, selected group). Safe if missing."""
    review = getattr(state, "review", None)
    if review is None:
        return None
    return getattr(review, "selection", None)


def review_plan(state: UIAppState):
    """Review plan slice (deletion readiness, reclaimable, risk). Safe if missing."""
    review = getattr(state, "review", None)
    if review is None:
        return None
    return getattr(review, "plan", None)


def review_preview(state: UIAppState):
    """Review preview slice. Safe if missing."""
    review = getattr(state, "review", None)
    if review is None:
        return None
    return getattr(review, "preview", None)


def mission(state: UIAppState):
    """Mission slice. Safe if missing."""
    return getattr(state, "mission", None)


def history(state: UIAppState):
    """History projection. Safe if missing."""
    return getattr(state, "history", None)


def active_phase_name(state: UIAppState) -> Optional[str]:
    """Current running phase name from phases map, if any."""
    phases = scan_phases(state)
    for _name, proj in phases.items():
        if getattr(proj, "status", None) == "running":
            return getattr(proj, "phase_name", None) or _name
    return None


def degraded_state(state: UIAppState) -> Optional[str]:
    """Human-readable degraded state if compat or session indicates problem; else None."""
    compat = scan_compat(state)
    if compat and getattr(compat, "degraded", False):
        return getattr(compat, "message", None) or "Compatibility degraded"
    sess = scan_session(state)
    if sess and getattr(sess, "engine_health", "").lower() not in ("", "ok", "healthy"):
        return getattr(sess, "engine_health", None)
    return None
