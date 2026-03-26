"""
Reusable folder drop zone (browse + optional DnD).
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk
from typing import Callable, Optional

try:
    from tkinterdnd2 import DND_FILES  # type: ignore
except Exception:
    DND_FILES = None


class DropZone(ttk.Frame):
    """Dashed drop area with browse button; calls on_path with first dropped or chosen folder."""

    def __init__(
        self,
        parent,
        *,
        on_path: Callable[[Path], None],
        browse_title: str = "Select folder",
        **kwargs,
    ) -> None:
        super().__init__(parent, **kwargs)
        self._on_path = on_path
        self._build(browse_title)

    def _build(self, browse_title: str) -> None:
        self.columnconfigure(0, weight=1)
        row = ttk.Frame(self)
        row.grid(row=0, column=0, sticky="ew")
        ttk.Button(row, text="Browse…", command=lambda: self._browse(browse_title)).pack(side="left")

    def _browse(self, title: str) -> None:
        p = filedialog.askdirectory(title=title, parent=self.winfo_toplevel())
        if p:
            self._on_path(Path(p))

    def enable_dnd(self, root: tk.Misc) -> None:
        """Call with TkinterDnD root if available."""
        if DND_FILES is None:
            return

        def drop(e):  # type: ignore[no-untyped-def]
            raw = e.data.strip("{}")
            parts = self._split_paths(raw)
            if parts:
                self._on_path(Path(parts[0]))

        try:
            self.drop_target_register(DND_FILES)  # type: ignore[attr-defined]
            self.dnd_bind("<<Drop>>", drop)  # type: ignore[attr-defined]
        except Exception:
            pass

    @staticmethod
    def _split_paths(raw: str) -> list[str]:
        out: list[str] = []
        cur = ""
        i = 0
        while i < len(raw):
            if raw[i] == "{":
                j = raw.find("}", i + 1)
                if j != -1:
                    out.append(raw[i + 1 : j])
                    i = j + 1
                    continue
            if raw[i] == " " and cur:
                out.append(cur)
                cur = ""
                i += 1
                continue
            cur += raw[i]
            i += 1
        if cur:
            out.append(cur)
        return [p for p in out if p]
