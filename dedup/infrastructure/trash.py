"""
DEDUP Trash - Helpers for the DEDUP fallback trash folder.

Only affects files moved to ~/.dedup/trash by DEDUP (fallback when system
trash is unavailable). Does not touch system recycle bin.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple


def get_dedup_trash_dir() -> Path:
    """Return the DEDUP fallback trash directory (same as in deletion engine)."""
    return Path.home() / ".dedup" / "trash"


def list_dedup_trash() -> Tuple[int, int, List[Path]]:
    """
    List contents of DEDUP trash folder.

    Returns:
        (file_count, total_bytes, list of file paths)
    """
    trash = get_dedup_trash_dir()
    if not trash.exists():
        return 0, 0, []
    count = 0
    total = 0
    paths: List[Path] = []
    try:
        for p in trash.iterdir():
            if p.is_file():
                count += 1
                try:
                    total += p.stat().st_size
                except OSError:
                    pass
                paths.append(p)
    except OSError:
        pass
    return count, total, paths


def empty_dedup_trash() -> Tuple[int, int]:
    """
    Permanently delete all files in the DEDUP trash folder.
    Does not remove the folder itself.

    Returns:
        (deleted_count, failed_count)
    """
    _, _, paths = list_dedup_trash()
    deleted = 0
    failed = 0
    for p in paths:
        try:
            p.unlink()
            deleted += 1
        except OSError:
            failed += 1
    return deleted, failed
