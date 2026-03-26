"""ScanCoordinator façade for Mission ViewModel."""

from __future__ import annotations

from typing import Any, Dict, List, TYPE_CHECKING

if TYPE_CHECKING:
    from dedup.orchestration.coordinator import ScanCoordinator


class RuntimeAdapter:
    def __init__(self, coordinator: "ScanCoordinator") -> None:
        self._coord = coordinator

    def get_recent_folders(self) -> List[str]:
        try:
            return list(self._coord.get_recent_folders() or [])[:10]
        except Exception:
            return []

    def get_history(self, limit: int) -> List[Dict[str, Any]]:
        try:
            return list(self._coord.get_history(limit=limit) or [])
        except Exception:
            return []

    def get_resumable_scan_ids(self) -> List[str]:
        try:
            return list(self._coord.get_resumable_scan_ids() or [])
        except Exception:
            return []
