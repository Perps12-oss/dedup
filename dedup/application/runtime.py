"""
Single composition root for the desktop app: one coordinator + application services.

Shells (CTK / legacy ttk) should own one `ApplicationRuntime` and pass services to controllers.
Pages must not import `ScanCoordinator`; they receive callbacks, store subscriptions, or services via the shell.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..orchestration.coordinator import ScanCoordinator
from .services import (
    HistoryApplicationService,
    ReviewApplicationService,
    ScanApplicationService,
    SettingsApplicationService,
)


@dataclass
class ApplicationRuntime:
    """
    One coordinator (event bus, persistence, workers) and thin facades for UI use-cases.

    Transitional: `coordinator` remains exposed for ProjectionHub wiring and pages not yet migrated.
    """

    coordinator: ScanCoordinator
    settings: SettingsApplicationService = field(default_factory=SettingsApplicationService)
    scan: ScanApplicationService = field(init=False)
    review: ReviewApplicationService = field(init=False)
    history: HistoryApplicationService = field(init=False)

    def __post_init__(self) -> None:
        c = self.coordinator
        self.scan = ScanApplicationService(c)
        self.review = ReviewApplicationService(c)
        self.history = HistoryApplicationService(c)
