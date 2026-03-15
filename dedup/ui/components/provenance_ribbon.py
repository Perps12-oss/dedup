"""ProvenanceRibbon — scan provenance metadata bar used at top of Review page."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from typing import Optional

from ..utils.formatting import fmt_bytes, fmt_int


class ProvenanceRibbon(ttk.Frame):
    """Shows scan provenance: session id, verification level, groups, reclaimable."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, style="Panel.TFrame", padding=(12, 6), **kwargs)

        self._items: list = []

        self._session_var    = tk.StringVar(value="No scan loaded")
        self._verif_var      = tk.StringVar(value="—")
        self._groups_var     = tk.StringVar(value="0")
        self._reclaim_var    = tk.StringVar(value="—")

        col = 0
        for label, var in [
            ("Scan", self._session_var),
            ("Verification", self._verif_var),
            ("Groups", self._groups_var),
            ("Reclaimable", self._reclaim_var),
        ]:
            if col > 0:
                ttk.Separator(self, orient="vertical").grid(
                    row=0, column=col * 2 - 1, sticky="ns", padx=10)
            lf = ttk.Frame(self, style="Panel.TFrame")
            lf.grid(row=0, column=col * 2, sticky="w")
            ttk.Label(lf, text=f"{label}: ", style="Panel.Muted.TLabel",
                      font=("Segoe UI", 8)).pack(side="left")
            ttk.Label(lf, textvariable=var, style="Panel.TLabel",
                      font=("Segoe UI", 9, "bold")).pack(side="left")
            col += 1

        self.columnconfigure(col * 2 - 1, weight=1)

    def update(self, session_id: str = "", verification: str = "",
               groups: int = 0, reclaimable_bytes: int = 0):
        if session_id:
            self._session_var.set(session_id[:16] + "…" if len(session_id) > 16 else session_id)
        self._verif_var.set(verification or "Full Hash")
        self._groups_var.set(fmt_int(groups))
        self._reclaim_var.set(fmt_bytes(reclaimable_bytes))
