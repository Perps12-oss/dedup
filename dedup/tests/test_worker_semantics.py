from __future__ import annotations

from datetime import datetime
from pathlib import Path

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
