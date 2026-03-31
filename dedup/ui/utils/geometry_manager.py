"""Window geometry persistence — restore on start, save on close."""

from __future__ import annotations

import logging
import tkinter as tk
from typing import Any

_log = logging.getLogger(__name__)

_MIN_W, _MIN_H = 760, 480


class WindowGeometryManager:
    """Restores and persists window size/position to AppSettings."""

    def __init__(self, root: tk.Tk, settings: Any) -> None:
        self._root = root
        self._settings = settings

    def restore(self) -> None:
        """Apply saved geometry; fall back to default if invalid."""
        s = self._settings
        w, h = int(s.window_width or 0), int(s.window_height or 0)
        x, y = int(s.window_x), int(s.window_y)
        try:
            if w >= _MIN_W and h >= _MIN_H:
                if x >= 0 and y >= 0:
                    self._root.geometry(f"{w}x{h}+{x}+{y}")
                else:
                    self._root.geometry(f"{w}x{h}")
                return
        except (tk.TclError, ValueError, TypeError) as e:
            _log.debug("Saved window geometry invalid, using default: %s", e)
        self._root.geometry("1180x760")

    def persist(self) -> None:
        """Save current geometry to settings (call before destroy)."""
        try:
            st = str(self._root.state() or "")
            if st.lower() == "zoomed":
                self._settings.window_width = 0
                self._settings.window_height = 0
                self._settings.window_x = -1
                self._settings.window_y = -1
            else:
                self._settings.window_width = self._root.winfo_width()
                self._settings.window_height = self._root.winfo_height()
                self._settings.window_x = self._root.winfo_x()
                self._settings.window_y = self._root.winfo_y()
        except Exception as e:
            _log.warning("Persist window geometry on exit failed: %s", e)
