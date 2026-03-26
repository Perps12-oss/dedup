"""Theme-related models (parallel to ThemeDict / theme registry)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Tuple


@dataclass(frozen=True)
class GradientStop:
    position: float  # 0..1
    color: str  # #RRGGBB


@dataclass(frozen=True)
class ThemeTokens:
    """
    Snapshot of resolved theme tokens. Wraps the full token dict from ThemeManager.
    """

    values: Dict[str, Any]

    @classmethod
    def from_mapping(cls, m: Mapping[str, Any]) -> ThemeTokens:
        return cls(values=dict(m))

    def as_dict(self) -> Dict[str, Any]:
        return dict(self.values)

    def get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)


@dataclass(frozen=True)
class ContrastSummary:
    """WCAG contrast summary for accent vs background (informative)."""

    ratio_label: str
    passes_aa_normal: bool
    passes_aa_large: bool
    fg_sample: str
    bg_sample: str


def stops_to_tuples(stops: List[GradientStop]) -> List[Tuple[float, str]]:
    return [(s.position, s.color) for s in stops]


def tuples_to_stops(raw: Optional[List[Tuple[float, str]]]) -> List[GradientStop]:
    if not raw:
        return []
    return [GradientStop(position=p, color=c) for p, c in raw]
