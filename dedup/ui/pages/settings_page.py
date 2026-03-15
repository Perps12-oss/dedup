"""Settings page — theme picker and UI preferences."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from typing import Callable

from ..components import SectionCard
from ..theme.theme_preview import ThemeSwatchGrid
from ..theme.theme_registry import get_display_names, key_from_display_name, THEMES
from ..utils.ui_state import UIState
from ..utils.icons import IC


class SettingsPage(ttk.Frame):
    """Settings and theme page."""

    def __init__(self, parent, state: UIState,
                 on_theme_change: Callable[[str], None],
                 on_preference_changed: Callable[[], None] | None = None,
                 **kwargs):
        super().__init__(parent, **kwargs)
        self._state = state
        self._on_theme_change = on_theme_change
        self._on_preference_changed = on_preference_changed
        self._build()

    def _build(self):
        self.columnconfigure(0, weight=1)

        # ── Page header ──────────────────────────────────────────────
        hdr = ttk.Frame(self, padding=(16, 12, 16, 0))
        hdr.grid(row=0, column=0, sticky="ew")
        ttk.Label(hdr, text=f"{IC.SETTINGS}  Settings",
                  font=("Segoe UI", 14, "bold")).pack(side="left")

        # ── Themes ───────────────────────────────────────────────────
        theme_card = SectionCard(self, title=f"{IC.THEMES}  Themes")
        theme_card.grid(row=1, column=0, sticky="ew", padx=16, pady=8)
        self._build_themes(theme_card.body)

        # ── UI Preferences ───────────────────────────────────────────
        pref_card = SectionCard(self, title=f"{IC.INFO}  UI Preferences")
        pref_card.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 8))
        self._build_prefs(pref_card.body)

    def _build_themes(self, body: ttk.Frame):
        body.columnconfigure(0, weight=1)

        # Theme dropdown for quick select
        sel_frame = ttk.Frame(body, style="Panel.TFrame")
        sel_frame.grid(row=0, column=0, sticky="w", pady=(0, 12))
        ttk.Label(sel_frame, text="Active theme:", style="Panel.Muted.TLabel",
                  font=("Segoe UI", 8)).pack(side="left")
        self._theme_var = tk.StringVar()
        display_names = get_display_names()
        cb = ttk.Combobox(sel_frame, textvariable=self._theme_var,
                          values=display_names, state="readonly", width=20)
        cb.pack(side="left", padx=(6, 0))
        cb.bind("<<ComboboxSelected>>", self._on_select)

        # Set current
        cur = self._state.settings.theme_key
        for name, k in {t["name"]: k for k, t in THEMES.items()}.items():
            if k == cur:
                self._theme_var.set(name)
                break

        # Swatch grid
        try:
            self._swatches = ThemeSwatchGrid(
                body,
                on_select=self._on_swatch_select,
                current_key=self._state.settings.theme_key)
            self._swatches.grid(row=1, column=0, sticky="w")
        except Exception:
            pass

    def _build_prefs(self, body: ttk.Frame):
        body.columnconfigure(0, weight=1)
        s = self._state.settings
        prefs = [
            ("Compact mode",          "density",         s.density == "compact"),
            ("Advanced mode",         "advanced_mode",   s.advanced_mode),
            ("Reduced motion",        "reduced_motion",  s.reduced_motion),
            ("Reduced gradients",     "reduced_gradients",s.reduced_gradients),
            ("High contrast",         "high_contrast",   s.high_contrast),
            ("Show insight drawer",   "show_insight_drawer", s.show_insight_drawer),
            ("Show thumbnails",       "review_show_thumbnails", s.review_show_thumbnails),
            ("Advanced scan events",  "scan_show_events",s.scan_show_events),
        ]
        self._pref_vars: dict[str, tk.BooleanVar] = {}
        for i, (label, attr, default) in enumerate(prefs):
            var = tk.BooleanVar(value=default)
            ttk.Checkbutton(body, text=label, variable=var,
                            command=lambda a=attr, v=var: self._on_pref(a, v.get())
                            ).grid(row=i // 2, column=i % 2, sticky="w", padx=(0, 20), pady=2)
            self._pref_vars[attr] = var

    def _on_select(self, event=None):
        display = self._theme_var.get()
        key = key_from_display_name(display)
        self._state.settings.theme_key = key
        self._on_theme_change(key)

    def _on_swatch_select(self, key: str):
        self._state.settings.theme_key = key
        self._on_theme_change(key)
        # Update dropdown
        for name, k in {t["name"]: k for k, t in THEMES.items()}.items():
            if k == key:
                self._theme_var.set(name)
                break

    def _on_pref(self, attr: str, value: bool):
        s = self._state.settings
        if attr == "density":
            s.density = "compact" if value else "cozy"
        elif hasattr(s, attr):
            setattr(s, attr, value)
        self._state.save()
        if self._on_preference_changed:
            self._on_preference_changed()

    def on_show(self):
        """Sync checkbox state from persisted settings when page is shown."""
        s = self._state.settings
        if not getattr(self, "_pref_vars", None):
            return
        self._pref_vars.get("density") and self._pref_vars["density"].set(s.density == "compact")
        self._pref_vars.get("advanced_mode") and self._pref_vars["advanced_mode"].set(s.advanced_mode)
        self._pref_vars.get("reduced_motion") and self._pref_vars["reduced_motion"].set(s.reduced_motion)
        self._pref_vars.get("reduced_gradients") and self._pref_vars["reduced_gradients"].set(s.reduced_gradients)
        self._pref_vars.get("high_contrast") and self._pref_vars["high_contrast"].set(s.high_contrast)
        self._pref_vars.get("show_insight_drawer") and self._pref_vars["show_insight_drawer"].set(s.show_insight_drawer)
        self._pref_vars.get("review_show_thumbnails") and self._pref_vars["review_show_thumbnails"].set(s.review_show_thumbnails)
        self._pref_vars.get("scan_show_events") and self._pref_vars["scan_show_events"].set(s.scan_show_events)
