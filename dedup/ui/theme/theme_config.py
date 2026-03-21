"""
Serializable theme preferences beyond a single preset key.

`AppSettings.theme_key` remains the persisted source of truth for the active preset;
this model supports future custom gradients, history, and import/export (Phase 2+).
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Literal, Optional, Tuple

AppearanceMode = Literal["light", "dark"]


@dataclass
class ThemeConfig:
    theme_key: str = "cerebro_noir"
    appearance_mode: AppearanceMode = "dark"
    transition_duration_ms: int = 0
    reduced_motion: bool = False
    custom_gradient_stops: Optional[List[Tuple[float, str]]] = None
    recent_custom_keys: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ThemeConfig":
        valid = {f for f in cls.__dataclass_fields__}
        kw = {k: v for k, v in d.items() if k in valid}
        return cls(**kw)
