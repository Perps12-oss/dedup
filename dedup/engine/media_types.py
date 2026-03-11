"""
DEDUP Media Types - Category-based extension filtering for discovery.

Central mapping of categories (Images, Videos, Audio, etc.) to file extensions.
Used during discovery to filter by media type; extensions are normalized lowercase.
"""

from __future__ import annotations

from typing import Dict, Set, List, Optional

# Category key used in config/UI (lowercase, no spaces)
CATEGORY_ALL = "all"
CATEGORY_IMAGES = "images"
CATEGORY_VIDEOS = "videos"
CATEGORY_AUDIO = "audio"
CATEGORY_DOCUMENTS = "documents"
CATEGORY_ARCHIVES = "archives"

# Extension sets per category (lowercase, no leading dot)
_EXTENSIONS: Dict[str, Set[str]] = {
    CATEGORY_IMAGES: {
        "jpg", "jpeg", "png", "gif", "bmp", "webp", "tiff", "tif",
        "heic", "heif", "raw", "cr2", "nef", "arw", "dng", "ico",
    },
    CATEGORY_VIDEOS: {
        "mp4", "mov", "avi", "mkv", "webm", "flv", "wmv", "m4v",
        "mpg", "mpeg", "m2v", "3gp", "ogv", "ts",
    },
    CATEGORY_AUDIO: {
        "mp3", "wav", "aac", "flac", "ogg", "m4a", "wma", "aiff",
        "aif", "opus", "oga", "weba",
    },
    CATEGORY_DOCUMENTS: {
        "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx",
        "txt", "rtf", "odt", "ods", "odp", "csv", "md", "tex",
    },
    CATEGORY_ARCHIVES: {
        "zip", "rar", "7z", "tar", "gz", "bz2", "xz", "zst",
        "iso", "dmg",
    },
}


def get_extensions_for_category(category: Optional[str]) -> Optional[Set[str]]:
    """
    Return the set of extensions for a category, or None for "all" / unknown.

    Args:
        category: One of "all", "images", "videos", "audio", "documents", "archives"
                  (case-insensitive).

    Returns:
        Set of extensions (lowercase, no dot), or None if all files allowed.
    """
    if not category or (category := category.strip().lower()) == CATEGORY_ALL:
        return None
    return _EXTENSIONS.get(category).copy() if category in _EXTENSIONS else None


def get_category_label(category: str) -> str:
    """Human-readable label for a category key."""
    labels = {
        CATEGORY_ALL: "All Files",
        CATEGORY_IMAGES: "Images",
        CATEGORY_VIDEOS: "Videos",
        CATEGORY_AUDIO: "Audio",
        CATEGORY_DOCUMENTS: "Documents",
        CATEGORY_ARCHIVES: "Archives",
    }
    return labels.get(category.strip().lower(), "All Files")


def list_categories() -> List[str]:
    """Return category keys for UI (e.g. dropdown). Order: All, then the rest."""
    return [CATEGORY_ALL] + [
        CATEGORY_IMAGES, CATEGORY_VIDEOS, CATEGORY_AUDIO,
        CATEGORY_DOCUMENTS, CATEGORY_ARCHIVES,
    ]


def is_image_extension(ext: str) -> bool:
    """True if extension is in the Images category (for thumbnail support)."""
    e = ext.lower().lstrip(".")
    return e in _EXTENSIONS.get(CATEGORY_IMAGES, set())
