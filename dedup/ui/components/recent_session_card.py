"""Compact card for one recent scan session row."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

import ttkbootstrap as tb
from tkinter import ttk

from ..theme.design_system import font_tuple
from ..utils.formatting import fmt_bytes, fmt_int


class RecentSessionCard(ttk.Frame):
    def __init__(
        self,
        parent,
        session: Dict[str, Any],
        *,
        on_resume: Optional[Callable[[str], None]] = None,
        on_review: Optional[Callable[[], None]] = None,
        resumable: bool = False,
        **kwargs,
    ) -> None:
        super().__init__(parent, **kwargs)
        self._session = session
        self._on_resume = on_resume
        self._on_review = on_review
        self._build(resumable)

    def _build(self, resumable: bool) -> None:
        s = self._session
        sid = str(s.get("scan_id", ""))
        outer = ttk.Frame(self, style="Panel.TFrame", padding=8)
        outer.pack(fill="x")
        ttk.Label(outer, text=str(s.get("started_at", "")), font=font_tuple("caption")).pack(anchor="w")
        roots = s.get("roots") or []
        ttk.Label(outer, text=", ".join(str(r) for r in roots[:2]), wraplength=400).pack(anchor="w")
        row = ttk.Frame(outer)
        row.pack(fill="x", pady=(4, 0))
        ttk.Label(row, text=f"{fmt_int(int(s.get('files_scanned') or 0))} files").pack(side="left")
        ttk.Label(row, text=f" · {fmt_bytes(int(s.get('reclaimable_bytes') or 0))} reclaim").pack(side="left")
        btns = ttk.Frame(outer)
        btns.pack(anchor="w", pady=(4, 0))
        if resumable and self._on_resume:
            tb.Button(btns, text="Resume", bootstyle="primary", command=lambda: self._on_resume(sid)).pack(
                side="left", padx=(0, 4)
            )
        if self._on_review:
            tb.Button(btns, text="Review", bootstyle="secondary", command=self._on_review).pack(side="left")
