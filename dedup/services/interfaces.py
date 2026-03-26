"""Abstract ports for ViewModels (Protocol-based; easy to mock)."""

from __future__ import annotations

from typing import Any, Callable, List, Protocol

from dedup.models.theme import ThemeTokens


class IThemeManager(Protocol):
    """Resolved theme tokens and subscription."""

    @property
    def current_key(self) -> str: ...

    def get_tokens(self) -> ThemeTokens: ...

    def subscribe(self, callback: Callable[[ThemeTokens], None]) -> None: ...

    def unsubscribe(self, callback: Callable[[ThemeTokens], None]) -> None: ...


class IStateStore(Protocol):
    """Read-only access to UI app state + subscription."""

    def subscribe(
        self,
        callback: Callable[[Any], None],
        *,
        fire_immediately: bool = True,
    ) -> Callable[[], None]: ...

    @property
    def state(self) -> Any: ...


class IRuntime(Protocol):
    """Coordinator façade for Mission page data (no tk)."""

    def get_recent_folders(self) -> List[str]: ...

    def get_history(self, limit: int) -> List[dict[str, Any]]: ...

    def get_resumable_scan_ids(self) -> List[str]: ...
