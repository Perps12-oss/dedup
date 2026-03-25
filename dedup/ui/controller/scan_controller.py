"""
ScanController — handles scan intents; drives coordinator and store intent lifecycle.

ScanPage (or app) calls handle_start_scan / handle_start_resume / handle_cancel.
Controller updates store.set_intent_lifecycle and delegates to coordinator.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Optional

from ...application.services import ScanApplicationService
from ...infrastructure.path_policy import canonical_scan_root
from ..state.store import IntentLifecycle, UIStateStore


class ScanController:
    """
    Handles scan commands. Updates store intent lifecycle (accepted/completed/failed);
    delegates start/cancel to ScanApplicationService. Callbacks (on_progress, on_complete, on_error)
    are passed at invoke time from the page.
    """

    def __init__(self, scan_service: ScanApplicationService, store: UIStateStore):
        self._scan = scan_service
        self._store = store

    def _post_to_ui(self, fn: Callable[[], None]) -> None:
        self._store.call_on_ui_thread(fn)

    def handle_start_scan(
        self,
        path: Path,
        options: Dict[str, Any],
        on_progress: Callable[[Any], None],
        on_complete: Callable[[Any], None],
        on_error: Callable[[str], None],
        on_cancel: Optional[Callable[[], None]] = None,
    ) -> str:
        """Start a new scan; set intent accepted then delegate to coordinator; on complete/error set lifecycle."""
        self._post_to_ui(lambda: self._store.set_intent_lifecycle(IntentLifecycle(status="accepted", intent_type="scan")))

        def _on_complete(result):
            self._post_to_ui(
                lambda: self._store.set_intent_lifecycle(IntentLifecycle(status="completed", intent_type="scan"))
            )
            self._post_to_ui(lambda: on_complete(result))

        def _on_error(err: str):
            self._post_to_ui(
                lambda: self._store.set_intent_lifecycle(
                    IntentLifecycle(status="failed", intent_type="scan", message=err)
                )
            )
            self._post_to_ui(lambda: on_error(err))

        root = canonical_scan_root(path)
        return self._scan.start_scan(
            [root],
            on_progress=on_progress,
            on_complete=_on_complete,
            on_error=_on_error,
            on_cancel=on_cancel,
            **options,
        )

    def handle_start_resume(
        self,
        scan_id: str,
        on_progress: Callable[[Any], None],
        on_complete: Callable[[Any], None],
        on_error: Callable[[str], None],
        on_cancel: Optional[Callable[[], None]] = None,
    ) -> str:
        """Resume a scan; set intent accepted then delegate to coordinator."""
        self._post_to_ui(lambda: self._store.set_intent_lifecycle(IntentLifecycle(status="accepted", intent_type="resume")))

        def _on_complete(result):
            self._post_to_ui(
                lambda: self._store.set_intent_lifecycle(IntentLifecycle(status="completed", intent_type="resume"))
            )
            self._post_to_ui(lambda: on_complete(result))

        def _on_error(err: str):
            self._post_to_ui(
                lambda: self._store.set_intent_lifecycle(
                    IntentLifecycle(status="failed", intent_type="resume", message=err)
                )
            )
            self._post_to_ui(lambda: on_error(err))

        return self._scan.start_scan(
            [],
            resume_scan_id=scan_id,
            on_progress=on_progress,
            on_complete=_on_complete,
            on_error=_on_error,
            on_cancel=on_cancel,
        )

    def handle_cancel(self) -> None:
        """Cancel current scan; set intent idle and delegate to coordinator."""
        self._post_to_ui(lambda: self._store.set_intent_lifecycle(IntentLifecycle(status="idle", intent_type="scan")))
        self._scan.cancel_scan()

    def get_resumable_scan_ids(self) -> list[str]:
        """Expose resumable scans for interruption zero-state actions."""
        return self._scan.get_resumable_scan_ids()
