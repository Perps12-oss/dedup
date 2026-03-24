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

from ..theme.design_system import SPACING, font_tuple
from ..utils.icons import IC
from .rainbow_progress import RainbowProgressBar

VARIANT_CFG = {
    "safe_resume": ("Panel.Success.TLabel", IC.OK, "Safe Resume"),
    "rebuild_phase": ("Panel.Warning.TLabel", IC.REBUILD, "Rebuild Phase"),
    "restart_required": ("Panel.Danger.TLabel", IC.RESTART, "Restart Required"),
    "verified": ("Panel.Success.TLabel", IC.SHIELD, "Verified"),
    "info": ("Panel.Accent.TLabel", IC.INFO, ""),
    "warning": ("Panel.Warning.TLabel", IC.WARN, ""),
    "idle": ("Panel.Muted.TLabel", "", "Idle"),
    "scanning": ("Panel.Accent.TLabel", IC.RUNNING, "Scanning"),
    "completed": ("Panel.Success.TLabel", IC.OK, "Completed"),
    "failed": ("Panel.Danger.TLabel", IC.ERROR, "Failed"),
}


class StatusRibbon(ttk.Frame):
    """
    Compact status ribbon (Scan page).

    Uses horizontal pack so the phase detail is not stranded on the far right of an
    empty weighted column (which looked like a “missing” progress bar).
    Optional RainbowProgressBar fills the space between status and detail when scanning.
    """

    def __init__(self, parent, *, show_progress: bool = True, progress_height: int = 40, **kwargs):
        super().__init__(parent, style="Panel.TFrame", padding=(SPACING["lg"], SPACING["md"]), **kwargs)
        self.columnconfigure(0, weight=1)

        self._icon_var = tk.StringVar(value="")
        self._state_var = tk.StringVar(value="")
        self._detail_var = tk.StringVar(value="")

        row = ttk.Frame(self, style="Panel.TFrame")
        row.grid(row=0, column=0, sticky="ew")
        row.columnconfigure(0, weight=1)

        self._icon_lbl = ttk.Label(
            row, textvariable=self._icon_var, style="Panel.Muted.TLabel", font=font_tuple("card_title")
        )
        self._state_lbl = ttk.Label(
            row, textvariable=self._state_var, style="Panel.Muted.TLabel", font=font_tuple("body_bold")
        )
        self._detail_lbl = ttk.Label(
            row, textvariable=self._detail_var, style="Panel.Secondary.TLabel", font=font_tuple("data_label")
        )

        # Pack left→right: icon, state, expanding bar, detail on the right (no dead column).
        self._mini_progress: RainbowProgressBar | None = None
        self._icon_lbl.pack(side="left", padx=(0, SPACING["md"]))
        self._state_lbl.pack(side="left", padx=(0, SPACING["sm"]))
        if show_progress:
            self._mini_progress = RainbowProgressBar(row, height=progress_height)
            self._mini_progress.pack(side="left", fill="x", expand=True, padx=(SPACING["md"], SPACING["md"]))
        self._detail_lbl.pack(side="right", padx=(SPACING["md"], 0))

    def set_state(self, variant: str, detail: str = "", label_override: str = ""):
        style, icon, default_label = VARIANT_CFG.get(variant, VARIANT_CFG["idle"])
        label = label_override or default_label
        self._icon_var.set(icon)
        self._state_var.set(label)
        self._detail_var.set(detail)
        self._icon_lbl.configure(style=style)
        self._state_lbl.configure(style=style)

        if self._mini_progress is not None:
            # Scanning progress is driven by ScanPage._update_scan_progress_eta via mirror_progress.
            # Do not reset here — session updates call set_state("scanning") often and would wipe %.
            if variant not in ("scanning", "info"):
                self._mini_progress.set_fraction(0.0, indeterminate=False)

    def set_detail(self, detail: str) -> None:
        """Update ribbon detail line without changing variant or resetting progress."""
        self._detail_var.set(detail)

    def mirror_progress(self, fraction: float, *, indeterminate: bool) -> None:
        """Keep ribbon bar in sync with the main Scan Progress rainbow (same fraction)."""
        if self._mini_progress is None:
            return
        self._mini_progress.set_fraction(fraction, indeterminate=indeterminate)

    def set_info(self, label: str, detail: str = ""):
        self.set_state("info", detail=detail, label_override=label)
