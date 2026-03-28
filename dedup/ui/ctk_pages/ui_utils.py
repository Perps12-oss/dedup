"""
Shared UI utilities for CEREBRO pages.

Provides safe alternatives to CustomTkinter private APIs and common utilities.
"""

from __future__ import annotations

import logging
import tkinter as tk
from typing import Any, Callable, TypeVar

import customtkinter as ctk

_log = logging.getLogger(__name__)

T = TypeVar("T")


def resolve_color(color: tuple[str, str] | str | list[str]) -> str:
    """Resolve a (light, dark) pair to the **effective** theme color.

    Uses the same 0/1 index as ``CTkAppearanceModeBaseClass._apply_appearance_mode`` via
    ``AppearanceModeTracker.get_mode()`` so **System** mode (OS-driven light/dark) matches
    all CustomTkinter widgets. ``get_appearance_mode()`` alone is insufficient when the
    tracker state must stay in sync with tuple indexing.
    """
    if isinstance(color, str):
        return color
    if not isinstance(color, (tuple, list)) or len(color) != 2:
        _log.warning("Invalid color format: %r, defaulting to black", color)
        return "#000000"

    mode_idx = ctk.AppearanceModeTracker.get_mode()
    if mode_idx not in (0, 1):
        _log.warning("Unexpected appearance mode index %r; defaulting to dark", mode_idx)
        mode_idx = 1
    return str(color[mode_idx])


def safe_callback(
    callback: Callable[..., T] | None,
    *args: Any,
    context: str = "callback",
    default: T | None = None,
    **kwargs: Any,
) -> T | None:
    """Invoke a callback with logging on failure (replaces silent ``except: pass``)."""
    if callback is None:
        return default
    try:
        return callback(*args, **kwargs)
    except Exception:
        _log.exception("%s failed", context)
        return default


def cancel_after(widget: tk.Misc, timer_id: str | int | None) -> None:
    """Cancel a Tk ``after`` timer safely."""
    if timer_id is not None:
        try:
            widget.after_cancel(timer_id)
        except (ValueError, tk.TclError):
            pass


def copy_to_clipboard(widget: tk.Misc, text: str) -> bool:
    """Copy text to the system clipboard via the widget's toplevel."""
    if not text or text == "—":
        return False
    try:
        root = widget.winfo_toplevel()
        root.clipboard_clear()
        root.clipboard_append(text.strip())
        root.update_idletasks()
        return True
    except tk.TclError:
        _log.exception("Clipboard copy failed")
        return False
