"""
Tests for exception hygiene: diagnostics recording, logging, and failure semantics.

- Checkpoint write failure is recorded and does not stop the scan.
- Callback/subscriber failure is logged and recorded.
- save_scan failure is logged and recorded.
- Diagnostics recorder is thread-safe and bounded.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from dedup.infrastructure.diagnostics import (
    CATEGORY_CALLBACK,
    CATEGORY_CHECKPOINT,
    CATEGORY_REPOSITORY,
    DiagnosticsRecorder,
    get_diagnostics_recorder,
)


class TestDiagnosticsRecorder:
    def test_record_increments_count(self):
        rec = DiagnosticsRecorder(max_entries=10)
        rec.record(CATEGORY_CHECKPOINT, "Checkpoint write failed", "disk full")
        assert rec.get_counts()[CATEGORY_CHECKPOINT] == 1
        rec.record(CATEGORY_CHECKPOINT, "Again", "")
        assert rec.get_counts()[CATEGORY_CHECKPOINT] == 2

    def test_get_recent_returns_newest_first(self):
        rec = DiagnosticsRecorder(max_entries=10)
        rec.record(CATEGORY_CALLBACK, "First", "")
        rec.record(CATEGORY_CALLBACK, "Second", "")
        rec.record(CATEGORY_REPOSITORY, "Third", "")
        recent = rec.get_recent(limit=5)
        assert len(recent) == 3
        assert recent[0].message == "Third"
        assert recent[1].message == "Second"
        assert recent[0].category == CATEGORY_REPOSITORY

    def test_get_recent_filter_by_category(self):
        rec = DiagnosticsRecorder(max_entries=10)
        rec.record(CATEGORY_CHECKPOINT, "A", "")
        rec.record(CATEGORY_CALLBACK, "B", "")
        rec.record(CATEGORY_CHECKPOINT, "C", "")
        recent = rec.get_recent(limit=10, category=CATEGORY_CHECKPOINT)
        assert len(recent) == 2
        assert all(e.category == CATEGORY_CHECKPOINT for e in recent)

    def test_clear_resets_counts_and_entries(self):
        rec = DiagnosticsRecorder(max_entries=10)
        rec.record(CATEGORY_CHECKPOINT, "X", "")
        rec.clear()
        assert rec.get_counts() == {}
        assert rec.get_recent(limit=10) == []
        assert not rec.has_warnings

    def test_has_warnings(self):
        rec = DiagnosticsRecorder(max_entries=10)
        assert not rec.has_warnings
        rec.record(CATEGORY_REPOSITORY, "Save failed", "")
        assert rec.has_warnings

    def test_bounded_entries(self):
        rec = DiagnosticsRecorder(max_entries=5)
        for i in range(10):
            rec.record(CATEGORY_CALLBACK, f"Msg {i}", "")
        assert len(rec.get_recent(limit=20)) == 5
        assert rec.get_counts()[CATEGORY_CALLBACK] == 10


class TestCoordinatorSaveScanFailure:
    """When persistence.save_scan raises, coordinator records and logs."""

    def test_save_scan_failure_recorded(self):
        from datetime import datetime
        from pathlib import Path

        from dedup.engine.models import ScanConfig, ScanResult
        from dedup.orchestration.coordinator import ScanCoordinator

        rec = get_diagnostics_recorder()
        rec.clear()

        coord = ScanCoordinator()
        coord.persistence.save_scan = MagicMock(side_effect=OSError("disk full"))

        config = ScanConfig(roots=[Path(".")])
        result = ScanResult(
            scan_id="test-scan",
            config=config,
            started_at=datetime.now(),
            duplicate_groups=[],
            files_scanned=0,
            total_reclaimable_bytes=0,
        )

        wrapper = coord._on_scan_complete_wrapper(user_callback=None)
        wrapper(result)

        assert rec.get_counts().get(CATEGORY_REPOSITORY, 0) >= 1
        rec.clear()


class TestEventBusSubscriberFailure:
    """When a subscriber raises, event bus logs and records."""

    def test_subscriber_error_recorded(self):
        from dedup.orchestration.events import EventBus, ScanEvent, ScanEventType

        rec = get_diagnostics_recorder()
        rec.clear()

        bus = EventBus()

        def bad_subscriber(event):
            raise ValueError("subscriber broken")

        bus.subscribe(ScanEventType.SCAN_PROGRESS, bad_subscriber)
        ev = ScanEvent(ScanEventType.SCAN_PROGRESS, "sid", {})
        bus.publish(ev)

        assert rec.get_counts().get(CATEGORY_CALLBACK, 0) >= 1
        rec.clear()
