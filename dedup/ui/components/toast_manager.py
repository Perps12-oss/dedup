"""
Lightweight non-modal toast using a borderless Toplevel.

Phase 3 stub: call sites can be added incrementally (scan complete, theme applied, etc.).
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Optional


class ToastManager:
    def __init__(self, root: tk.Tk) -> None:
        self._root = root
        self._after_id: Optional[str] = None

    def show(self, message: str, ms: int = 3200) -> None:
        if self._after_id:
            try:
                self._root.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

        tw = tk.Toplevel(self._root)
        tw.overrideredirect(True)
        tw.attributes("-topmost", True)
        f = ttk.Frame(tw, padding=(12, 8))
        f.pack()
        ttk.Label(f, text=message, wraplength=280).pack()
        tw.update_idletasks()
        x = self._root.winfo_rootx() + self._root.winfo_width() - tw.winfo_width() - 24
        y = self._root.winfo_rooty() + self._root.winfo_height() - tw.winfo_height() - 48
        tw.geometry(f"+{max(x, 0)}+{max(y, 0)}")

        def _close() -> None:
            try:
                tw.destroy()
            except Exception:
                pass
            self._after_id = None

        self._after_id = self._root.after(ms, _close)
