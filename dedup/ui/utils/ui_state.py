"""
Global UI state and settings for CEREBRO shell.
AppSettings is persisted alongside the main Config.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, List, Optional

from ..theme.theme_registry import DEFAULT_THEME


@dataclass
class AppSettings:
    """Persisted UI preferences."""

    theme_key: str = DEFAULT_THEME
    density: str = "comfortable"  # "comfortable" | "cozy" | "compact"
    advanced_mode: bool = False
    reduced_motion: bool = False
    reduced_gradients: bool = False
    high_contrast: bool = False
    show_insight_drawer: bool = True
    # Per-page toggles
    mission_show_capabilities: bool = True
    mission_show_warnings: bool = True
    scan_show_saved_work: bool = True
    scan_show_events: bool = False
    # Live Metrics card on Scan page; default True matches pre-gating behavior.
    scan_show_phase_metrics: bool = True
    review_show_preview: bool = True
    review_show_thumbnails: bool = True
    review_show_risk_flags: bool = True
    history_resumable_only: bool = False
    history_show_audit: bool = False
    diag_show_integrity: bool = True
    diag_show_events: bool = False
    # Window geometry (0×0 = use proportional default on next launch; also written when closing maximized)
    window_width: int = 0
    window_height: int = 0
    # Position (-1 = center on primary monitor next launch)
    window_x: int = -1
    window_y: int = -1
    # Optional multi-stop accent gradient [[0.0, "#hex"], ...] for top bar strip (2+ stops)
    custom_gradient_stops: Optional[list] = None
    # Sun Valley (sv-ttk) Fluent-style ttk base; falls back to clam if package missing
    sun_valley_shell: bool = True
    # Windows 11+ optional Mica-style backdrop (requires pywinstyles)
    win_mica_backdrop: bool = False

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "AppSettings":
        valid = {f for f in cls.__dataclass_fields__}
        defaults = asdict(cls())
        incoming = {k: v for k, v in d.items() if k in valid}
        merged = {**defaults, **incoming}
        return cls(**{k: merged[k] for k in valid})


def _settings_path() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    d = base / "dedup"
    d.mkdir(parents=True, exist_ok=True)
    return d / "ui_settings.json"


def load_settings() -> AppSettings:
    p = _settings_path()
    if not p.exists():
        return AppSettings()
    try:
        return AppSettings.from_dict(json.loads(p.read_text("utf-8")))
    except Exception:
        return AppSettings()


def save_settings(s: AppSettings) -> None:
    try:
        _settings_path().write_text(json.dumps(s.to_dict(), indent=2), encoding="utf-8")
    except Exception:
        pass


class UIState:
    """
    Lightweight observable state container for the running app session.
    """

    def __init__(self):
        self.settings: AppSettings = load_settings()
        self._callbacks: dict[str, List[Callable]] = {}
        # Live scan state
        self.active_session_id: Optional[str] = None
        self.scan_phase: str = ""
        self.scan_status: str = "Idle"
        self.engine_health: str = "Healthy"
        self.checkpoint_ts: str = "—"
        self.active_workers: int = 0
        self.warning_count: int = 0

    def on(self, event: str, cb: Callable) -> None:
        self._callbacks.setdefault(event, []).append(cb)

    def emit(self, event: str, data: Any = None) -> None:
        for cb in self._callbacks.get(event, []):
            try:
                cb(data)
            except Exception:
                pass

    def save(self) -> None:
        save_settings(self.settings)
