"""
Settings page — theme picker and UI preferences.

Blueprint: Three-card layout (Appearance, Behavior, Advanced).
Theme cards with selection state. Density as radios. Logical grouping with tooltips.
"""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Callable, Optional

from ..components import SectionCard
from ..theme.theme_registry import THEMES, key_from_display_name, DEFAULT_THEME
from ..theme.theme_manager import get_theme_manager
from ..theme.design_system import font_tuple, SPACING
from ..utils.ui_state import UIState
from ..utils.icons import IC


def _tooltip(widget: tk.Widget, text: str) -> None:
    """Bind hover to show a small tooltip Toplevel."""
    tip: Optional[tk.Toplevel] = [None]
    def show(e):
        t = tk.Toplevel(widget)
        t.wm_overrideredirect(True)
        t.wm_geometry(f"+{e.x_root + 12}+{e.y_root + 12}")
        lbl = tk.Label(t, text=text, justify="left", bg="#2d2d2d", fg="#e0e0e0",
                       padx=8, pady=6, font=font_tuple("caption"))
        lbl.pack()
        tip[0] = t
    def hide(*_):
        if tip[0] and tip[0].winfo_exists():
            tip[0].destroy()
        tip[0] = None
    widget.bind("<Enter>", show)
    widget.bind("<Leave>", hide)


class SettingsPage(ttk.Frame):
    """Settings page: Appearance, Behavior, Advanced. Renders from UIState.settings."""

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
        self.rowconfigure(3, weight=1)
        pad = SPACING["page"]

        # Page header
        hdr = ttk.Frame(self, padding=(pad, pad, pad, SPACING["lg"]))
        hdr.grid(row=0, column=0, sticky="ew")
        ttk.Label(hdr, text=f"{IC.SETTINGS}  Settings",
                  font=font_tuple("page_title")).pack(side="left")
        ttk.Label(hdr, text="Theme · Density · Preferences",
                  style="Muted.TLabel",
                  font=font_tuple("page_subtitle")).pack(side="left", padx=(SPACING["lg"], 0), pady=6)

        # ── APPEARANCE ─────────────────────────────────────────────────
        appearance = SectionCard(self, title=f"{IC.THEMES}  Appearance")
        appearance.grid(row=1, column=0, sticky="ew", padx=pad, pady=(0, SPACING["md"]))
        self._build_appearance(appearance.body)

        # ── BEHAVIOR ──────────────────────────────────────────────────
        behavior = SectionCard(self, title=f"{IC.INFO}  Behavior")
        behavior.grid(row=2, column=0, sticky="ew", padx=pad, pady=(0, SPACING["md"]))
        self._build_behavior(behavior.body)

        # ── ADVANCED ───────────────────────────────────────────────────
        advanced = SectionCard(self, title=f"{IC.SHIELD}  Advanced")
        advanced.grid(row=3, column=0, sticky="nsew", padx=pad, pady=(0, pad))
        self._build_advanced(advanced.body)

    def _build_appearance(self, body: ttk.Frame):
        body.columnconfigure(0, weight=1)

        # Theme cards (premium selection)
        ttk.Label(body, text="Theme", style="Panel.Secondary.TLabel",
                  font=font_tuple("section_title")).grid(row=0, column=0, sticky="w", pady=(0, SPACING["sm"]))
        theme_grid = ttk.Frame(body, style="Panel.TFrame")
        theme_grid.grid(row=1, column=0, sticky="w", pady=(0, SPACING["lg"]))
        self._theme_cards: dict[str, tk.Frame] = {}
        cols = 5
        for i, (key, t) in enumerate(THEMES.items()):
            card = self._make_theme_card(theme_grid, key, t)
            row, col = i // cols, i % cols
            theme_grid.columnconfigure(col, minsize=100)
            card.grid(row=row, column=col, padx=SPACING["xs"], pady=SPACING["xs"], sticky="nw")
            self._theme_cards[key] = card

        # Display Density (radio)
        ttk.Label(body, text="Display Density", style="Panel.Secondary.TLabel",
                  font=font_tuple("body_bold")).grid(row=2, column=0, sticky="w", pady=(0, SPACING["xs"]))
        density_frame = ttk.Frame(body, style="Panel.TFrame")
        density_frame.grid(row=3, column=0, sticky="w", pady=(0, SPACING["lg"]))
        self._density_var = tk.StringVar(value=self._state.settings.density or "comfortable")
        if self._density_var.get() not in ("comfortable", "cozy", "compact"):
            self._density_var.set("comfortable")
        for val, label in [("comfortable", "Comfortable"), ("cozy", "Cozy"), ("compact", "Compact")]:
            rb = ttk.Radiobutton(
                density_frame, text=label, variable=self._density_var, value=val,
                command=self._on_density_change,
            )
            rb.pack(side="left", padx=(0, SPACING["lg"]))

        # Appearance preferences (grouped checkboxes)
        ttk.Label(body, text="Preferences", style="Panel.Secondary.TLabel",
                  font=font_tuple("body_bold")).grid(row=4, column=0, sticky="w", pady=(0, SPACING["xs"]))
        pref_frame = ttk.Frame(body, style="Panel.TFrame")
        pref_frame.grid(row=5, column=0, sticky="w")
        self._pref_vars: dict[str, tk.BooleanVar] = {}
        appearance_prefs = [
            ("review_show_thumbnails", "Show thumbnails in Review"),
            ("reduced_motion", "Reduced motion"),
            ("high_contrast", "High contrast (system follows)"),
            ("reduced_gradients", "Reduced gradients"),
        ]
        for i, (attr, label) in enumerate(appearance_prefs):
            var = tk.BooleanVar(value=getattr(self._state.settings, attr, False))
            cb = ttk.Checkbutton(pref_frame, text=label, variable=var,
                                command=lambda a=attr, v=var: self._on_pref(a, v.get()))
            cb.grid(row=i, column=0, sticky="w", pady=2)
            self._pref_vars[attr] = var

    def _make_theme_card(self, parent: ttk.Frame, key: str, t: dict) -> tk.Frame:
        tm = get_theme_manager()
        tokens = tm.tokens
        is_selected = (self._state.settings.theme_key == key)
        accent = tokens.get("accent_primary", "#5eb8e6")
        bstrong = tokens.get("border_strong", "#2a2d32")
        outer = tk.Frame(parent, bg=accent if is_selected else tokens.get("border_soft", "#1c1e22"),
                         padx=2, pady=2, cursor="hand2")
        inner = tk.Frame(outer, bg=t["bg_panel"], width=96, height=64, padx=4, pady=4)
        inner.pack_propagate(False)
        inner.pack()
        # Gradient strip
        bar = tk.Canvas(inner, height=8, bg=t["bg_panel"], highlightthickness=0)
        bar.pack(fill="x")
        w = 88
        for i in range(w):
            t_val = i / max(w - 1, 1)
            from ..theme.gradients import lerp_color
            col = lerp_color(t["gradient_start"], t["gradient_end"], t_val)
            bar.create_line(i, 0, i, 8, fill=col)
        name = t.get("name", key)
        lbl = tk.Label(inner, text=name, bg=t["bg_panel"], fg=t["text_secondary"],
                      font=font_tuple("caption"), wraplength=88, justify="center")
        lbl.pack(fill="both", expand=True)
        sel_mark = "●" if is_selected else "○"
        sel_lbl = tk.Label(inner, text=sel_mark, bg=t["bg_panel"],
                           fg=accent if is_selected else t["text_muted"],
                           font=font_tuple("body"))
        sel_lbl.pack()
        for w_ in (outer, inner, lbl, sel_lbl, bar):
            w_.bind("<Button-1>", lambda e, k=key: self._on_theme_select(k))
        return outer

    def _build_behavior(self, body: ttk.Frame):
        body.columnconfigure(0, weight=1)

        # Review & Safety
        ttk.Label(body, text="Review & Safety", style="Panel.Secondary.TLabel",
                  font=font_tuple("body_bold")).grid(row=0, column=0, sticky="w", pady=(0, SPACING["xs"]))
        review_frame = ttk.Frame(body, style="Panel.TFrame")
        review_frame.grid(row=1, column=0, sticky="w", pady=(0, SPACING["md"]))
        for i, (attr, label) in enumerate([
            ("review_show_preview", "Confirm before executing deletions"),
            ("review_show_risk_flags", "Show risk warnings"),
        ]):
            var = tk.BooleanVar(value=getattr(self._state.settings, attr, True))
            ttk.Checkbutton(review_frame, text=label, variable=var,
                           command=lambda a=attr, v=var: self._on_pref(a, v.get())).grid(
                row=i, column=0, sticky="w", pady=2)
            self._pref_vars[attr] = var

        # Scan & Performance
        ttk.Label(body, text="Scan & Performance", style="Panel.Secondary.TLabel",
                  font=font_tuple("body_bold")).grid(row=2, column=0, sticky="w", pady=(0, SPACING["xs"]))
        scan_frame = ttk.Frame(body, style="Panel.TFrame")
        scan_frame.grid(row=3, column=0, sticky="w")
        scan_row = ttk.Frame(scan_frame, style="Panel.TFrame")
        scan_row.grid(row=0, column=0, sticky="w", pady=2)
        var = tk.BooleanVar(value=self._state.settings.scan_show_events)
        ttk.Checkbutton(scan_row, text="Advanced scan events (verbose logging)", variable=var,
                       command=lambda: self._on_pref("scan_show_events", var.get())).pack(side="left")
        self._pref_vars["scan_show_events"] = var
        info_btn = ttk.Label(scan_row, text="ⓘ", style="Panel.Muted.TLabel", cursor="help")
        info_btn.pack(side="left", padx=(SPACING["xs"], 0))
        _tooltip(info_btn, "Logs detailed phase info to Diagnostics during scan.")
        scan_row2 = ttk.Frame(scan_frame, style="Panel.TFrame")
        scan_row2.grid(row=1, column=0, sticky="w", pady=2)
        var2 = tk.BooleanVar(value=self._state.settings.show_insight_drawer)
        ttk.Checkbutton(scan_row2, text="Show insight drawer during scan", variable=var2,
                       command=lambda: self._on_pref("show_insight_drawer", var2.get())).pack(side="left")
        self._pref_vars["show_insight_drawer"] = var2
        info2 = ttk.Label(scan_row2, text="ⓘ", style="Panel.Muted.TLabel", cursor="help")
        info2.pack(side="left", padx=(SPACING["xs"], 0))
        _tooltip(info2, "Displays live metrics and health in the right drawer.")

    def _build_advanced(self, body: ttk.Frame):
        body.columnconfigure(0, weight=1)

        # Engine info (read-only)
        info_frame = ttk.Frame(body, style="Panel.TFrame")
        info_frame.grid(row=0, column=0, sticky="ew", pady=(0, SPACING["lg"]))
        info_frame.columnconfigure(1, weight=1)
        rows = [
            ("Engine", "xxhash64 (default)"),
            ("Trash protection", "Active"),
            ("Audit logging", "Enabled"),
            ("Schema version", "2.1.4"),
        ]
        for i, (label, val) in enumerate(rows):
            ttk.Label(info_frame, text=label + ":", style="Panel.Muted.TLabel",
                      font=font_tuple("body")).grid(row=i, column=0, sticky="w", pady=2)
            ttk.Label(info_frame, text=val, style="Panel.Secondary.TLabel",
                      font=font_tuple("body")).grid(row=i, column=1, sticky="w", padx=(SPACING["sm"], 0), pady=2)

        # Advanced mode
        adv_var = tk.BooleanVar(value=self._state.settings.advanced_mode)
        ttk.Checkbutton(body, text="Advanced mode (extra diagnostics and metrics)",
                       variable=adv_var,
                       command=lambda: self._on_pref("advanced_mode", adv_var.get())).grid(
            row=1, column=0, sticky="w", pady=(SPACING["md"], SPACING["lg"]))
        self._pref_vars["advanced_mode"] = adv_var

        # Actions
        btn_frame = ttk.Frame(body, style="Panel.TFrame")
        btn_frame.grid(row=2, column=0, sticky="ew")
        btn_frame.columnconfigure(0, weight=1)
        ttk.Button(btn_frame, text="Reset to Defaults", style="Ghost.TButton",
                  command=self._on_reset).pack(side="left", padx=(0, SPACING["sm"]))
        ttk.Button(btn_frame, text="Export Settings", style="Ghost.TButton",
                  command=self._on_export).pack(side="left")

    def _on_theme_select(self, key: str):
        self._state.settings.theme_key = key
        self._on_theme_change(key)
        self._refresh_theme_cards()

    def _refresh_theme_cards(self):
        if not hasattr(self, "_theme_cards"):
            return
        for key, card in self._theme_cards.items():
            for child in card.winfo_children():
                child.destroy()
            t = THEMES.get(key, {})
            self._remake_card(card, key, t)

    def _remake_card(self, outer: tk.Frame, key: str, t: dict):
        tm = get_theme_manager()
        tokens = tm.tokens
        is_selected = (self._state.settings.theme_key == key)
        accent = tokens.get("accent_primary", "#5eb8e6")
        outer.configure(bg=accent if is_selected else tokens.get("border_soft", "#1c1e22"))
        inner = tk.Frame(outer, bg=t["bg_panel"], width=96, height=64, padx=4, pady=4)
        inner.pack_propagate(False)
        inner.pack()
        bar = tk.Canvas(inner, height=8, bg=t["bg_panel"], highlightthickness=0)
        bar.pack(fill="x")
        w = 88
        for i in range(w):
            t_val = i / max(w - 1, 1)
            from ..theme.gradients import lerp_color
            col = lerp_color(t["gradient_start"], t["gradient_end"], t_val)
            bar.create_line(i, 0, i, 8, fill=col)
        name = t.get("name", key)
        lbl = tk.Label(inner, text=name, bg=t["bg_panel"], fg=t["text_secondary"],
                      font=font_tuple("caption"), wraplength=88, justify="center")
        lbl.pack(fill="both", expand=True)
        sel_mark = "●" if is_selected else "○"
        sel_lbl = tk.Label(inner, text=sel_mark, bg=t["bg_panel"],
                          fg=accent if is_selected else t["text_muted"], font=font_tuple("body"))
        sel_lbl.pack()
        for w_ in (outer, inner, lbl, sel_lbl, bar):
            w_.bind("<Button-1>", lambda e, k=key: self._on_theme_select(k))

    def _on_density_change(self):
        val = self._density_var.get()
        self._state.settings.density = val
        self._state.save()
        if self._on_preference_changed:
            self._on_preference_changed()

    def _on_pref(self, attr: str, value: bool):
        s = self._state.settings
        if hasattr(s, attr):
            setattr(s, attr, value)
        self._state.save()
        if self._on_preference_changed:
            self._on_preference_changed()

    def _on_reset(self):
        if not messagebox.askyesno("Reset Settings", "Reset all settings to defaults?"):
            return
        self._state.settings = type(self._state.settings)()
        self._state.save()
        self._on_theme_change(self._state.settings.theme_key)
        if self._on_preference_changed:
            self._on_preference_changed()
        self._refresh_all()

    def _on_export(self):
        import json
        data = self._state.settings.to_dict()
        try:
            root = self.winfo_toplevel()
            root.clipboard_clear()
            root.clipboard_append(json.dumps(data, indent=2))
            messagebox.showinfo("Export", "Settings copied to clipboard.")
        except Exception:
            messagebox.showerror("Export", "Could not copy to clipboard.")

    def _refresh_all(self):
        self._density_var.set(self._state.settings.density or "comfortable")
        if self._density_var.get() not in ("comfortable", "cozy", "compact"):
            self._density_var.set("comfortable")
        for attr, var in self._pref_vars.items():
            if hasattr(self._state.settings, attr):
                var.set(getattr(self._state.settings, attr))
        self._refresh_theme_cards()

    def on_show(self):
        """Sync state from persisted settings when page is shown."""
        s = self._state.settings
        self._density_var.set(s.density if s.density in ("comfortable", "cozy", "compact") else "comfortable")
        for attr, var in getattr(self, "_pref_vars", {}).items():
            if hasattr(s, attr):
                var.set(getattr(s, attr))
        self._refresh_theme_cards()
