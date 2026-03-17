"""
DEDUP Adapters - Implementations of engine interfaces using existing infrastructure.

Use these as default injected dependencies so the engine can be tested with mocks
while production code continues to use the real Persistence and EventBus.
"""

from __future__ import annotations

from .event_publisher import EventPublisherAdapter
from .persistence_adapters import (
    CheckpointStoreAdapter,
    InventoryStoreAdapter,
    SessionStoreAdapter,
)

__all__ = [
    "CheckpointStoreAdapter",
    "InventoryStoreAdapter",
    "SessionStoreAdapter",
    "EventPublisherAdapter",
]
