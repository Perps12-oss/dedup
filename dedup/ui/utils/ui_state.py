"""
Global UI state and settings for CEREBRO shell.
AppSettings is persisted alongside the main Config (see `dedup.infrastructure.ui_settings`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, List, Optional

from ...infrastructure.ui_settings import AppSettings, load_settings, save_settings

if TYPE_CHECKING:
    from ...application.services import SettingsApplicationService

# Re-export for callers that imported AppSettings from this module
__all__ = ["AppSettings", "UIState", "load_settings", "save_settings"]


class UIState:
    """
    Lightweight observable state container for the running app session.
    """

    def __init__(self) -> None:
        self.settings: AppSettings = load_settings()
        self._callbacks: dict[str, List[Callable]] = {}
        self._settings_service: Optional["SettingsApplicationService"] = None
        # Live scan state
        self.active_session_id: Optional[str] = None
        self.scan_phase: str = ""
        self.scan_status: str = "Idle"
        self.engine_health: str = "Healthy"
        self.checkpoint_ts: str = "—"
        self.active_workers: int = 0
        self.warning_count: int = 0

    def attach_settings_service(self, service: "SettingsApplicationService") -> None:
        """Route `save()` through `SettingsApplicationService` (shell boundary)."""
        self._settings_service = service

    def on(self, event: str, cb: Callable) -> None:
        self._callbacks.setdefault(event, []).append(cb)

    def emit(self, event: str, data: Any = None) -> None:
        for cb in self._callbacks.get(event, []):
            try:
                cb(data)
            except Exception:
                pass

    def save(self) -> None:
        if self._settings_service is not None:
            self._settings_service.persist_ui_preferences(self.settings)
        else:
            save_settings(self.settings)
