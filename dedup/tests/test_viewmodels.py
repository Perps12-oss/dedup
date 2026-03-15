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
