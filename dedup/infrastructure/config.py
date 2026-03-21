"""
DEDUP Configuration - Application settings management.

Configuration is stored in JSON format in the user's config directory.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List


@dataclass
class Config:
    """Application configuration."""

    # Scan defaults
    default_min_size: int = 1
    default_include_hidden: bool = False
    default_follow_symlinks: bool = False
    default_hash_algorithm: str = "xxhash64"

    # UI settings
    theme: str = "system"  # system, light, dark
    window_width: int = 1200
    window_height: int = 800

    # Performance
    max_workers: int = 4
    batch_size: int = 1000

    # Deletion
    default_deletion_policy: str = "trash"  # trash, permanent
    confirm_deletions: bool = True

    # History
    keep_history_days: int = 30
    max_history_entries: int = 100

    # Recent folders
    recent_folders: List[str] = field(default_factory=list)
    max_recent_folders: int = 10

    def __post_init__(self):
        """Validate and clamp config values to safe ranges."""
        if self.default_min_size < 0:
            self.default_min_size = 0
        if self.max_workers < 1:
            self.max_workers = 1
        if self.max_workers > 32:
            self.max_workers = 32
        if self.batch_size < 1:
            self.batch_size = 1
        if self.max_recent_folders < 1:
            self.max_recent_folders = 1
        if self.window_width < 600:
            self.window_width = 600
        if self.window_height < 400:
            self.window_height = 400
        # Keep only existing recent folders
        self.recent_folders = [f for f in self.recent_folders if Path(f).exists()][: self.max_recent_folders]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Config:
        """Create from dictionary."""
        # Filter to only valid fields
        valid_fields = {f for f in cls.__dataclass_fields__}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)


def get_config_dir() -> Path:
    """Get the configuration directory."""
    if os.name == "nt":  # Windows
        config_dir = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif os.name == "darwin":  # macOS
        config_dir = Path.home() / "Library" / "Application Support"
    else:  # Linux and others
        config_dir = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))

    dedup_dir = config_dir / "dedup"
    dedup_dir.mkdir(parents=True, exist_ok=True)
    return dedup_dir


def get_config_path() -> Path:
    """Get the configuration file path."""
    return get_config_dir() / "config.json"


def load_config() -> Config:
    """Load configuration from disk."""
    config_path = get_config_path()

    if not config_path.exists():
        return Config()

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return Config.from_dict(data)
    except (json.JSONDecodeError, IOError, KeyError):
        return Config()


def save_config(config: Config) -> bool:
    """Save configuration to disk."""
    try:
        config_path = get_config_path()
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config.to_dict(), f, indent=2)
        return True
    except IOError:
        return False


def add_recent_folder(config: Config, folder: Path | str) -> Config:
    """Add a folder to recent folders list."""
    folder_str = str(folder)

    # Remove if already exists (to move to front)
    if folder_str in config.recent_folders:
        config.recent_folders.remove(folder_str)

    # Add to front
    config.recent_folders.insert(0, folder_str)

    # Trim to max
    config.recent_folders = config.recent_folders[: config.max_recent_folders]

    return config
