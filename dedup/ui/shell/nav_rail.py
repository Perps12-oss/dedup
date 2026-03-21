"""
NavRail — fixed left navigation rail.

Items: Mission, Scan, Review, History, Diagnostics, Themes, Settings
"""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from typing import Callable, Dict, List, Tuple, Optional

from ..utils.icons import IC
from ..theme.theme_manager import get_theme_manager
from ..theme.design_system import font_tuple, SPACING

# Primary pages: Home (Mission), Scan, Review. Secondary: History, Diagnostics, Settings.
PRIMARY_NAV: List[Tuple[str, str, str]] = [
    ("mission", IC.MISSION, "Mission"),
    ("scan",    IC.SCAN,    "Scan"),
    ("review",  IC.REVIEW,  "Review"),
]
SECONDARY_NAV: List[Tuple[str, str, str]] = [
    ("history",     IC.HISTORY,     "History"),
    ("diagnostics", IC.DIAGNOSTICS, "Diagnostics"),
    ("themes",      IC.THEMES,      "Themes"),
    ("settings",    IC.SETTINGS,    "Settings"),
]
NAV_ITEMS: List[Tuple[str, str, str]] = PRIMARY_NAV + SECONDARY_NAV

RAIL_WIDTH = 56


class NavRail(tk.Frame):
    """
    Left navigation rail.  Uses tk.Frame (not ttk) so we can set a
    background colour that isn't overridden by the platform theme.
    """

    def __init__(self, parent, on_navigate: Callable[[str], None], **kwargs):
        super().__init__(parent, **kwargs)
        self._on_navigate = on_navigate
        self._buttons: Dict[str, tk.Frame] = {}
        self._active: Optional[str] = None
        self._tm = get_theme_manager()
        self._tm.subscribe(self._apply_colors)
        self._build()
        self._apply_colors(self._tm.tokens)

    def _build(self):
        self.configure(width=RAIL_WIDTH)
        self.pack_propagate(False)
        self.grid_propagate(False)

        # App logo/name strip at top
        self._logo = tk.Label(
            self, text="CE\nRE\nBRO",
            font=font_tuple("card_title"),
            pady=SPACING["lg"], cursor="arrow",
        )
        self._logo.pack(fill="x")

        # Separator
        self._sep1 = tk.Frame(self, height=1)
        self._sep1.pack(fill="x", pady=(0, SPACING["sm"]))

        # Primary navigation (Mission, Scan, Review)
        for key, icon, label in PRIMARY_NAV:
            self._add_nav_cell(key, icon, label)

        # Separator between primary and secondary
        self._sep_primary_secondary = tk.Frame(self, height=1)
        self._sep_primary_secondary.pack(fill="x", pady=SPACING["sm"])

        # Secondary navigation (History, Diagnostics, Settings)
        for key, icon, label in SECONDARY_NAV:
            self._add_nav_cell(key, icon, label)

        # Bottom spacer + compact toggle
        self._spacer = tk.Frame(self)
        self._spacer.pack(fill="both", expand=True)

        self._compact_lbl = tk.Label(self, text="⇔", font=font_tuple("body"), cursor="hand2")
        self._compact_lbl.pack(pady=SPACING["md"])

    def _add_nav_cell(self, key: str, icon: str, label: str) -> None:
        cell = tk.Frame(self, cursor="hand2")
        cell.pack(fill="x", pady=1)
        icon_lbl = tk.Label(cell, text=icon, font=font_tuple("nav_icon"))
        icon_lbl.pack(pady=(SPACING["md"], 0))
        name_lbl = tk.Label(cell, text=label, font=font_tuple("strip"))
        name_lbl.pack(pady=(0, SPACING["md"]))
        for w in (cell, icon_lbl, name_lbl):
            w.bind("<Button-1>", lambda e, k=key: self._on_click(k))
            w.bind("<Enter>", lambda e, c=cell: self._on_hover(c, True))
            w.bind("<Leave>", lambda e, c=cell, k=key: self._on_hover(c, False, k))
        self._buttons[key] = cell

    def _on_click(self, key: str):
        self._on_navigate(key)

    def _on_hover(self, cell: tk.Frame, entering: bool, key: str = ""):
        t = self._tm.tokens
        if key and key == self._active:
            return
        bg = t["bg_elevated"] if entering else t["bg_sidebar"]
        cell.configure(background=bg)
        for child in cell.winfo_children():
            child.configure(background=bg)

    def set_active(self, key: str):
        t = self._tm.tokens
        if self._active and self._active in self._buttons:
            old = self._buttons[self._active]
            old.configure(background=t["bg_sidebar"])
            for child in old.winfo_children():
                child.configure(background=t["bg_sidebar"],
                                foreground=t["text_secondary"])
        self._active = key
        if key in self._buttons:
            cell = self._buttons[key]
            cell.configure(background=t["nav_active_bg"])
            for child in cell.winfo_children():
                child.configure(background=t["nav_active_bg"],
                                foreground=t["nav_active_fg"])

    def _apply_colors(self, t: dict):
        self.configure(background=t["bg_sidebar"])
        self._logo.configure(background=t["bg_sidebar"],
                             foreground=t["accent_primary"])
        self._sep1.configure(background=t["border_soft"])
        self._sep_primary_secondary.configure(background=t["border_soft"])
        self._spacer.configure(background=t["bg_sidebar"])
        self._compact_lbl.configure(background=t["bg_sidebar"],
                                    foreground=t["text_muted"])
        for key, cell in self._buttons.items():
            is_active = (key == self._active)
            bg = t["nav_active_bg"] if is_active else t["bg_sidebar"]
            fg = t["nav_active_fg"] if is_active else t["text_secondary"]
            cell.configure(background=bg)
            for child in cell.winfo_children():
                child.configure(background=bg, foreground=fg)
