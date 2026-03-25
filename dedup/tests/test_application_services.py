"""ApplicationRuntime and service facades delegate to coordinator without UI imports."""

from __future__ import annotations

from dedup.application.runtime import ApplicationRuntime
from dedup.orchestration.coordinator import ScanCoordinator


def test_application_runtime_exposes_same_coordinator_for_hub():
    c = ScanCoordinator()
    rt = ApplicationRuntime(c)
    assert rt.scan.coordinator is c
    assert rt.review.get_last_result() is c.get_last_result()
    assert rt.history.get_history(limit=1) == c.get_history(limit=1)


def test_scan_service_resumable_returns_list():
    c = ScanCoordinator()
    rt = ApplicationRuntime(c)
    # No checkpoint dir activity — expect empty list, not exception
    ids = rt.scan.get_resumable_scan_ids()
    assert isinstance(ids, list)
