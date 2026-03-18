"""
TopBar — persistent top command bar.

Left:   App title + active session chip + mode chip
Center: Contextual page actions (set by each page)
Right:  Theme switcher, density toggle, advanced mode, help
"""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional, List, Tuple

from ..utils.icons import IC
from ..theme.theme_manager import get_theme_manager
from ..theme.theme_registry import get_display_names, key_from_display_name, THEMES
from ..theme.design_system import font_tuple, SPACING

ActionSpec = Tuple[str, str, Callable]  # (label, style, command)


class TopBar(tk.Frame):
    """Persistent application top bar."""

    BAR_HEIGHT = 44

    def __init__(self, parent,
                 on_theme_change: Callable[[str], None],
                 on_density_toggle: Callable[[], None],
                 on_advanced_toggle: Callable[[], None],
                 on_settings: Callable[[], None],
                 **kwargs):
        super().__init__(parent, height=self.BAR_HEIGHT, **kwargs)
        self.pack_propagate(False)
        self._tm = get_theme_manager()
        self._on_theme_change = on_theme_change
        self._on_density_toggle = on_density_toggle
        self._on_advanced_toggle = on_advanced_toggle
        self._on_settings = on_settings
        self._action_widgets: List[tk.Widget] = []
        self._build()
        self._tm.subscribe(self._apply_colors)
        self._apply_colors(self._tm.tokens)

    def _build(self):
        self.grid_columnconfigure(1, weight=1)

        # ---- LEFT section ----
        left = tk.Frame(self)
        left.grid(row=0, column=0, sticky="w", padx=(8, 0))
        self._left_frame = left

        self._title_lbl = tk.Label(
            left, text="CEREBRO",
            font=font_tuple("section_title"), pady=0)
        self._title_lbl.pack(side="left", padx=(SPACING["sm"], SPACING["md"]))

        self._subtitle_lbl = tk.Label(
            left, text="Dedup Engine",
            font=font_tuple("caption"))
        self._subtitle_lbl.pack(side="left")

        # Session chip
        self._session_chip = tk.Label(
            left, text="No session",
            font=font_tuple("strip"),
            padx=SPACING["md"], pady=SPACING["xs"], cursor="arrow")
        self._session_chip.pack(side="left", padx=(SPACING["lg"], 0))

        # Mode chip
        self._mode_chip = tk.Label(
            left, text="Idle",
            font=font_tuple("strip"),
            padx=SPACING["md"], pady=SPACING["xs"])
        self._mode_chip.pack(side="left", padx=(SPACING["sm"], 0))

        # ---- CENTER section (contextual actions) ----
        self._center_frame = tk.Frame(self)
        self._center_frame.grid(row=0, column=1, sticky="ew")

        # ---- RIGHT section ----
        right = tk.Frame(self)
        right.grid(row=0, column=2, sticky="e", padx=(0, 8))
        self._right_frame = right

        # Theme selector
        self._theme_var = tk.StringVar()
        display_names = get_display_names()
        self._theme_combo = ttk.Combobox(
            right, textvariable=self._theme_var,
            values=display_names, state="readonly", width=14)
        self._theme_combo.pack(side="left", padx=(0, 6))
        self._theme_combo.bind("<<ComboboxSelected>>", self._on_theme_select)

        # Density toggle
        self._density_btn = tk.Label(
            right, text="⊞ Cozy", font=font_tuple("strip"),
            padx=SPACING["md"], pady=SPACING["xs"], cursor="hand2")
        self._density_btn.pack(side="left", padx=(0, SPACING["sm"]))
        self._density_btn.bind("<Button-1>", lambda e: self._on_density_toggle())

        # Advanced toggle
        self._adv_var = tk.BooleanVar(value=False)
        self._adv_btn = tk.Label(
            right, text="Advanced", font=font_tuple("strip"),
            padx=SPACING["md"], pady=SPACING["xs"], cursor="hand2")
        self._adv_btn.pack(side="left", padx=(0, SPACING["sm"]))
        self._adv_btn.bind("<Button-1>", lambda e: self._on_advanced_toggle())

        # Settings
        settings_btn = tk.Label(
            right, text=IC.SETTINGS, font=font_tuple("body"),
            padx=SPACING["md"], cursor="hand2")
        settings_btn.pack(side="left")
        settings_btn.bind("<Button-1>", lambda e: self._on_settings())
        self._settings_lbl = settings_btn

    def set_page_actions(self, actions: List[ActionSpec]):
        """Replace the center contextual action buttons."""
        for w in self._action_widgets:
            w.destroy()
        self._action_widgets.clear()
        t = self._tm.tokens
        for label, style, cmd in actions:
            btn = ttk.Button(self._center_frame, text=label, style=style, command=cmd)
            btn.pack(side="left", padx=SPACING["sm"])
            self._action_widgets.append(btn)

    def set_session(self, session_id: str, mode: str = "Idle"):
        t = self._tm.tokens
        short = session_id[:12] + "…" if len(session_id) > 12 else session_id
        self._session_chip.configure(text=short or "No session")
        self._mode_chip.configure(text=mode)
        chip_bg = t["nav_active_bg"] if mode not in ("Idle", "") else t["bg_elevated"]
        chip_fg = t["nav_active_fg"] if mode not in ("Idle", "") else t["text_muted"]
        self._mode_chip.configure(background=chip_bg, foreground=chip_fg)

    def set_current_theme(self, theme_key: str):
        for name, key_token in {t["name"]: k for k, t in THEMES.items()}.items():
            if key_token == theme_key:
                self._theme_var.set(name)
                return

    def set_density_label(self, density: str):
        self._density_btn.configure(text=f"⊞ {density.title()}")

    def set_advanced(self, active: bool):
        t = self._tm.tokens
        bg = t["nav_active_bg"] if active else t["bg_elevated"]
        fg = t["nav_active_fg"] if active else t["text_secondary"]
        self._adv_btn.configure(background=bg, foreground=fg)

    def subscribe_to_hub(self, hub) -> None:
        """
        Subscribe to ProjectionHub session projections.
        Drives the session + mode chips from the canonical SessionProjection.
        """
        def _on_session(proj) -> None:
            mode_map = {
                "running":   "Scanning",
                "completed": "Review",
                "cancelled": "Idle",
                "failed":    "Error",
                "idle":      "Idle",
            }
            mode = mode_map.get(proj.status, "Idle")
            self.set_session(proj.session_id, mode)
        hub.subscribe("session", _on_session)

    def _on_theme_select(self, event=None):
        display = self._theme_var.get()
        key = key_from_display_name(display)
        self._on_theme_change(key)

    def _apply_colors(self, t: dict):
        bg = t["bg_sidebar"]
        fg = t["text_primary"]
        fg2 = t["text_secondary"]
        for frame in (self, self._left_frame, self._center_frame, self._right_frame):
            frame.configure(background=bg)
        self._title_lbl.configure(background=bg, foreground=t["accent_primary"])
        self._subtitle_lbl.configure(background=bg, foreground=fg2)
        self._session_chip.configure(background=t["bg_elevated"],
                                     foreground=fg2)
        self._mode_chip.configure(background=t["bg_elevated"], foreground=fg2)
        self._density_btn.configure(background=t["bg_elevated"], foreground=fg2)
        self._adv_btn.configure(background=t["bg_elevated"], foreground=fg2)
        self._settings_lbl.configure(background=bg, foreground=fg2)
