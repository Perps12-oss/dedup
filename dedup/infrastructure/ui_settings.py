"""
Persisted UI preferences (`ui_settings.json`), independent of engine `config.json`.

Used by `SettingsApplicationService`, `UIState`, and the CTK shell.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional


@dataclass
class AppSettings:
    """Persisted UI preferences."""

    theme_key: str = "obsidian_gold"
    density: str = "comfortable"  # "comfortable" | "cozy" | "compact"
    advanced_mode: bool = False
    reduced_motion: bool = False
    reduced_gradients: bool = False
    high_contrast: bool = False
    show_insight_drawer: bool = True
    mission_show_capabilities: bool = True
    mission_show_warnings: bool = True
    scan_show_saved_work: bool = True
    scan_show_events: bool = False
    scan_show_phase_metrics: bool = True
    review_show_preview: bool = True
    review_show_thumbnails: bool = True
    review_show_risk_flags: bool = True
    history_resumable_only: bool = False
    history_show_audit: bool = False
    diag_show_integrity: bool = True
    diag_show_events: bool = False
    window_width: int = 0
    window_height: int = 0
    window_x: int = -1
    window_y: int = -1
    custom_gradient_stops: Optional[list] = None
    sun_valley_shell: bool = True
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
