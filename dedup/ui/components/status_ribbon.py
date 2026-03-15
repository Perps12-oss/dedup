"""
StatusRibbon — single-line state-truth component.

Variants:
  safe_resume     → green / accent
  rebuild_phase   → warning amber
  restart_required → danger red
  verified        → success green
  info            → info blue
  warning         → warning amber
  idle            → muted
"""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from typing import Optional

from ..utils.icons import IC

VARIANT_CFG = {
    "safe_resume":      ("Panel.Success.TLabel", IC.OK,     "Safe Resume"),
    "rebuild_phase":    ("Panel.Warning.TLabel", IC.REBUILD,"Rebuild Phase"),
    "restart_required": ("Panel.Danger.TLabel",  IC.RESTART,"Restart Required"),
    "verified":         ("Panel.Success.TLabel", IC.SHIELD, "Verified"),
    "info":             ("Panel.Accent.TLabel",  IC.INFO,   ""),
    "warning":          ("Panel.Warning.TLabel", IC.WARN,   ""),
    "idle":             ("Panel.Muted.TLabel",   "",        "Idle"),
    "scanning":         ("Panel.Accent.TLabel",  IC.RUNNING,"Scanning"),
    "completed":        ("Panel.Success.TLabel", IC.OK,     "Completed"),
    "failed":           ("Panel.Danger.TLabel",  IC.ERROR,  "Failed"),
}


class StatusRibbon(ttk.Frame):
    """Compact status ribbon used at top of Scan and Review pages."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, style="Panel.TFrame", padding=(12, 6), **kwargs)
        self.columnconfigure(1, weight=1)

        self._icon_var  = tk.StringVar(value="")
        self._state_var = tk.StringVar(value="")
        self._detail_var = tk.StringVar(value="")

        self._icon_lbl = ttk.Label(self, textvariable=self._icon_var,
                                   style="Panel.Muted.TLabel",
                                   font=("Segoe UI", 10))
        self._icon_lbl.grid(row=0, column=0, padx=(0, 6), sticky="w")

        self._state_lbl = ttk.Label(self, textvariable=self._state_var,
                                    style="Panel.Muted.TLabel",
                                    font=("Segoe UI", 9, "bold"))
        self._state_lbl.grid(row=0, column=1, sticky="w")

        self._detail_lbl = ttk.Label(self, textvariable=self._detail_var,
                                     style="Panel.Secondary.TLabel",
                                     font=("Segoe UI", 8))
        self._detail_lbl.grid(row=0, column=2, sticky="e", padx=(8, 0))

    def set_state(self, variant: str, detail: str = "", label_override: str = ""):
        style, icon, default_label = VARIANT_CFG.get(variant, VARIANT_CFG["idle"])
        label = label_override or default_label
        self._icon_var.set(icon)
        self._state_var.set(label)
        self._detail_var.set(detail)
        self._icon_lbl.configure(style=style)
        self._state_lbl.configure(style=style)

    def set_info(self, label: str, detail: str = ""):
        self.set_state("info", detail=detail, label_override=label)
