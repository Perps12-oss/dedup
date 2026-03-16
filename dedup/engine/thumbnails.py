"""
DEDUP Thumbnails - Async thumbnail generation and disk cache for image duplicate groups.

Uses Pillow when available; degrades gracefully when not installed.
Cache key: path + size + mtime (or path only) to avoid stale thumbnails.
"""

from __future__ import annotations

import hashlib
import os
import threading
from pathlib import Path
from typing import Optional, Callable, Tuple

from .media_types import is_image_extension

_PILLOW_AVAILABLE = False
try:
    from PIL import Image  # type: ignore
    _PILLOW_AVAILABLE = True
except ImportError:
    Image = None  # type: ignore

# Default max edge for thumbnails
DEFAULT_SIZE: Tuple[int, int] = (128, 128)
# Max thumbnails to generate per batch (avoid flooding UI)
MAX_THUMBNAILS_PER_GROUP = 8


def get_cache_dir(base_dir: Optional[Path] = None) -> Path:
    """Return the thumbnails cache directory (creates if needed)."""
    if base_dir is not None:
        cache = Path(base_dir) / "thumbnails"
    else:
        if os.name == "nt":
            root = Path.home() / "AppData" / "Local" / "dedup"
        else:
            root = Path.home() / ".local" / "share" / "dedup"
        cache = root / "thumbnails"
    cache.mkdir(parents=True, exist_ok=True)
    return cache


def _cache_key(path: str, size: Tuple[int, int]) -> str:
    """Stable cache key for a file path and size (no mtime to keep cache valid across runs)."""
    norm = str(Path(path).resolve())
    return hashlib.sha256(f"{norm}|{size[0]}x{size[1]}".encode()).hexdigest()[:24]


def get_thumbnail_path(
    file_path: str,
    size: Tuple[int, int] = DEFAULT_SIZE,
    cache_dir: Optional[Path] = None,
) -> Optional[Path]:
    """
    Return path to a cached thumbnail image, or None if not an image or Pillow unavailable.
    Generates and caches the thumbnail if missing (blocking).
    """
    if not _PILLOW_AVAILABLE or not Image:
        return None
    path = Path(file_path)
    if not path.exists() or not path.is_file():
        return None
    ext = path.suffix.lower().lstrip(".")
    if not is_image_extension(ext):
        return None
    cache = get_cache_dir(cache_dir)
    key = _cache_key(file_path, size)
    cached = cache / f"{key}.png"
    if cached.exists():
        return cached
    try:
        with Image.open(path) as img:
            img.thumbnail(size, getattr(Image, "Resampling", Image).LANCZOS)
            img.convert("RGB").save(cached, "PNG")
        return cached
    except Exception:
        return None


def generate_thumbnails_async(
    file_paths: list[str],
    callback: Callable[[str, Optional[Path]], None],
    size: Tuple[int, int] = DEFAULT_SIZE,
    cache_dir: Optional[Path] = None,
    max_count: int = MAX_THUMBNAILS_PER_GROUP,
    cancel_event: Optional[threading.Event] = None,
) -> None:
    """
    Generate thumbnails in a background thread and invoke callback(path, thumbnail_path) for each.
    Only processes image paths; limits to max_count. Callback may be invoked from worker thread
    (caller should schedule UI updates with after() if needed).
    If cancel_event is set, worker stops and skips any pending callbacks.
    """
    image_paths = [
        p for p in file_paths
        if is_image_extension(Path(p).suffix.lower().lstrip("."))
    ][:max_count]

    def work():
        for p in image_paths:
            if cancel_event and cancel_event.is_set():
                return
            thumb = get_thumbnail_path(p, size=size, cache_dir=cache_dir)
            if cancel_event and cancel_event.is_set():
                return
            callback(p, thumb)

    t = threading.Thread(target=work, daemon=True)
    t.start()
