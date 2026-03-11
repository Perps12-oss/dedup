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


def get_file_type(extension: str) -> str:
    """
    Get file type category from extension.
    
    Args:
        extension: File extension (with or without dot)
    
    Returns:
        File type category
    """
    ext = extension.lower().lstrip('.')
    
    image_exts = {'jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'tiff', 'heic', 'raw', 'cr2', 'nef'}
    video_exts = {'mp4', 'mov', 'avi', 'mkv', 'webm', 'flv', 'wmv', 'm4v', 'mpg', 'mpeg'}
    audio_exts = {'mp3', 'wav', 'aac', 'flac', 'ogg', 'm4a', 'wma', 'aiff'}
    doc_exts = {'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'rtf', 'odt'}
    archive_exts = {'zip', 'rar', '7z', 'tar', 'gz', 'bz2', 'xz'}
    code_exts = {'py', 'js', 'ts', 'java', 'cpp', 'c', 'h', 'go', 'rs', 'rb', 'php'}
    
    if ext in image_exts:
        return "image"
    if ext in video_exts:
        return "video"
    if ext in audio_exts:
        return "audio"
    if ext in doc_exts:
        return "document"
    if ext in archive_exts:
        return "archive"
    if ext in code_exts:
        return "code"
    
    return "other"


def count_files(directory: Path, max_count: int = 1000000) -> int:
    """
    Quickly count files in a directory (with limit).
    
    Args:
        directory: Directory to count
        max_count: Maximum count before stopping
    
    Returns:
        File count (or max_count if exceeded)
    """
    count = 0
    
    try:
        for item in directory.rglob('*'):
            if item.is_file():
                count += 1
                if count >= max_count:
                    return max_count
    except (OSError, PermissionError):
        pass
    
    return count
