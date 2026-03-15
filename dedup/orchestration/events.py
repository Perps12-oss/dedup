"""
DEDUP Event Bus - Decoupled event communication.

Provides a simple publish-subscribe mechanism for UI components
to receive scan updates without direct coupling.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable, Dict, List, Any, Optional
import threading


class ScanEventType(Enum):
    """
    Types of scan events.

    Engine events (published by worker / pipeline):
      SESSION_*, PHASE_*, SCAN_*, DELETION_*, RESUME_*

    UI projection events (synthesised by ProjectionHub, never by the engine):
      UI_SESSION_SNAPSHOT     — SessionProjection ready for TopBar / StatusStrip
      UI_PHASE_SNAPSHOT       — Dict[phase_name, PhaseProjection] ready for timeline
      UI_METRICS_SNAPSHOT     — MetricsProjection ready for MetricCard row
      UI_RESUME_DECISION      — CompatibilityProjection + resume outcome
      UI_REVIEW_STATE_CHANGED — ReviewGroupProjection list changed
      UI_DELETION_PLAN_CHANGED— DeletionReadinessProjection changed
      UI_INTEGRITY_WARNING    — integrity issue detected
      UI_SESSION_TERMINAL     — session reached a terminal state

    Rule: no widget should subscribe to raw engine events directly.
    Use ProjectionHub.subscribe() instead.
    """
    SESSION_STARTED = auto()
    SESSION_COMPLETED = auto()
    SESSION_CANCELLED = auto()
    SESSION_FAILED = auto()
    PHASE_STARTED = auto()
    PHASE_PROGRESS = auto()
    PHASE_CHECKPOINTED = auto()
    PHASE_COMPLETED = auto()

    SCAN_STARTED = auto()
    SCAN_PROGRESS = auto()
    SCAN_COMPLETED = auto()
    SCAN_CANCELLED = auto()
    SCAN_ERROR = auto()

    DELETION_STARTED = auto()
    DELETION_PROGRESS = auto()
    DELETION_COMPLETED = auto()

    RESUME_REQUESTED = auto()
    RESUME_VALIDATED = auto()
    RESUME_REJECTED = auto()
    PHASE_REBUILD_STARTED = auto()

    # ---- UI projection event labels (synthesised, never by engine) ----
    UI_SESSION_SNAPSHOT      = auto()
    UI_PHASE_SNAPSHOT        = auto()
    UI_METRICS_SNAPSHOT      = auto()
    UI_RESUME_DECISION       = auto()
    UI_REVIEW_STATE_CHANGED  = auto()
    UI_DELETION_PLAN_CHANGED = auto()
    UI_INTEGRITY_WARNING     = auto()
    UI_SESSION_TERMINAL      = auto()


@dataclass
class ScanEvent:
    """A scan event with payload."""
    event_type: ScanEventType
    scan_id: str
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=lambda: __import__('time').time())


class EventBus:
    """
    Simple event bus for decoupled communication.
    
    Usage:
        bus = EventBus()
        
        def on_progress(event: ScanEvent):
            print(f"Progress: {event.payload}")
        
        bus.subscribe(ScanEventType.SCAN_PROGRESS, on_progress)
        bus.publish(ScanEvent(ScanEventType.SCAN_PROGRESS, "scan-123", {"percent": 50}))
    """
    
    def __init__(self):
        self._subscribers: Dict[ScanEventType, List[Callable[[ScanEvent], None]]] = {}
        self._lock = threading.Lock()
    
    def subscribe(
        self,
        event_type: ScanEventType,
        callback: Callable[[ScanEvent], None]
    ) -> Callable[[], None]:
        """
        Subscribe to an event type.
        
        Returns an unsubscribe function.
        """
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            self._subscribers[event_type].append(callback)
        
        def unsubscribe():
            self.unsubscribe(event_type, callback)
        
        return unsubscribe
    
    def unsubscribe(
        self,
        event_type: ScanEventType,
        callback: Callable[[ScanEvent], None]
    ):
        """Unsubscribe from an event type."""
        with self._lock:
            if event_type in self._subscribers:
                try:
                    self._subscribers[event_type].remove(callback)
                except ValueError:
                    pass
    
    def publish(self, event: ScanEvent):
        """Publish an event to all subscribers."""
        callbacks = []
        
        with self._lock:
            callbacks = self._subscribers.get(event.event_type, []).copy()
        
        for callback in callbacks:
            try:
                callback(event)
            except Exception:
                # Don't let subscriber errors break the bus
                pass


# Global event bus instance
_global_bus: Optional[EventBus] = None
_bus_lock = threading.Lock()


def get_event_bus() -> EventBus:
    """Get the global event bus."""
    global _global_bus
    
    with _bus_lock:
        if _global_bus is None:
            _global_bus = EventBus()
        return _global_bus
