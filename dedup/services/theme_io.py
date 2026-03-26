"""Theme bundle JSON serialization (no tk dependencies)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

from dedup.ui.theme.theme_config import ThemeConfig

THEME_EXPORT_FORMAT = "cerebro_theme_config_v1"


def build_export_payload(
    *,
    theme_key: str,
    theme_config: ThemeConfig,
    ui_flags: Dict[str, bool],
) -> Dict[str, Any]:
    return {
        "export_format": THEME_EXPORT_FORMAT,
        "exported_at_utc": datetime.now(timezone.utc).isoformat(),
        "theme_key": theme_key,
        "theme_config": theme_config.to_dict(),
        "ui": ui_flags,
    }


def export_theme_json_bytes(
    *,
    theme_key: str,
    theme_config: ThemeConfig,
    ui_flags: Dict[str, bool],
) -> bytes:
    payload = build_export_payload(theme_key=theme_key, theme_config=theme_config, ui_flags=ui_flags)
    return json.dumps(payload, indent=2, default=lambda o: list(o) if isinstance(o, tuple) else o).encode("utf-8")


def write_export_file(path: Path, *, theme_key: str, theme_config: ThemeConfig, ui_flags: Dict[str, bool]) -> None:
    path.write_bytes(export_theme_json_bytes(theme_key=theme_key, theme_config=theme_config, ui_flags=ui_flags))


def parse_import_payload(raw_text: str) -> Dict[str, Any]:
    return json.loads(raw_text)


def validate_import_format(data: Dict[str, Any]) -> Tuple[bool, str]:
    if data.get("export_format") != THEME_EXPORT_FORMAT:
        return False, f"Expected export_format {THEME_EXPORT_FORMAT!r}."
    return True, ""

