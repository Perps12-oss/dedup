"""
ScanController — handles scan intents; drives coordinator and store intent lifecycle.

ScanPage (or app) calls handle_start_scan / handle_start_resume / handle_cancel.
Controller updates store.set_intent_lifecycle and delegates to coordinator.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Optional

from ...orchestration.coordinator import ScanCoordinator
from ..state.store import UIStateStore, IntentLifecycle


class ScanController:
    """
    Handles scan commands. Updates store intent lifecycle (accepted/completed/failed);
    delegates start/cancel to coordinator. Callbacks (on_progress, on_complete, on_error)
    are passed at invoke time from the page.
    """

    def __init__(self, coordinator: ScanCoordinator, store: UIStateStore):
        self._coordinator = coordinator
        self._store = store

    def handle_start_scan(
        self,
        path: Path,
        options: Dict[str, Any],
        on_progress: Callable[[Any], None],
        on_complete: Callable[[Any], None],
        on_error: Callable[[str], None],
    ) -> None:
        """Start a new scan; set intent accepted then delegate to coordinator; on complete/error set lifecycle."""
        self._store.set_intent_lifecycle(IntentLifecycle(status="accepted", intent_type="scan"))

        def _on_complete(result):
            self._store.set_intent_lifecycle(IntentLifecycle(status="completed", intent_type="scan"))
            on_complete(result)

        def _on_error(err: str):
            self._store.set_intent_lifecycle(IntentLifecycle(status="failed", intent_type="scan", message=err))
            on_error(err)

        self._coordinator.start_scan(
            roots=[path],
            on_progress=on_progress,
            on_complete=_on_complete,
            on_error=_on_error,
            **options,
        )

    def handle_start_resume(
        self,
        scan_id: str,
        on_progress: Callable[[Any], None],
        on_complete: Callable[[Any], None],
        on_error: Callable[[str], None],
    ) -> None:
        """Resume a scan; set intent accepted then delegate to coordinator."""
        self._store.set_intent_lifecycle(IntentLifecycle(status="accepted", intent_type="resume"))

        def _on_complete(result):
            self._store.set_intent_lifecycle(IntentLifecycle(status="completed", intent_type="resume"))
            on_complete(result)

        def _on_error(err: str):
            self._store.set_intent_lifecycle(IntentLifecycle(status="failed", intent_type="resume", message=err))
            on_error(err)

        self._coordinator.start_scan(
            roots=[],
            resume_scan_id=scan_id,
            on_progress=on_progress,
            on_complete=_on_complete,
            on_error=_on_error,
        )

    def handle_cancel(self) -> None:
        """Cancel current scan; set intent idle and delegate to coordinator."""
        self._store.set_intent_lifecycle(IntentLifecycle(status="idle", intent_type="scan"))
        self._coordinator.cancel_scan()

    def get_resumable_scan_ids(self) -> list[str]:
        """Expose resumable scans for interruption zero-state actions."""
        try:
            return list(self._coordinator.get_resumable_scan_ids() or [])
        except Exception:
            return []
