"""
Tests for Stage 0 foundation: interfaces, adapters, error_handling.

These tests verify that the new protocols and adapters work correctly
so that later refactors can rely on them.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from dedup.engine.interfaces import (
    CheckpointStore,
    EventPublisher,
    InventoryStore,
    SessionStore,
)
from dedup.engine.models import (
    CheckpointInfo,
    FileMetadata,
    PhaseStatus,
    ScanPhase,
)
from dedup.infrastructure.adapters import (
    CheckpointStoreAdapter,
    EventPublisherAdapter,
    InventoryStoreAdapter,
    SessionStoreAdapter,
)
from dedup.infrastructure.error_handling import (
    degrade_on_error,
    log_exceptions,
    return_on_error,
)
from dedup.infrastructure.persistence import Persistence
from dedup.orchestration.events import EventBus


def test_checkpoint_store_adapter(temp_dir):
    """CheckpointStoreAdapter delegates to Persistence correctly."""
    db = Persistence(db_path=temp_dir / "foundation.db")
    try:
        # Checkpoints require a session row (FK); create one first.
        SessionStoreAdapter(db).create("s1", "{}", "h", status="running")
        store: CheckpointStore = CheckpointStoreAdapter(db)
        store.write(
            "s1",
            ScanPhase.DISCOVERY,
            completed_units=10,
            total_units=100,
            status=PhaseStatus.RUNNING,
            metadata_json={"k": "v"},
        )
        cp = store.get("s1", ScanPhase.DISCOVERY)
        assert cp is not None
        assert cp.completed_units == 10
        assert cp.total_units == 100
        assert cp.metadata_json.get("k") == "v"
        assert store.get("s1", ScanPhase.FULL_HASH) is None
    finally:
        db.close()


def test_inventory_store_adapter(temp_dir):
    """InventoryStoreAdapter delegates to Persistence correctly."""
    db = Persistence(db_path=temp_dir / "inv.db")
    try:
        store: InventoryStore = InventoryStoreAdapter(db)
        files = [
            FileMetadata(path=str(temp_dir / "a.txt"), size=1, mtime_ns=0),
            FileMetadata(path=str(temp_dir / "b.txt"), size=2, mtime_ns=0),
        ]
        n = store.add_files_batch("s2", files)
        assert n == 2
        out = list(store.iter_by_session("s2"))
        assert len(out) == 2
        paths = {f.path for f in out}
        assert any("a.txt" in p for p in paths)
        assert any("b.txt" in p for p in paths)
    finally:
        db.close()


def test_session_store_adapter(temp_dir):
    """SessionStoreAdapter delegates to Persistence correctly."""
    db = Persistence(db_path=temp_dir / "sess.db")
    try:
        store: SessionStore = SessionStoreAdapter(db)
        assert store.get("s3") is None
        store.create("s3", '{"roots":[]}', "hash1", status="running")
        row = store.get("s3")
        assert row is not None
        store.update_status("s3", "completed", completed=True)
        row2 = store.get("s3")
        assert row2 is not None
    finally:
        db.close()


def test_event_publisher_adapter():
    """EventPublisherAdapter publishes to EventBus by event type name."""
    from dedup.orchestration.events import ScanEventType

    bus = EventBus()
    received = []

    def capture(ev):
        received.append((ev.event_type.name, ev.scan_id, ev.payload))

    bus.subscribe(ScanEventType.RESUME_REQUESTED, capture)
    publisher: EventPublisher = EventPublisherAdapter(bus)
    publisher.publish("RESUME_REQUESTED", "scan-99", {"reason": "test"})
    assert len(received) == 1
    assert received[0][0] == "RESUME_REQUESTED"
    assert received[0][1] == "scan-99"
    assert received[0][2]["reason"] == "test"


def test_log_exceptions_decorator(caplog):
    """log_exceptions logs and re-raises by default."""
    log = logging.getLogger("test.foundation")

    @log_exceptions(log, re_raise=True)
    def failing():
        raise ValueError("expected")

    with pytest.raises(ValueError, match="expected"):
        failing()
    assert "expected" in caplog.text or "failing" in caplog.text


def test_log_exceptions_no_rerase(caplog):
    """log_exceptions can suppress and return None."""
    log = logging.getLogger("test.foundation2")

    @log_exceptions(log, re_raise=False)
    def failing():
        raise RuntimeError("suppress")

    result = failing()
    assert result is None
    assert "suppress" in caplog.text or "failing" in caplog.text


def test_degrade_on_error_context_manager(caplog):
    """degrade_on_error suppresses specified exceptions and logs."""
    log = logging.getLogger("test.degrade")
    out = [None]

    with degrade_on_error("default", log, (ValueError,)):
        out[0] = "ok"
    assert out[0] == "ok"

    with degrade_on_error("default", log, (ValueError,)):
        raise ValueError("bad")
    assert "bad" in caplog.text or "Degraded" in caplog.text


def test_return_on_error_decorator(caplog):
    """return_on_error returns default on specified exception."""
    log = logging.getLogger("test.return_err")

    @return_on_error(0, log, (ZeroDivisionError,))
    def div(a, b):
        return a // b

    assert div(4, 2) == 2
    assert div(4, 0) == 0
    assert "ZeroDivisionError" in caplog.text or "div" in caplog.text
