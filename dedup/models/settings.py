"""Settings shapes for ViewModels (subset / mirror of AppSettings)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from .theme import GradientStop


@dataclass(frozen=True)
class UISettings:
    """Portable UI preferences used by ViewModels."""

    theme_key: str
    density: str
    advanced_mode: bool
    reduced_motion: bool
    reduced_gradients: bool
    high_contrast: bool
    custom_gradient_stops: Optional[List[GradientStop]] = None


@dataclass(frozen=True)
class MissionSettings:
    """Mission page toggles."""

    show_capabilities: bool = True
    show_warnings: bool = True


def gradient_stops_from_app(raw: Optional[list]) -> Optional[List[GradientStop]]:
    if not raw:
        return None
    out: List[GradientStop] = []
    for item in raw:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            try:
                pos = float(item[0])
                col = str(item[1]).strip()
                if col and not col.startswith("#"):
                    col = "#" + col
                if len(col) == 7:
                    out.append(GradientStop(position=max(0.0, min(1.0, pos)), color=col))
            except (TypeError, ValueError):
                continue
    out.sort(key=lambda x: x.position)
    return out if len(out) >= 2 else None
