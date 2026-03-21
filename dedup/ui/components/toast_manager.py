"""
Toast notifications — short-lived, non-modal messages in the bottom-right of the window.

Attach once to the root window (e.g. ``CerebroApp`` uses ``ToastManager(self.root)``).

Usage::

    toast = ToastManager(root)
    toast.show("Scan complete.", ms=4500, reduced_motion=False)

``show`` replaces any visible toast. When ``reduced_motion`` is False, the toast
slides up with a short ease; otherwise it appears in place. The window does not
steal keyboard focus.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Optional

from ..utils.animations import animate_scalar


class ToastManager:
    def __init__(self, root: tk.Tk) -> None:
        self._root = root
        self._after_id: Optional[str] = None
        self._anim_after: Optional[str] = None

    def show(self, message: str, ms: int = 3200, *, reduced_motion: bool = False) -> None:
        if self._after_id:
            try:
                self._root.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None
        if self._anim_after:
            try:
                self._root.after_cancel(self._anim_after)
            except Exception:
                pass
            self._anim_after = None

        tw = tk.Toplevel(self._root)
        tw.overrideredirect(True)
        tw.attributes("-topmost", True)
        f = ttk.Frame(tw, padding=(12, 8))
        f.pack()
        ttk.Label(f, text=message, wraplength=280).pack()
        tw.update_idletasks()
        x = self._root.winfo_rootx() + self._root.winfo_width() - tw.winfo_width() - 24
        final_y = self._root.winfo_rooty() + self._root.winfo_height() - tw.winfo_height() - 48
        x = max(x, 0)
        final_y = max(final_y, 0)

        def _close() -> None:
            try:
                tw.destroy()
            except Exception:
                pass
            self._after_id = None

        def _schedule_dismiss() -> None:
            self._after_id = self._root.after(ms, _close)

        if reduced_motion:
            tw.geometry(f"+{x}+{final_y}")
            _schedule_dismiss()
            return

        start_y = final_y + 56
        tw.geometry(f"+{x}+{start_y}")

        def _move(progress: float) -> None:
            y = int(start_y + (final_y - start_y) * progress)
            try:
                tw.geometry(f"+{x}+{y}")
            except Exception:
                pass

        def _after_anim() -> None:
            _schedule_dismiss()

        animate_scalar(self._root, duration_ms=220, tick_ms=16, on_frame=_move, on_done=_after_anim)
