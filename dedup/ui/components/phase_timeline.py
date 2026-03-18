"""
PhaseTimeline — horizontal step bar showing the durable pipeline phases.

States per phase:
  pending   — not yet started (muted dot)
  active    — currently running (accent, animated pulse)
  completed — done (success checkmark)
  resumed   — loaded from checkpoint (info, resume badge)
  failed    — error (danger)
  rebuilt   — phase was rebuilt (warning)
  skipped   — phase was skipped (muted)
"""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from typing import List, Dict, Optional, Callable

from ..theme.theme_manager import get_theme_manager
from ..theme.design_system import font_tuple
from ..utils.icons import IC

PHASE_LABELS = [
    ("discovery",   "Discovery"),
    ("size",        "Size"),
    ("partial",     "Partial Hash"),
    ("full",        "Full Hash"),
    ("results",     "Results"),
]

_KEY_ALIASES = {
    "size_reduction":  "size",
    "partial_hash":    "partial",
    "full_hash":       "full",
    "result_assembly": "results",
    "hashing_partial": "partial",
    "hashing_full":    "full",
    "complete":        "results",
}

STATE_ICONS = {
    "pending":   IC.PENDING,
    "active":    IC.ACTIVE,
    "completed": IC.DONE,
    "resumed":   IC.RESUME,
    "failed":    IC.ERROR,
    "rebuilt":   IC.REBUILD,
    "skipped":   IC.SKIPPED,
}

STATE_STYLE = {
    "pending":   "Panel.Muted.TLabel",
    "active":    "Panel.Accent.TLabel",
    "completed": "Panel.Success.TLabel",
    "resumed":   "Panel.TLabel",
    "failed":    "Panel.Danger.TLabel",
    "rebuilt":   "Panel.Warning.TLabel",
    "skipped":   "Panel.Muted.TLabel",
}


class PhaseTimeline(ttk.Frame):
    """Horizontal phase timeline bar."""

    def __init__(self, parent, phases: Optional[List[tuple]] = None, **kwargs):
        super().__init__(parent, style="Panel.TFrame", **kwargs)
        self._phases = phases or PHASE_LABELS
        self._states: Dict[str, str] = {k: "pending" for k, _ in self._phases}
        self._cells: Dict[str, Dict[str, tk.Widget]] = {}
        self._build()
        tm = get_theme_manager()
        tm.subscribe(self._on_theme_change)

    def _build(self):
        for col, (key, label) in enumerate(self._phases):
            self.columnconfigure(col * 2, weight=1)
            cell = ttk.Frame(self, style="Panel.TFrame", padding=(6, 4))
            cell.grid(row=0, column=col * 2, sticky="ew")

            icon_var = tk.StringVar(value=STATE_ICONS.get("pending", "○"))
            lbl_var  = tk.StringVar(value=label)

            icon_lbl = ttk.Label(cell, textvariable=icon_var,
                                 style="Panel.Muted.TLabel",
                                 font=font_tuple("body_bold"))
            icon_lbl.pack(side="left", padx=(0, 4))

            name_lbl = ttk.Label(cell, textvariable=lbl_var,
                                 style="Panel.Muted.TLabel",
                                 font=font_tuple("caption"))
            name_lbl.pack(side="left")

            self._cells[key] = {
                "frame": cell,
                "icon_var": icon_var,
                "lbl_var": lbl_var,
                "icon_lbl": icon_lbl,
                "name_lbl": name_lbl,
            }

            # Arrow between phases
            if col < len(self._phases) - 1:
                ttk.Label(self, text="→", style="Panel.Muted.TLabel",
                          font=font_tuple("caption")).grid(row=0, column=col * 2 + 1, padx=2)

    def set_phase_state(self, phase_key: str, state: str, label_override: str = ""):
        phase_key = _KEY_ALIASES.get(phase_key, phase_key)
        if phase_key not in self._cells:
            return
        self._states[phase_key] = state
        c = self._cells[phase_key]
        icon = STATE_ICONS.get(state, "○")
        style = STATE_STYLE.get(state, "Panel.Muted.TLabel")
        c["icon_var"].set(icon)
        c["icon_lbl"].configure(style=style)
        c["name_lbl"].configure(style=style)
        if label_override:
            c["lbl_var"].set(label_override)

    def reset(self):
        for key, _ in self._phases:
            self.set_phase_state(key, "pending")

    def _on_theme_change(self, tokens):
        pass
