"""
Tests for UI viewmodels — ensure they conform to page contracts.
"""
from __future__ import annotations

import pytest

from dedup.ui.viewmodels.review_vm import ReviewVM
from dedup.ui.viewmodels.history_vm import HistoryVM
from dedup.ui.viewmodels.scan_vm import ScanVM
from dedup.ui.viewmodels.mission_vm import MissionVM
from dedup.ui.viewmodels.diagnostics_vm import DiagnosticsVM
from dedup.ui.projections.review_projection import ReviewGroupProjection
from dedup.ui.projections.session_projection import EMPTY_SESSION
from dedup.ui.projections.history_projection import EMPTY_HISTORY
from dedup.ui.projections.metrics_projection import merge_metrics


# ---------------------------------------------------------------------------
# ReviewVM
# ---------------------------------------------------------------------------

def _make_group(gid: str, file_count: int = 2, reclaimable: int = 1024) -> ReviewGroupProjection:
    return ReviewGroupProjection(
        group_id=gid, group_size=512, file_count=file_count,
        verification_level="full_hash", confidence_label="Exact",
        reclaimable_bytes=reclaimable, review_status="unreviewed",
        risk_flags=(), keeper_candidate="/a/f1.txt",
        thumbnail_capable=False, metadata_summary=f"group {gid}",
    )


class TestReviewVM:
    def test_filtered_groups_is_property(self):
        vm = ReviewVM()
        assert isinstance(vm.filtered_groups, list)

    def test_filter_text(self):
        vm = ReviewVM()
        vm.groups = [_make_group("g1"), _make_group("g2")]
        vm.filter_text = "g1"
        assert len(vm.filtered_groups) == 1
        assert vm.filtered_groups[0].group_id == "g1"

    def test_set_keep(self):
        vm = ReviewVM()
        vm.groups = [_make_group("g1")]
        vm.set_keep("g1", "/a/f1.txt")
        assert vm.keep_selections["g1"] == "/a/f1.txt"
        assert vm.keep_count == 1
        assert vm.delete_count == 1

    def test_total_groups(self):
        vm = ReviewVM()
        vm.groups = [_make_group("g1"), _make_group("g2")]
        assert vm.total_groups == 2

    def test_reclaimable_bytes(self):
        vm = ReviewVM()
        vm.groups = [_make_group("g1", reclaimable=100), _make_group("g2", reclaimable=200)]
        assert vm.reclaimable_bytes == 300


# ---------------------------------------------------------------------------
# HistoryVM
# ---------------------------------------------------------------------------

class TestHistoryVM:
    def test_selected_session_property(self):
        vm = HistoryVM()
        assert vm.selected_session is None

    def test_avg_duration_s_delegates(self):
        vm = HistoryVM()
        assert vm.avg_duration_s == EMPTY_HISTORY.avg_duration_s

    def test_avg_reclaim_bytes_delegates(self):
        vm = HistoryVM()
        assert vm.avg_reclaim_bytes == EMPTY_HISTORY.avg_reclaim_bytes


# ---------------------------------------------------------------------------
# ScanVM
# ---------------------------------------------------------------------------

class TestScanVM:
    def test_default_state(self):
        vm = ScanVM()
        assert not vm.is_scanning

    def test_reset_sets_scanning_true(self):
        """reset() is called at scan start — it sets is_scanning = True."""
        vm = ScanVM()
        vm.reset()
        assert vm.is_scanning
        assert vm.current_file == ""
        assert vm.error_message == ""

    def test_work_saved_projection_uses_reuse_metrics(self):
        vm = ScanVM()
        vm.apply_metrics_projection(merge_metrics(
            vm.metrics,
            files_reused_from_prior_inventory=123,
            dirs_skipped_via_manifest=45,
            dirs_scanned=100,
            discovery_reuse_mode="subtree_skip",
            prior_session_compatible=True,
            prior_session_rejected_reason="compatible",
            time_saved_estimate=9.8,
        ))
        ws = vm.work_saved_info
        assert ws["Dirs skipped"] == "45"
        assert ws["Files reused"] == "123"
        assert ws["Reuse mode"] == "subtree_skip"
        assert ws["Skip ratio"] == "45%"
        assert ws["Compatible prior"] == "Yes"
        assert ws["Compatibility reason"] == "compatible"
        assert ws["Time saved"] == "~10s"

    def test_work_saved_projection_defaults_without_reuse(self):
        vm = ScanVM()
        ws = vm.work_saved_info
        assert ws["Dirs skipped"] == "0"
        assert ws["Files reused"] == "0"
        assert ws["Reuse mode"] == "none"
        assert ws["Skip ratio"] == "—"
        assert ws["Hash cache hit rate"] == "—"
        assert ws["Compatible prior"] == "No"

    def test_session_totals_are_monotonic_across_updates(self):
        vm = ScanVM()
        vm.apply_metrics_projection(merge_metrics(
            vm.metrics,
            files_discovered_total=100,
            dirs_scanned=20,
            result_duplicate_groups=8,
            result_duplicate_files=25,
            elapsed_s=10.0,
        ))
        vm.apply_metrics_projection(merge_metrics(
            vm.metrics,
            files_discovered_total=40,
            dirs_scanned=5,
            result_duplicate_groups=3,
            result_duplicate_files=10,
            elapsed_s=2.0,
        ))
        assert vm.session_metrics.files_discovered_total == 100
        assert vm.session_metrics.directories_scanned_total == 20
        assert vm.session_metrics.duplicate_groups_total == 8
        assert vm.session_metrics.duplicate_files_total == 25
        assert vm.session_metrics.elapsed_total_s == 10.0

    def test_dirs_scanned_flows_from_projection(self):
        vm = ScanVM()
        vm.apply_metrics_projection(merge_metrics(
            vm.metrics,
            files_discovered_total=1000,
            dirs_scanned=200,
            dirs_reused=50,
            dirs_skipped_via_manifest=50,
            elapsed_s=10.0,
        ))
        assert vm.session_metrics.directories_scanned_total == 200
        assert vm.session_metrics.dirs_reused_total == 50
        assert vm.session_metrics.dirs_skipped_via_manifest == 50

    def test_discovery_speed_property(self):
        vm = ScanVM()
        vm.apply_metrics_projection(merge_metrics(
            vm.metrics,
            files_discovered_total=5000,
            elapsed_s=10.0,
        ))
        assert vm.session_metrics.discovery_speed == pytest.approx(500.0)

    def test_discovery_speed_zero_when_elapsed_zero(self):
        """When elapsed_total_s is 0, discovery_speed must return 0 (not inf or absurd value)."""
        vm = ScanVM()
        vm.apply_metrics_projection(merge_metrics(
            vm.metrics,
            files_discovered_total=2120,
            elapsed_s=0.0,
        ))
        assert vm.session_metrics.discovery_speed == 0.0

    def test_skip_ratio_property(self):
        vm = ScanVM()
        vm.apply_metrics_projection(merge_metrics(
            vm.metrics,
            dirs_scanned=100,
            dirs_skipped_via_manifest=75,
        ))
        assert vm.session_metrics.skip_ratio == pytest.approx(0.75)

    def test_hash_cache_hit_rate_property(self):
        vm = ScanVM()
        vm.apply_metrics_projection(merge_metrics(
            vm.metrics,
            hash_cache_hits=90,
            hash_cache_misses=10,
        ))
        assert vm.session_metrics.hash_cache_hit_rate == pytest.approx(0.9)
        ws = vm.work_saved_info
        assert ws["Hash cache hit rate"] == "90%"

    def test_phase_and_result_metrics_are_separate(self):
        vm = ScanVM()
        vm.apply_metrics_projection(merge_metrics(
            vm.metrics,
            current_phase_name="result_assembly",
            current_phase_rows_processed=12,
            current_phase_total_units=20,
            current_phase_elapsed_s=3.5,
            current_file="C:/x/a.txt",
            result_rows_assembled=30,
            result_duplicate_groups=6,
            result_duplicate_files=18,
        ))
        assert vm.phase_metrics.phase_name == "result_assembly"
        assert vm.phase_metrics.completed_units == 12
        assert vm.phase_metrics.total_units == 20
        assert vm.result_metrics.rows_processed == 30
        assert vm.result_metrics.groups_assembled == 6
        assert vm.result_metrics.duplicate_files_in_results == 18

    def test_final_results_not_set_without_results_ready(self):
        """FinalScanResultsSummary is never populated from non-terminal projections."""
        vm = ScanVM()
        vm.apply_metrics_projection(merge_metrics(
            vm.metrics,
            result_duplicate_groups=1030,
            result_duplicate_files=2060,
            result_reclaimable_bytes=2_000_000_000,
            # results_ready=False (default)
        ))
        assert not vm.final_results.results_ready
        assert vm.final_results.duplicate_groups_total == 0
        assert vm.final_results.reclaimable_bytes_total == 0

    def test_final_results_populated_on_terminal_event(self):
        """FinalScanResultsSummary is set only when results_ready=True."""
        vm = ScanVM()
        vm.apply_metrics_projection(merge_metrics(
            vm.metrics,
            result_duplicate_groups=1030,
            result_duplicate_files=2060,
            result_reclaimable_bytes=2_000_000_000,
            result_files_scanned=144267,
            result_verification_level="full_hash",
            results_ready=True,
        ))
        fr = vm.final_results
        assert fr.results_ready is True
        assert fr.duplicate_groups_total == 1030
        assert fr.duplicate_files_total == 2060
        assert fr.reclaimable_bytes_total == 2_000_000_000
        assert fr.files_scanned_total == 144267
        assert fr.verification_level == "full_hash"

    def test_final_results_are_monotonic(self):
        """A later stale/smaller update cannot overwrite a true terminal value."""
        vm = ScanVM()
        vm.apply_metrics_projection(merge_metrics(
            vm.metrics,
            result_duplicate_groups=1030,
            result_reclaimable_bytes=2_000_000_000,
            results_ready=True,
        ))
        # Simulate stale / partial update arriving after the real terminal event
        vm.apply_metrics_projection(merge_metrics(
            vm.metrics,
            result_duplicate_groups=5,
            result_reclaimable_bytes=1000,
            results_ready=True,
        ))
        assert vm.final_results.duplicate_groups_total == 1030
        assert vm.final_results.reclaimable_bytes_total == 2_000_000_000

    def test_scan_result_dict_keys_match_hub_expectations(self):
        """
        Regression test: ScanResult.to_dict() uses 'total_duplicates' and
        'duplicate_groups' (a list).  The hub must read these keys — not the
        legacy 'duplicates_found' / 'groups_found' names that caused Groups=0.
        """
        from dedup.engine.models import ScanResult, ScanConfig, DuplicateGroup, FileMetadata
        from datetime import datetime
        config = ScanConfig(roots=[], min_size_bytes=1)
        grp = DuplicateGroup(
            group_id="g1",
            group_hash="aabbcc",
            files=[
                FileMetadata(path="/a.jpg", size=1024, mtime_ns=0, inode=1),
                FileMetadata(path="/b.jpg", size=1024, mtime_ns=0, inode=2),
            ],
        )
        result = ScanResult(
            scan_id="s1",
            config=config,
            started_at=datetime.now(),
            files_scanned=100,
            duplicate_groups=[grp, grp],
            total_duplicates=4,
            total_reclaimable_bytes=8192,
        )
        d = result.to_dict()
        # Keys the hub now correctly reads:
        assert "total_duplicates" in d
        assert "duplicate_groups" in d
        assert "total_reclaimable_bytes" in d
        assert "files_scanned" in d
        # Keys the hub must NOT look for (old bug):
        assert "duplicates_found" not in d
        assert "groups_found" not in d
        # Values match what the hub extracts:
        assert d["total_duplicates"] == 4
        assert len(d["duplicate_groups"]) == 2
        assert d["total_reclaimable_bytes"] == 8192


# ---------------------------------------------------------------------------
# MissionVM
# ---------------------------------------------------------------------------

class TestMissionVM:
    def test_capabilities_by_name_empty_before_refresh(self):
        """Before refresh_from_coordinator, capabilities are empty."""
        vm = MissionVM()
        caps = vm.capabilities_by_name()
        assert isinstance(caps, dict)

    def test_session_is_empty_by_default(self):
        vm = MissionVM()
        assert vm.session.session_id == ""


# ---------------------------------------------------------------------------
# DiagnosticsVM
# ---------------------------------------------------------------------------

class TestDiagnosticsVM:
    def test_default_session(self):
        vm = DiagnosticsVM()
        assert vm.session.session_id == ""
