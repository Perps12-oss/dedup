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


def scan_metrics_session_totals(state: UIAppState) -> Optional[Dict[str, Any]]:
    """
    Session-wide cumulative metrics (discovery totals, elapsed, live duplicate group count).
    Distinct from phase-local and result-assembly rows in MetricsProjection.
    """
    m = scan_metrics(state)
    if m is None:
        return None
    return {
        "files_discovered_total": m.files_discovered_total,
        "files_discovered_fresh": m.files_discovered_fresh,
        "files_reused_from_prior_inventory": m.files_reused_from_prior_inventory,
        "dirs_scanned": m.dirs_scanned,
        "dirs_reused": m.dirs_reused,
        "elapsed_s": m.elapsed_s,
        "duplicate_groups_live": m.duplicate_groups_live,
        "discovery_reuse_mode": m.discovery_reuse_mode,
        "dirs_skipped_via_manifest": m.dirs_skipped_via_manifest,
        "prior_session_compatible": m.prior_session_compatible,
        "prior_session_rejected_reason": m.prior_session_rejected_reason,
        "time_saved_estimate": m.time_saved_estimate,
    }


def scan_metrics_phase_local(state: UIAppState) -> Optional[Dict[str, Any]]:
    """Current pipeline phase only — progress strings, rows processed, ETA hints."""
    m = scan_metrics(state)
    if m is None:
        return None
    return {
        "current_phase_name": m.current_phase_name,
        "current_phase_progress": m.current_phase_progress,
        "current_phase_rows_processed": m.current_phase_rows_processed,
        "current_phase_total_units": m.current_phase_total_units,
        "current_phase_elapsed_s": m.current_phase_elapsed_s,
        "current_phase_started_at": m.current_phase_started_at,
        "current_phase_last_updated_at": m.current_phase_last_updated_at,
        "current_file": m.current_file,
        "disk_read_bps": m.disk_read_bps,
        "rows_per_sec": m.rows_per_sec,
        "cache_hit_rate": m.cache_hit_rate,
        "hash_cache_hits": m.hash_cache_hits,
        "hash_cache_misses": m.hash_cache_misses,
        "eta_seconds": m.eta_seconds,
        "eta_confidence": m.eta_confidence,
    }


def scan_metrics_result_assembly(state: UIAppState) -> Optional[Dict[str, Any]]:
    """Terminal / result-assembly authoritative counts (verification, reclaimable, etc.)."""
    m = scan_metrics(state)
    if m is None:
        return None
    return {
        "result_duplicate_files": m.result_duplicate_files,
        "result_duplicate_groups": m.result_duplicate_groups,
        "result_rows_assembled": m.result_rows_assembled,
        "result_reclaimable_bytes": m.result_reclaimable_bytes,
        "result_files_scanned": m.result_files_scanned,
        "result_verification_level": m.result_verification_level,
        "results_ready": m.results_ready,
    }


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
