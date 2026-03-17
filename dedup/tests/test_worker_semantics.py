"""
Worker tests: callback semantics, events, and lifecycle.

Characterisation tests: start/cancel/join, get_result/get_error, scan_id, double-start raises.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from dedup.engine.models import ScanConfig, ScanResult
from dedup.orchestration.events import EventBus, ScanEventType
from dedup.orchestration.worker import ScanWorker


class _FakePipeline:
    def __init__(self, config, result: ScanResult):
        self.scan_id = "scan-test"
        self._result = result
        self._config = config

    def run(self, progress_cb=None, event_bus=None):
        return self._result

    def cancel(self):
        return None


def _result_with_errors(config: ScanConfig) -> ScanResult:
    return ScanResult(
        scan_id="scan-test",
        config=config,
        started_at=datetime.now(),
        completed_at=datetime.now(),
        files_scanned=1,
        bytes_scanned=1,
        errors=["pipeline partial failure"],
    )


def _result_success(config: ScanConfig) -> ScanResult:
    return ScanResult(
        scan_id="scan-test",
        config=config,
        started_at=datetime.now(),
        completed_at=datetime.now(),
        files_scanned=1,
        bytes_scanned=1,
        errors=[],
    )


def test_worker_treats_result_errors_as_failure(monkeypatch, temp_dir):
    config = ScanConfig(roots=[Path(temp_dir)])
    event_bus = EventBus()
    result = _result_with_errors(config)

    def _factory(*args, **kwargs):
        return _FakePipeline(config, result)

    monkeypatch.setattr("dedup.orchestration.worker.ScanPipeline", _factory)

    seen_events = []
    for et in (ScanEventType.SESSION_FAILED, ScanEventType.SCAN_ERROR, ScanEventType.SCAN_COMPLETED):
        event_bus.subscribe(et, lambda e, _et=et: seen_events.append(_et))

    on_complete = []
    on_error = []
    worker = ScanWorker(config=config, event_bus=event_bus)
    worker.callbacks.on_complete = lambda _r: on_complete.append(1)
    worker.callbacks.on_error = lambda err: on_error.append(err)

    worker.start()
    assert worker.join(timeout=5.0)

    assert len(on_complete) == 0
    assert len(on_error) == 1
    assert ScanEventType.SESSION_FAILED in seen_events
    assert ScanEventType.SCAN_ERROR in seen_events
    assert ScanEventType.SCAN_COMPLETED not in seen_events


def test_worker_emits_completion_for_clean_result(monkeypatch, temp_dir):
    config = ScanConfig(roots=[Path(temp_dir)])
    event_bus = EventBus()
    result = _result_success(config)

    def _factory(*args, **kwargs):
        return _FakePipeline(config, result)

    monkeypatch.setattr("dedup.orchestration.worker.ScanPipeline", _factory)

    seen_events = []
    for et in (ScanEventType.SESSION_COMPLETED, ScanEventType.SCAN_COMPLETED, ScanEventType.SCAN_ERROR):
        event_bus.subscribe(et, lambda e, _et=et: seen_events.append(_et))

    on_complete = []
    on_error = []
    worker = ScanWorker(config=config, event_bus=event_bus)
    worker.callbacks.on_complete = lambda _r: on_complete.append(1)
    worker.callbacks.on_error = lambda err: on_error.append(err)

    worker.start()
    assert worker.join(timeout=5.0)

    assert len(on_complete) == 1
    assert len(on_error) == 0
    assert ScanEventType.SESSION_COMPLETED in seen_events
    assert ScanEventType.SCAN_COMPLETED in seen_events
    assert ScanEventType.SCAN_ERROR not in seen_events


def test_worker_scan_id_after_start(monkeypatch, temp_dir):
    """scan_id is available after start() and matches the pipeline."""
    config = ScanConfig(roots=[Path(temp_dir)])
    event_bus = EventBus()
    result = _result_success(config)

    def _factory(*args, **kwargs):
        return _FakePipeline(config, result)

    monkeypatch.setattr("dedup.orchestration.worker.ScanPipeline", _factory)
    worker = ScanWorker(config=config, event_bus=event_bus)
    assert worker.scan_id is None
    worker.start()
    assert worker.scan_id == "scan-test"
    worker.join(timeout=5.0)


def test_worker_get_result_after_success(monkeypatch, temp_dir):
    """get_result() returns the ScanResult after successful completion."""
    config = ScanConfig(roots=[Path(temp_dir)])
    event_bus = EventBus()
    result = _result_success(config)

    def _factory(*args, **kwargs):
        return _FakePipeline(config, result)

    monkeypatch.setattr("dedup.orchestration.worker.ScanPipeline", _factory)
    worker = ScanWorker(config=config, event_bus=event_bus)
    worker.start()
    worker.join(timeout=5.0)
    got = worker.get_result()
    assert got is not None
    assert got.scan_id == result.scan_id
    assert got.files_scanned == 1


def test_worker_get_error_after_failure(monkeypatch, temp_dir):
    """get_error() returns the error string when result has errors."""
    config = ScanConfig(roots=[Path(temp_dir)])
    event_bus = EventBus()
    result = _result_with_errors(config)

    def _factory(*args, **kwargs):
        return _FakePipeline(config, result)

    monkeypatch.setattr("dedup.orchestration.worker.ScanPipeline", _factory)
    worker = ScanWorker(config=config, event_bus=event_bus)
    worker.start()
    worker.join(timeout=5.0)
    err = worker.get_error()
    assert err is not None
    assert "pipeline partial failure" in err


def test_worker_start_when_already_running_raises(monkeypatch, temp_dir):
    """start() when already running raises RuntimeError."""
    import threading
    config = ScanConfig(roots=[Path(temp_dir)])
    event_bus = EventBus()
    result = _result_success(config)
    release = threading.Event()

    class _BlockingFakePipeline(_FakePipeline):
        def run(self, progress_cb=None, event_bus=None):
            release.wait(timeout=5.0)
            return self._result

    def _factory(*args, **kwargs):
        return _BlockingFakePipeline(config, result)

    monkeypatch.setattr("dedup.orchestration.worker.ScanPipeline", _factory)
    worker = ScanWorker(config=config, event_bus=event_bus)
    worker.start()
    try:
        with pytest.raises(RuntimeError, match="already running"):
            worker.start()
    finally:
        release.set()
        worker.join(timeout=5.0)


def test_worker_cancel_then_join(monkeypatch, temp_dir):
    """cancel() then join() returns True when thread has stopped."""
    config = ScanConfig(roots=[Path(temp_dir)])
    event_bus = EventBus()
    result = _result_success(config)

    def _factory(*args, **kwargs):
        return _FakePipeline(config, result)

    monkeypatch.setattr("dedup.orchestration.worker.ScanPipeline", _factory)
    worker = ScanWorker(config=config, event_bus=event_bus)
    worker.start()
    worker.cancel()
    done = worker.join(timeout=5.0)
    assert done is True
    assert not worker.is_running
