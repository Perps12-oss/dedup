"""
Canonical path policy for user-selected scan roots and UI paths.

Single place for resolve/validation rules so engine and UI stay aligned.
"""

from __future__ import annotations

import logging
from pathlib import Path

_log = logging.getLogger(__name__)


def canonical_scan_root(path: Path | str) -> Path:
    """
    Normalize a user-supplied folder root for scanning.

    Uses :meth:`Path.resolve` for a stable absolute path. On failure (e.g. missing
    path on some platforms), returns the path expanded as far as possible and logs.
    """
    p = Path(path)
    try:
        return p.resolve()
    except (OSError, RuntimeError) as e:
        _log.warning("canonical_scan_root: resolve failed for %s — using as-is: %s", p, e)
        try:
            return p.absolute()
        except (OSError, RuntimeError):
            return p
