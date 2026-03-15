"""
DEDUP Utilities - Helper functions.
"""

from __future__ import annotations

from pathlib import Path
from typing import Union


def format_bytes(size_bytes: int) -> str:
    """
    Format bytes as human-readable string.
    
    Args:
        size_bytes: Size in bytes
    
    Returns:
        Human-readable string (e.g., "1.5 GB")
    """
    if size_bytes < 0:
        return "Unknown"
    
    if size_bytes == 0:
        return "0 B"
    
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    size = float(size_bytes)
    unit_index = 0
    
    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1
    
    if unit_index == 0:
        return f"{int(size)} {units[unit_index]}"
    
    if size >= 100:
        return f"{int(size)} {units[unit_index]}"
    
    return f"{size:.1f} {units[unit_index]}"


def format_duration(seconds: float) -> str:
    """
    Format duration in seconds as human-readable string.
    
    Args:
        seconds: Duration in seconds
    
    Returns:
        Human-readable string (e.g., "2h 15m" or "45s")
    """
    if seconds < 0:
        return "Unknown"
    
    if seconds < 60:
        return f"{int(seconds)}s"
    
    minutes = int(seconds // 60)
    remaining_seconds = int(seconds % 60)
    
    if minutes < 60:
        if remaining_seconds > 0:
            return f"{minutes}m {remaining_seconds}s"
        return f"{minutes}m"
    
    hours = minutes // 60
    remaining_minutes = minutes % 60
    
    if remaining_minutes > 0:
        return f"{hours}h {remaining_minutes}m"
    return f"{hours}h"


def ensure_dir(path: Union[str, Path]) -> Path:
    """
    Ensure a directory exists, creating it if necessary.
    
    Args:
        path: Directory path
    
    Returns:
        Path object
    """
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def truncate_path(path: Union[str, Path], max_length: int = 60) -> str:
    """
    Truncate a path for display.
    
    Args:
        path: File path
        max_length: Maximum length
    
    Returns:
        Truncated path string
    """
    path_str = str(path)
    
    if len(path_str) <= max_length:
        return path_str
    
    # Keep the filename and truncate the middle
    path_obj = Path(path_str)
    filename = path_obj.name
    
    if len(filename) >= max_length - 3:
        return "..." + filename[-(max_length - 3):]
    
    prefix_length = max_length - len(filename) - 3
    prefix = str(path_obj.parent)[:prefix_length]
    
    return f"{prefix}.../{filename}"
