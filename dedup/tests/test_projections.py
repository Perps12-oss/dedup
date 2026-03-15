"""
Tests for the UI projection layer — dataclasses, builders, and contracts.
"""
from __future__ import annotations

import pytest

from dedup.ui.projections.session_projection import (
    SessionProjection, EMPTY_SESSION, build_session_from_event,
)
from dedup.ui.projections.phase_projection import (
    PhaseProjection, PHASE_ORDER, PHASE_LABELS, canonical_phase,
    initial_phase_map, build_phase_from_checkpoint,
)
from dedup.ui.projections.metrics_projection import (
    MetricsProjection, EMPTY_METRICS, build_metrics_from_progress, merge_metrics,
)
from dedup.ui.projections.compatibility_projection import (
    CompatibilityProjection, EMPTY_COMPAT,
)
from dedup.ui.projections.review_projection import (
    ReviewGroupProjection, build_review_group_from_duplicate_group,
    build_review_groups_from_result,
)
from dedup.ui.projections.deletion_projection import (
    DeletionReadinessProjection, EMPTY_DELETION, build_deletion_from_review_vm,
)
from dedup.ui.projections.history_projection import (
    HistoryProjection, HistorySessionProjection, EMPTY_HISTORY,
    build_history_from_coordinator,
)


# ---------------------------------------------------------------------------
# Session projection
# ---------------------------------------------------------------------------

class TestSessionProjection:
    def test_empty_session_defaults(self):
        s = EMPTY_SESSION
        assert s.session_id == ""
        assert s.status == "idle"
        assert not s.is_active

    def test_is_active(self):
        s = SessionProjection(
            session_id="abc", status="running", created_at="", updated_at="",
            current_phase="discovery", phase_status="running",
            resume_policy="", resume_reason="", is_resumable=False,
            engine_health="healthy", warnings_count=0,
            config_hash="", schema_version=1, scan_root="",
        )
        assert s.is_active

    def test_build_from_event_minimal(self):
        proj = build_session_from_event(session_id="", status="idle")
        assert proj.session_id == ""
        assert proj.status == "idle"

    def test_frozen(self):
        with pytest.raises(AttributeError):
            EMPTY_SESSION.session_id = "x"


# ---------------------------------------------------------------------------
# Phase projection
# ---------------------------------------------------------------------------

class TestPhaseProjection:
    def test_canonical_phase_known(self):
        assert canonical_phase("size_reduction") == "size_reduction"
        assert canonical_phase("discovery") == "discovery"

    def test_initial_phase_map_keys(self):
        m = initial_phase_map()
        for phase in PHASE_ORDER:
            assert phase in m
            assert m[phase].status == "pending"

    def test_build_from_checkpoint(self):
        proj = build_phase_from_checkpoint(
            phase_name="discovery",
            status="completed",
            finalized=True,
            rows_written=100,
        )
        assert proj.phase_name == "discovery"
        assert proj.status == "completed"
        assert proj.finalized is True


# ---------------------------------------------------------------------------
# Metrics projection
# ---------------------------------------------------------------------------

class TestMetricsProjection:
    def test_empty_metrics(self):
        m = EMPTY_METRICS
        assert m.files_scanned == 0
        assert m.eta_seconds is None

    def test_merge_overrides(self):
        merged = merge_metrics(
            EMPTY_METRICS,
            files_scanned=100,
            eta_seconds=60.0,
        )
        assert merged.files_scanned == 100
        assert merged.eta_seconds == 60.0
        assert merged.files_skipped == 0  # unchanged from base


# ---------------------------------------------------------------------------
# Compatibility projection
# ---------------------------------------------------------------------------

class TestCompatibilityProjection:
    def test_empty_compat(self):
        c = EMPTY_COMPAT
        assert c.session_compatible is False
        assert c.overall_resume_outcome == "unknown"


# ---------------------------------------------------------------------------
# Review projection
# ---------------------------------------------------------------------------

class _FakeFile:
    def __init__(self, path, size):
        self.path = path
        self.size = size
        self.filename = path.split("/")[-1]


class _FakeGroup:
    def __init__(self, group_id, files, reclaimable_size=0):
        self.group_id = group_id
        self.group_hash = "abc123"
        self.files = files
        self.reclaimable_size = reclaimable_size


class TestReviewProjection:
    def test_build_from_group(self):
        files = [
            _FakeFile("/a/photo.jpg", 1024),
            _FakeFile("/b/photo.jpg", 1024),
        ]
        grp = _FakeGroup("g1", files, 1024)
        proj = build_review_group_from_duplicate_group(grp)
        assert proj.group_id == "g1"
        assert proj.file_count == 2
        assert proj.thumbnail_capable is True
        assert proj.verification_level == "full_hash"

    def test_has_risk_false(self):
        files = [_FakeFile("/a/f.txt", 10), _FakeFile("/b/f.txt", 10)]
        grp = _FakeGroup("g2", files)
        proj = build_review_group_from_duplicate_group(grp)
        assert not proj.has_risk

    def test_has_risk_large_group(self):
        files = [_FakeFile(f"/d/f{i}.txt", 10) for i in range(12)]
        grp = _FakeGroup("g3", files)
        proj = build_review_group_from_duplicate_group(grp)
        assert proj.has_risk


# ---------------------------------------------------------------------------
# History projection
# ---------------------------------------------------------------------------

class TestHistoryProjection:
    def test_empty_history(self):
        h = EMPTY_HISTORY
        assert h.total_scans == 0
        assert h.sessions == ()

    def test_session_projection_fields(self):
        s = HistorySessionProjection(
            scan_id="s1", status="completed", started_at="2025-01-01",
            duration_s=120.0, files_scanned=500, duplicates_found=10,
            reclaimable_bytes=2048, roots=("/tmp",), warning_count=0,
            is_resumable=False, resume_outcome="", resume_reason="",
            config_hash="abc", phase_summary="5/5 completed",
        )
        assert s.scan_id == "s1"
        assert s.status == "completed"
        assert s.phase_summary == "5/5 completed"


# ---------------------------------------------------------------------------
# Deletion projection
# ---------------------------------------------------------------------------

class TestDeletionProjection:
    def test_empty_deletion(self):
        d = EMPTY_DELETION
        assert d.execution_ready is False
        assert d.mode == "trash"
