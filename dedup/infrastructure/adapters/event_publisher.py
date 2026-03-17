"""
Event publisher adapter - Implements EventPublisher by delegating to EventBus.

Converts string event_type + scan_id + payload into ScanEvent and publishes.
Used so the engine can emit events without importing orchestration types
directly (dependency inversion). Callers can pass event type by name, e.g.
"RESUME_REQUESTED", "PHASE_REBUILD_STARTED".
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from ...orchestration.events import EventBus, ScanEvent, ScanEventType

_log = logging.getLogger(__name__)


class EventPublisherAdapter:
    """Implements EventPublisher by delegating to EventBus."""

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus

    def publish(self, event_type: str, scan_id: str, payload: Dict[str, Any]) -> None:
        try:
            ev_type = getattr(ScanEventType, event_type, None)
            if ev_type is None:
                _log.debug("Unknown event_type %r, skipping publish", event_type)
                return
            self._bus.publish(ScanEvent(event_type=ev_type, scan_id=scan_id, payload=payload))
        except Exception as e:
            _log.warning(
                "Event publish failed (event_type=%s, scan_id=%s): %s",
                event_type,
                scan_id,
                e,
                exc_info=True,
            )
