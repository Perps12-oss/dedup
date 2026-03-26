"""Review page MVVM placeholder (Review page still uses store + controller)."""

from __future__ import annotations

from typing import Optional

from dedup.core.observable import Observable


class ReviewPageViewModel:
    """Holds observable placeholders for future Review MVVM migration."""

    def __init__(self) -> None:
        self.groups_total = Observable(0)
