"""Selectors for session vs phase-local vs result-assembly metrics."""

from __future__ import annotations

from dedup.ui.projections.metrics_projection import EMPTY_METRICS, MetricsProjection
from dedup.ui.state.selectors import (
    scan_metrics_phase_local,
    scan_metrics_result_assembly,
    scan_metrics_session_totals,
)
from dedup.ui.state.store import ProjectedScanState, UIAppState


def test_metrics_scope_selectors_partition_fields():
    m = MetricsProjection(
        files_discovered_total=10,
        files_discovered_fresh=10,
        files_reused_from_prior_inventory=0,
        dirs_scanned=2,
        dirs_reused=0,
        elapsed_s=1.5,
        duplicate_groups_live=3,
        current_phase_name="hash",
        current_phase_progress="5/10",
        current_phase_rows_processed=5,
        current_phase_total_units=10,
        current_phase_elapsed_s=0.5,
        current_phase_started_at=None,
        current_phase_last_updated_at=None,
        current_file="/x/a.bin",
        result_duplicate_files=0,
        result_duplicate_groups=0,
        result_rows_assembled=0,
        result_reclaimable_bytes=0,
        result_files_scanned=0,
        result_verification_level="",
        results_ready=False,
        discovery_reuse_mode="none",
        dirs_skipped_via_manifest=0,
        prior_session_compatible=False,
        prior_session_rejected_reason="none",
        time_saved_estimate=0.0,
        disk_read_bps=100.0,
        rows_per_sec=1.0,
        cache_hit_rate=0.0,
        hash_cache_hits=0,
        hash_cache_misses=0,
        eta_seconds=None,
        eta_confidence="unknown",
    )
    state = UIAppState(scan=ProjectedScanState(metrics=m))
    s = scan_metrics_session_totals(state)
    p = scan_metrics_phase_local(state)
    r = scan_metrics_result_assembly(state)
    assert s is not None and s["files_discovered_total"] == 10
    assert p is not None and p["current_phase_name"] == "hash"
    assert r is not None and r["results_ready"] is False


def test_empty_metrics_scopes():
    state = UIAppState(scan=ProjectedScanState(metrics=EMPTY_METRICS))
    assert scan_metrics_session_totals(state) is not None
    assert scan_metrics_phase_local(state) is not None
    assert scan_metrics_result_assembly(state) is not None
