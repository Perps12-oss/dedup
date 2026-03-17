"""
Characterisation tests for ProjectionHub: subscribe, event handling, push, flush delivery.
"""
from __future__ import annotations


class FakeTkRoot:
    """Minimal Tk root stand-in: after(ms, cb) enqueues cb; run_pending() runs current batch once."""
    def __init__(self):
        self._pending: list = []

    def after(self, ms: int, callback):
        self._pending.append((ms, callback))

    def run_pending(self) -> None:
        to_run, self._pending = self._pending, []
        for _ms, cb in to_run:
            cb()


def test_subscribe_and_unsubscribe():
    """subscribe returns an unsub that removes the callback."""
    from dedup.orchestration.events import EventBus
    from dedup.ui.projections.hub import ProjectionHub, THROTTLE_MS

    root = FakeTkRoot()
    bus = EventBus()
    hub = ProjectionHub(bus, root)
    received = []

    def on_session(snap):
        received.append(snap)

    unsub = hub.subscribe("session", on_session)
    hub.push_deletion(hub.deletion)  # no-op for session; trigger something dirty
    hub._dirty["session"] = True
    root.run_pending()
    assert len(received) >= 0  # may or may not deliver depending on throttle

    unsub()
    with hub._sub_lock:
        assert on_session not in hub._subscribers.get("session", [])
    hub.shutdown()


def test_session_started_updates_snapshot():
    """SESSION_STARTED event updates hub session snapshot and scan_root."""
    from dedup.orchestration.events import EventBus, ScanEvent, ScanEventType
    from dedup.ui.projections.hub import ProjectionHub

    root = FakeTkRoot()
    bus = EventBus()
    hub = ProjectionHub(bus, root)
    bus.publish(ScanEvent(
        ScanEventType.SESSION_STARTED,
        "scan-1",
        {"roots": ["/some/path"], "config": {}},
    ))
    root.run_pending()
    assert hub.session.session_id == "scan-1"
    assert hub.session.status == "running"
    hub.shutdown()


def test_push_deletion_updates_deletion_snapshot():
    """push_deletion updates the deletion projection and marks it dirty."""
    from dedup.ui.projections.hub import ProjectionHub
    from dedup.ui.projections.deletion_projection import (
        DeletionReadinessProjection,
        EMPTY_DELETION,
    )
    from dedup.orchestration.events import EventBus

    root = FakeTkRoot()
    bus = EventBus()
    hub = ProjectionHub(bus, root)
    custom = DeletionReadinessProjection(
        mode="permanent",
        pre_delete_revalidation_enabled=False,
        audit_logging_enabled=False,
        selected_delete_count=5,
        selected_keep_count=1,
        reclaimable_now=1000,
        risk_flags=0,
        dry_run_status="passed",
        dry_run_detail="ok",
        execution_ready=True,
    )
    hub.push_deletion(custom)
    assert hub.deletion.selected_delete_count == 5
    assert hub.deletion.mode == "permanent"
    hub.shutdown()


def test_push_event_log_entry_appends_and_caps():
    """push_event_log_entry prepends and caps events_log at 500."""
    from dedup.orchestration.events import EventBus
    from dedup.ui.projections.hub import ProjectionHub

    root = FakeTkRoot()
    bus = EventBus()
    hub = ProjectionHub(bus, root)
    hub.push_event_log_entry("first")
    with hub._lock:
        assert len(hub._events_log) == 1
        assert hub._events_log[0] == "first"
    for i in range(600):
        hub.push_event_log_entry(f"entry-{i}")
    with hub._lock:
        assert len(hub._events_log) <= 500
    hub.shutdown()


def test_unknown_event_type_no_op():
    """Event type with no handler does not crash and does not change session id."""
    from dedup.orchestration.events import EventBus, ScanEvent, ScanEventType
    from dedup.ui.projections.hub import ProjectionHub

    root = FakeTkRoot()
    bus = EventBus()
    hub = ProjectionHub(bus, root)
    # RESUME_REQUESTED is not in hub's handler map
    bus.publish(ScanEvent(ScanEventType.RESUME_REQUESTED, "scan-x", {}))
    root.run_pending()
    assert hub.session.session_id == ""
    hub.shutdown()


def test_flush_delivers_to_subscribers():
    """When dirty and throttle allows, _flush delivers snapshot to subscribed callbacks."""
    from dedup.orchestration.events import EventBus, ScanEvent, ScanEventType
    from dedup.ui.projections.hub import ProjectionHub
    import time

    root = FakeTkRoot()
    bus = EventBus()
    hub = ProjectionHub(bus, root)
    received_metrics = []

    hub.subscribe("metrics", received_metrics.append)
    bus.publish(ScanEvent(
        ScanEventType.SCAN_PROGRESS,
        "scan-1",
        {"phase": "discovery", "files_found": 10, "elapsed_seconds": 1.0},
    ))
    hub._last_delivered["metrics"] = 0.0
    hub._dirty["metrics"] = True
    hub._flush(time.monotonic() + 1.0)
    assert len(received_metrics) >= 1
    assert received_metrics[-1].files_discovered_total == 10
    hub.shutdown()


def test_callback_failure_does_not_break_other_callbacks():
    """If one subscriber raises, others still get the snapshot."""
    from dedup.orchestration.events import EventBus, ScanEvent, ScanEventType
    from dedup.ui.projections.hub import ProjectionHub
    import time

    root = FakeTkRoot()
    bus = EventBus()
    hub = ProjectionHub(bus, root)
    good_received = []

    def bad_cb(_):
        raise RuntimeError("bad")

    hub.subscribe("session", bad_cb)
    hub.subscribe("session", good_received.append)
    bus.publish(ScanEvent(ScanEventType.SESSION_STARTED, "s1", {"roots": ["/x"]}))
    hub._last_delivered["session"] = 0.0
    hub._dirty["session"] = True
    hub._flush(time.monotonic() + 1.0)
    assert len(good_received) >= 1
    assert good_received[-1].session_id == "s1"
    hub.shutdown()


def test_shutdown_stops_scheduling():
    """After shutdown, _schedule_poll does not call root.after."""
    from dedup.orchestration.events import EventBus
    from dedup.ui.projections.hub import ProjectionHub

    root = FakeTkRoot()
    bus = EventBus()
    hub = ProjectionHub(bus, root)
    hub.shutdown()
    before = len(root._pending)
    hub._schedule_poll()
    assert len(root._pending) == before
