"""
Application-facing service facades.

UI shells and controllers depend on these types — not on orchestration internals.
Orchestration stays behind `ScanCoordinator`; services are the stable boundary for the UI layer.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ..engine.models import DeletionPlan, DeletionResult, ScanResult
from ..infrastructure.config import Config, load_config, save_config
from ..infrastructure.ui_settings import (
    AppSettings,
)
from ..infrastructure.ui_settings import (
    load_settings as load_ui_preferences_json,
)
from ..infrastructure.ui_settings import (
    save_settings as save_ui_preferences_json,
)
from ..orchestration.coordinator import ScanCoordinator

_log = logging.getLogger(__name__)


class ScanApplicationService:
    """Start / resume / cancel scans and query scan lifecycle. Wraps `ScanCoordinator`."""

    def __init__(self, coordinator: ScanCoordinator) -> None:
        self._c = coordinator

    @property
    def coordinator(self) -> ScanCoordinator:
        """Transitional: hub and event bus still attach to the underlying coordinator."""
        return self._c

    def start_scan(
        self,
        roots: List[Path],
        on_progress: Optional[Callable[[Any], None]] = None,
        on_complete: Optional[Callable[[ScanResult], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
        on_cancel: Optional[Callable[[], None]] = None,
        resume_scan_id: Optional[str] = None,
        **scan_options: Any,
    ) -> str:
        return self._c.start_scan(
            roots,
            on_progress=on_progress,
            on_complete=on_complete,
            on_error=on_error,
            on_cancel=on_cancel,
            resume_scan_id=resume_scan_id,
            **scan_options,
        )

    def cancel_scan(self) -> None:
        self._c.cancel_scan()

    @property
    def is_scanning(self) -> bool:
        return self._c.is_scanning

    def get_active_scan_id(self) -> Optional[str]:
        return self._c.get_active_scan_id()

    def get_last_result(self) -> Optional[ScanResult]:
        return self._c.get_last_result()

    def get_resumable_scan_ids(self) -> List[str]:
        try:
            return list(self._c.get_resumable_scan_ids() or [])
        except Exception as e:
            _log.warning("ScanApplicationService.get_resumable_scan_ids failed: %s", e)
            return []


class ReviewApplicationService:
    """Deletion plan / execute / last result. Wraps coordinator review operations."""

    def __init__(self, coordinator: ScanCoordinator) -> None:
        self._c = coordinator

    def get_last_result(self) -> Optional[ScanResult]:
        return self._c.get_last_result()

    def create_deletion_plan(
        self,
        result: Optional[ScanResult] = None,
        keep_strategy: str = "first",
        group_keep_paths: Optional[Dict[str, str]] = None,
    ) -> Optional[DeletionPlan]:
        return self._c.create_deletion_plan(
            result=result,
            keep_strategy=keep_strategy,
            group_keep_paths=group_keep_paths,
        )

    def execute_deletion(
        self,
        plan: DeletionPlan,
        dry_run: bool = False,
        progress_cb: Optional[Callable[[int, int, str], bool]] = None,
    ) -> DeletionResult:
        return self._c.execute_deletion(plan, dry_run=dry_run, progress_cb=progress_cb)


class HistoryApplicationService:
    """History list, load/delete session, resumable IDs, recent folders."""

    def __init__(self, coordinator: ScanCoordinator) -> None:
        self._c = coordinator

    @property
    def coordinator(self) -> ScanCoordinator:
        """For history projection builders that still expect a coordinator (transitional)."""
        return self._c

    def get_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self._c.get_history(limit=limit)

    def load_scan(self, scan_id: str) -> Optional[ScanResult]:
        return self._c.load_scan(scan_id)

    def delete_scan(self, scan_id: str) -> bool:
        return self._c.delete_scan(scan_id)

    def get_resumable_scan_ids(self) -> List[str]:
        return self._c.get_resumable_scan_ids()

    def get_recent_folders(self) -> List[str]:
        return self._c.get_recent_folders()

    def add_recent_folder(self, folder: Path) -> None:
        self._c.add_recent_folder(folder)


class SettingsApplicationService:
    """Persisted JSON: engine `config.json` and UI `ui_settings.json`. Shells use this — not raw `load_config` / `save_settings` from pages."""

    def load(self) -> Config:
        return load_config()

    def save(self, config: Config) -> None:
        save_config(config)

    def load_ui_preferences(self) -> AppSettings:
        """Load `AppSettings` from `ui_settings.json`."""
        return load_ui_preferences_json()

    def persist_ui_preferences(self, settings: AppSettings) -> None:
        """Write `AppSettings` to `ui_settings.json`."""
        save_ui_preferences_json(settings)
