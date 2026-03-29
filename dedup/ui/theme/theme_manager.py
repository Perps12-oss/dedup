"""
CEREBRO ThemeManager
====================
Applies a token-based theme to the running tkinter application via ttk.Style.
Uses a 'clam' base for full cross-platform colour control.
"""

from __future__ import annotations

import logging
import tkinter as tk
from tkinter import ttk
from typing import Any, Callable, List, Optional, Tuple

from .cinematic_tokens import finalize_cinematic_tokens
from .design_system import font_tuple, get_font_scale
from .gradients import lerp_color
from .theme_registry import DEFAULT_THEME, get_theme
from .theme_tokens import ThemeDict

_INSTANCE: Optional["ThemeManager"] = None
_log = logging.getLogger(__name__)


def _try_set_sun_valley_theme(root: tk.Tk, dark: bool) -> bool:
    """
    Apply optional sv-ttk Fluent-style base (install: pip install sv-ttk, extra modern-ui).
    Returns True if applied; False on missing package or error — caller falls back to clam.
    """
    try:
        import sv_ttk  # type: ignore[import-untyped]

        sv_ttk.set_theme("dark" if dark else "light")
        return True
    except Exception:
        return False


def parse_gradient_stops_from_raw(raw: Any) -> Optional[List[Tuple[float, str]]]:
    """Normalize AppSettings.custom_gradient_stops (JSON lists) into sorted stops."""
    if not raw:
        return None
    out: List[Tuple[float, str]] = []
    for item in raw:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            try:
                pos = float(item[0])
                col = str(item[1]).strip()
                if col and not col.startswith("#"):
                    col = "#" + col
                if len(col) == 7:
                    out.append((max(0.0, min(1.0, pos)), col))
            except (TypeError, ValueError):
                continue
    out.sort(key=lambda x: x[0])
    return out if len(out) >= 2 else None


def merge_gradient_into_tokens(base: ThemeDict, stops: List[Tuple[float, str]]) -> ThemeDict:
    """Copy preset tokens and override gradient_* + multi-stop strip data."""
    s = sorted(stops, key=lambda x: x[0])
    t = dict(base)
    # Force chrome + panels to follow the new gradient, not a stale finalized chrome.
    t.pop("cinematic_chrome_base", None)
    t.pop("cinematic_chrome_dark", None)
    t["gradient_start"] = s[0][1]
    t["gradient_end"] = s[-1][1]
    if len(s) >= 3:
        t["gradient_mid"] = s[len(s) // 2][1]
    else:
        t["gradient_mid"] = lerp_color(s[0][1], s[-1][1], 0.5)
    t["_multi_gradient_stops"] = s
    return finalize_cinematic_tokens(t)


def get_theme_manager() -> "ThemeManager":
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = ThemeManager()
    return _INSTANCE


class ThemeManager:
    """
    Singleton that owns theme state and applies it to ttk.Style.
    Observers can subscribe to theme changes to update custom Canvas widgets.
    """

    def __init__(self):
        self._current_key: str = DEFAULT_THEME
        self._tokens: ThemeDict = get_theme(DEFAULT_THEME)
        self._observers: List[Callable[[ThemeDict], None]] = []
        self._sun_valley_enabled: bool = True
        self._sun_valley_dark: bool = True

    @property
    def tokens(self) -> ThemeDict:
        return self._tokens

    @property
    def current_key(self) -> str:
        return self._current_key

    def subscribe(self, callback: Callable[[ThemeDict], None]) -> None:
        self._observers.append(callback)

    def unsubscribe(self, callback: Callable[[ThemeDict], None]) -> None:
        self._observers = [o for o in self._observers if o is not callback]

    def apply(
        self,
        theme_key: str,
        root: tk.Tk,
        *,
        gradient_stops: Optional[List[Tuple[float, str]]] = None,
        sun_valley: bool = True,
    ) -> None:
        self._current_key = theme_key
        base = get_theme(theme_key)
        if gradient_stops and len(gradient_stops) >= 2:
            self._tokens = merge_gradient_into_tokens(base, gradient_stops)
        else:
            self._tokens = dict(base)
        self._sun_valley_enabled = bool(sun_valley)
        self._sun_valley_dark = str(base.get("mode", "dark")).lower() != "light"
        self._configure_styles(root)
        self._apply_tk_defaults(root)
        for cb in self._observers:
            try:
                cb(self._tokens)
            except Exception as e:
                _log.warning("Theme observer failed: %s", e)

    def _configure_styles(self, root: tk.Tk) -> None:
        t = self._tokens
        style = ttk.Style(root)
        if self._sun_valley_enabled:
            if not _try_set_sun_valley_theme(root, self._sun_valley_dark):
                style.theme_use("clam")
        else:
            style.theme_use("clam")

        bg = t["bg_base"]
        panel = t["bg_panel"]
        elev = t["bg_elevated"]
        sidebar = t["bg_sidebar"]
        bsoft = t["border_soft"]
        bstrong = t["border_strong"]
        fg = t["text_primary"]
        fg2 = t["text_secondary"]
        t["text_muted"]
        acc = t["accent_primary"]
        sel = t["selection_bg"]
        success = t["success"]
        warning = t["warning"]
        danger = t["danger"]

        # Root window
        root.configure(background=bg)

        # ---- Base widgets ----
        style.configure("TFrame", background=bg)
        style.configure("TLabel", background=bg, foreground=fg, font=font_tuple("body"))
        style.configure(
            "TEntry",
            fieldbackground=elev,
            foreground=fg,
            insertcolor=fg,
            bordercolor=bstrong,
            lightcolor=bsoft,
            darkcolor=bsoft,
        )
        style.configure(
            "TCombobox",
            fieldbackground=elev,
            foreground=fg,
            selectbackground=sel,
            selectforeground=fg,
            bordercolor=bstrong,
            arrowcolor=fg2,
        )
        style.configure("TCheckbutton", background=bg, foreground=fg, indicatorcolor=elev, indicatorbackground=elev)
        style.configure("TRadiobutton", background=bg, foreground=fg, indicatorcolor=elev)
        style.configure("TSpinbox", fieldbackground=elev, foreground=fg, bordercolor=bstrong)
        style.configure("TScrollbar", background=panel, troughcolor=bg, arrowcolor=fg2, bordercolor=bsoft)
        style.configure("TSeparator", background=bsoft)
        style.configure(
            "TProgressbar", background=acc, troughcolor=elev, bordercolor=bsoft, lightcolor=acc, darkcolor=acc
        )
        style.configure(
            "Thick.Horizontal.TProgressbar",
            background=acc,
            troughcolor=elev,
            bordercolor=bsoft,
            lightcolor=acc,
            darkcolor=acc,
            thickness=14,
        )
        style.configure("TNotebook", background=bg, bordercolor=bsoft, tabmargins=0)
        style.configure("TNotebook.Tab", background=panel, foreground=fg2, padding=[12, 4], bordercolor=bsoft)

        style.map("TNotebook.Tab", background=[("selected", elev)], foreground=[("selected", fg)])
        style.map("TCheckbutton", indicatorcolor=[("selected", acc)])
        focus_ring = t.get("focus_ring", acc)
        style.map("TEntry", bordercolor=[("focus", focus_ring), ("!focus", bstrong)])

        # ---- Panel frames ----
        style.configure("Panel.TFrame", background=panel, relief="solid", borderwidth=1, bordercolor=bsoft)
        style.configure("Sidebar.TFrame", background=sidebar)
        style.configure("Elevated.TFrame", background=elev, relief="solid", borderwidth=1, bordercolor=bstrong)
        style.configure("Card.TFrame", background=panel, relief="solid", borderwidth=1, bordercolor=bsoft)
        style.configure("Strip.TFrame", background=sidebar)

        # ---- Labels on panels ----
        style.configure("Panel.TLabel", background=panel, foreground=fg)
        style.configure("Sidebar.TLabel", background=sidebar, foreground=fg)
        style.configure("Elevated.TLabel", background=elev, foreground=fg)
        # Muted labels use secondary (fg2) for legibility; fgm was too faded
        style.configure("Muted.TLabel", background=bg, foreground=fg2)
        style.configure("Secondary.TLabel", background=bg, foreground=fg2)
        style.configure("Panel.Muted.TLabel", background=panel, foreground=fg2)
        style.configure("Panel.Secondary.TLabel", background=panel, foreground=fg2)
        style.configure("Elevated.Secondary.TLabel", background=elev, foreground=fg2)
        style.configure("Elevated.Muted.TLabel", background=elev, foreground=fg2)
        style.configure("Accent.TLabel", background=bg, foreground=acc)
        style.configure("Panel.Accent.TLabel", background=panel, foreground=acc)
        style.configure("Success.TLabel", background=bg, foreground=success)
        style.configure("Warning.TLabel", background=bg, foreground=warning)
        style.configure("Danger.TLabel", background=bg, foreground=danger)
        style.configure("Panel.Success.TLabel", background=panel, foreground=success)
        style.configure("Panel.Warning.TLabel", background=panel, foreground=warning)
        style.configure("Panel.Danger.TLabel", background=panel, foreground=danger)

        # ---- LabelFrame ----
        style.configure("TLabelframe", background=panel, bordercolor=bstrong, foreground=fg2, relief="solid")
        style.configure("TLabelframe.Label", background=panel, foreground=fg2)

        # ---- Buttons ----
        style.configure(
            "TButton",
            background=elev,
            foreground=fg,
            bordercolor=bstrong,
            lightcolor=bsoft,
            darkcolor=bsoft,
            relief="flat",
            padding=[14, 10],
            font=font_tuple("body_bold"),
        )
        style.map("TButton", background=[("active", bstrong), ("pressed", acc)], foreground=[("pressed", fg)])

        style.configure(
            "Accent.TButton",
            background=acc,
            foreground=bg,
            bordercolor=acc,
            relief="flat",
            padding=[16, 10],
            font=font_tuple("body_bold"),
        )
        style.map(
            "Accent.TButton",
            background=[("active", t["gradient_end"]), ("pressed", t["gradient_start"])],
            foreground=[("active", bg)],
        )

        style.configure(
            "Danger.TButton",
            background=danger,
            foreground=bg,
            bordercolor=danger,
            relief="flat",
            padding=[16, 10],
            font=font_tuple("body_bold"),
        )
        style.map(
            "Danger.TButton",
            background=[
                ("active", t.get("danger_hover", danger)),
                ("disabled", danger),
            ],
            foreground=[("disabled", bg)],
            bordercolor=[
                ("active", t.get("danger_hover", danger)),
                ("disabled", danger),
            ],
        )

        style.configure(
            "Ghost.TButton",
            background=bg,
            foreground=fg2,
            bordercolor=bsoft,
            relief="flat",
            padding=[14, 10],
            font=font_tuple("body"),
        )
        style.map("Ghost.TButton", background=[("active", panel)], foreground=[("active", fg)])

        style.configure(
            "Nav.TButton",
            background=sidebar,
            foreground=fg2,
            bordercolor=sidebar,
            relief="flat",
            padding=[12, 8],
            font=font_tuple("body"),
        )
        style.map(
            "Nav.TButton",
            background=[("active", t["nav_active_bg"]), ("disabled", sidebar)],
            foreground=[("active", t["nav_active_fg"]), ("disabled", t["nav_active_fg"])],
        )

        # ---- Treeview (DataTable) ----
        scale = get_font_scale()
        row_h = max(22, int(round(36 * scale)))
        style.configure(
            "Treeview",
            background=panel,
            foreground=fg,
            fieldbackground=panel,
            bordercolor=bsoft,
            rowheight=row_h,
            font=font_tuple("body"),
        )
        style.configure(
            "Treeview.Heading",
            background=sidebar,
            foreground=fg2,
            bordercolor=bsoft,
            relief="flat",
            font=font_tuple("body_bold"),
        )
        style.map("Treeview", background=[("selected", sel)], foreground=[("selected", fg)])
        style.map("Treeview.Heading", background=[("active", elev)])

        # ---- Paned window ----
        style.configure("TPanedwindow", background=bg)
        style.configure("Sash", sashrelief="flat", sashthickness=4, background=bsoft)

    def _apply_tk_defaults(self, root: tk.Tk) -> None:
        """Apply theme tokens to raw Tk widgets via option_add (Listbox, Canvas, etc.)."""
        t = self._tokens
        bg = t["bg_base"]
        fg = t["text_primary"]
        panel = t["bg_panel"]
        sel = t["selection_bg"]
        # IMPORTANT: Avoid setting broad Tk defaults (e.g. "*Background") when running
        # under CustomTkinter (CTk). CTk manages colors internally and global option_add
        # rules can cause "white repaint blocks" and incorrect label backgrounds.
        is_ctk_root = "customtkinter" in (type(root).__module__ or "").lower()
        if not is_ctk_root:
            root.option_add("*Background", bg)
            root.option_add("*Foreground", fg)
            root.option_add("*HighlightBackground", bg)
            root.option_add("*HighlightColor", fg)
        root.option_add("*Listbox*Background", panel)
        root.option_add("*Listbox*Foreground", fg)
        root.option_add("*Listbox*SelectBackground", sel)
        root.option_add("*Listbox*SelectForeground", fg)
        root.option_add("*Listbox*Font", font_tuple("caption"))
        root.option_add("*Canvas*Background", panel)
        root.option_add("*Canvas*HighlightBackground", panel)

    def set_appearance_mode(self, mode: str) -> None:
        """Set the appearance mode (light/dark)."""
        self._sun_valley_dark = mode.lower() != "light"

    def get_custom_gradient_stops(self) -> Optional[List[Tuple[float, str]]]:
        """Get custom gradient stops if set."""
        multi = self._tokens.get("_multi_gradient_stops")
        if isinstance(multi, list) and len(multi) >= 2:
            return [(float(p), str(c)) for p, c in multi]
        return None

    def set_custom_gradient_stops(self, stops: List[Tuple[float, str]]) -> None:
        """Set custom gradient stops and update tokens."""
        if len(stops) < 2:
            return
        srt = sorted(stops, key=lambda x: x[0])
        self._tokens = merge_gradient_into_tokens(self._tokens, srt)
        # Notify observers
        for cb in self._observers:
            try:
                cb(self._tokens)
            except Exception as e:
                _log.warning("Theme observer failed (set_custom_gradient_stops): %s", e)

    def clear_custom_gradient_stops(self) -> None:
        """Clear custom gradient stops and revert to preset defaults."""
        base = get_theme(self._current_key)
        self._tokens = dict(base)
        for cb in self._observers:
            try:
                cb(self._tokens)
            except Exception as e:
                _log.warning("Theme observer failed (clear_custom_gradient_stops): %s", e)

    def apply_theme(self, theme_key: str) -> None:
        """Apply a theme by key (without tk root for CTK usage)."""
        self._current_key = theme_key
        base = get_theme(theme_key)
        self._tokens = dict(base)
        for cb in self._observers:
            try:
                cb(self._tokens)
            except Exception as e:
                _log.warning("Theme observer failed (apply_theme): %s", e)

    def t(self, key: str) -> str:
        """Shorthand token lookup."""
        return self._tokens.get(key, self._tokens.get("danger", "#ff00ff"))
