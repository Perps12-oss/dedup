"""
Safe invocation helper for UI callbacks (Tk commands).
"""
from __future__ import annotations

import logging
from tkinter import messagebox
from typing import Any, Callable, TypeVar

T = TypeVar("T")


def safe_ui_call(
    logger: logging.Logger,
    fn: Callable[..., T],
    *args: Any,
    title: str = "Error",
    user_message: str = "Something went wrong. Details were logged.",
    **kwargs: Any,
) -> T | None:
    try:
        return fn(*args, **kwargs)
    except Exception:
        logger.exception("UI callback failed: %s", getattr(fn, "__name__", repr(fn)))
        try:
            messagebox.showerror(title, user_message)
        except Exception:
            pass
        return None
