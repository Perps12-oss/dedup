"""
CustomTkinter History page (experimental).

Lists persisted scans from the coordinator; opening one loads it into Review.
"""

from __future__ import annotations

from typing import Any, Callable

import customtkinter as ctk

from ..utils.formatting import fmt_bytes, fmt_int


class HistoryPageCTK(ctk.CTkFrame):
    def __init__(
        self,
        parent,
        *,
        get_history: Callable[[], list[dict[str, Any]]],
        on_load_scan: Callable[[str], None],
        **kwargs,
    ) -> None:
        super().__init__(parent, **kwargs)
        self._get_history = get_history
        self._on_load_scan = on_load_scan
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._build()

    def _build(self) -> None:
        top = ctk.CTkFrame(self, corner_radius=12)
        top.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 12))
        top.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(top, text="Scan History", font=ctk.CTkFont(size=26, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=16, pady=(14, 4)
        )
        ctk.CTkLabel(
            top,
            text="Saved scans from this device. Open one to review duplicates (execution uses the loaded result).",
            text_color=("gray40", "gray70"),
        ).grid(row=1, column=0, sticky="w", padx=16, pady=(0, 8))
        ctk.CTkButton(top, text="Refresh list", width=140, fg_color="gray35", command=self.reload).grid(
            row=2, column=0, sticky="w", padx=16, pady=(0, 12)
        )

        self._scroll = ctk.CTkScrollableFrame(self, corner_radius=12)
        self._scroll.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 12))
        self._scroll.grid_columnconfigure(0, weight=1)

        hint = ctk.CTkFrame(self, corner_radius=12)
        hint.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 20))
        ctk.CTkLabel(
            hint,
            text="Tip: After opening a scan, use Review → Execute only when the summary matches what you expect.",
            text_color=("gray45", "gray65"),
            wraplength=720,
            justify="left",
        ).pack(anchor="w", padx=16, pady=14)

    def reload(self) -> None:
        for w in self._scroll.winfo_children():
            w.destroy()
        rows = self._get_history()
        if not rows:
            ctk.CTkLabel(self._scroll, text="No scan history yet.", text_color=("gray40", "gray70")).grid(
                row=0, column=0, sticky="w", padx=12, pady=12
            )
            return
        for i, row in enumerate(rows):
            self._row(self._scroll, i, row)

    def _row(self, parent: ctk.CTkScrollableFrame, index: int, data: dict[str, Any]) -> None:
        sid = str(data.get("scan_id") or "")
        short = (sid[:12] + "…") if len(sid) > 12 else sid or "—"
        started = str(data.get("started_at") or "—")[:19]
        status = str(data.get("status") or "—")
        files_n = int(data.get("files_scanned") or 0)
        dups = int(data.get("duplicates_found") or 0)
        reclaim = int(data.get("reclaimable_bytes") or 0)
        roots = data.get("roots") or []
        root_hint = ""
        if roots:
            try:
                from pathlib import Path

                root_hint = Path(str(roots[0])).name[:40]
            except Exception:
                root_hint = str(roots[0])[:40]

        fr = ctk.CTkFrame(parent, corner_radius=10)
        fr.grid(row=index, column=0, sticky="ew", padx=8, pady=6)
        fr.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(fr, fg_color="transparent")
        header.grid(row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=(10, 4))
        ctk.CTkLabel(header, text=short, font=ctk.CTkFont(weight="bold")).pack(side="left")
        ctk.CTkLabel(header, text=f"  ·  {status}", text_color=("gray45", "gray65")).pack(side="left")

        meta = (
            f"{started}  ·  {fmt_int(files_n)} files scanned  ·  {fmt_int(dups)} dup groups  ·  "
            f"{fmt_bytes(reclaim)} reclaimable"
        )
        if root_hint:
            meta += f"\nRoot: {root_hint}"

        body = ctk.CTkFrame(fr, fg_color="transparent")
        body.grid(row=1, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 10))
        body.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(body, text=meta, text_color=("gray40", "gray70"), justify="left", anchor="w").grid(
            row=0, column=0, sticky="nw"
        )
        ctk.CTkButton(
            body,
            text="Open in Review",
            width=130,
            command=lambda s=sid: self._on_load_scan(s),
        ).grid(row=0, column=1, sticky="ne", padx=(12, 0))
