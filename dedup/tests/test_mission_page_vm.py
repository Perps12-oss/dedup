"""MissionPageViewModel unit tests (no tk)."""

from dedup.ui.viewmodels.mission_page_vm import MissionPageViewModel


class _FakeCoord:
    def get_recent_folders(self):
        return ["/a", "/b"]

    def get_history(self, limit=50):
        return []

    def get_resumable_scan_ids(self):
        return []


def test_mission_page_vm_refresh_updates_observables():
    vm = MissionPageViewModel(_FakeCoord())
    seen = []

    vm.engine_status.subscribe(lambda v: seen.append(v.hash_backend))
    vm.refresh_from_coordinator()
    assert len(seen) >= 1
