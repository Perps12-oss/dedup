"""
AppShell — master layout frame.

Layout:
┌──────────────────────────────────────────────────────────┐
│ TOP BAR                                                  │
├────────────┬──────────────────────────┬──────────────────┤
│ NAV RAIL   │ MAIN CONTENT             │ INSIGHT DRAWER   │
│ (72px)     │ (flex)                   │ (220px, toggle)  │
├────────────┴──────────────────────────┴──────────────────┤
│ STATUS STRIP                                             │
└──────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

from tkinter import ttk
from typing import Callable, Dict, List, Optional, Tuple

from ..theme.gradients import GradientBar
from ..theme.theme_manager import get_theme_manager
from ..utils.ui_state import UIState
from .insight_drawer import InsightDrawer
from .nav_rail import NavRail
from .status_strip import StatusStrip
from .top_bar import TopBar

ActionSpec = Tuple[str, str, Callable]


class AppShell(ttk.Frame):
    MAX_CONTENT_WIDTH = 1560

    """
    Root layout container wired to theme, nav, status, and drawer.
    Pages are placed in `self.content` and shown/hidden via `show_page()`.
    """

    def __init__(
        self,
        parent,
        state: UIState,
        on_navigate: Callable[[str], None],
        on_theme_change: Callable[[str], None],
        **kwargs,
    ):
        super().__init__(parent, **kwargs)
        self._state = state
        self._on_navigate = on_navigate
        self._on_theme_change = on_theme_change
        self._tm = get_theme_manager()
        self._pages: Dict[str, ttk.Frame] = {}
        self._active_page: Optional[str] = None
        self._build()

    def _build(self):
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # ---- Top bar ----
        self.top_bar = TopBar(
            self,
            on_theme_change=self._do_theme_change,
            on_density_toggle=self._do_density_toggle,
            on_advanced_toggle=self._do_advanced_toggle,
            on_settings=lambda: self._on_navigate("settings"),
            on_drawer_toggle=self.toggle_drawer,
        )
        self.top_bar.grid(row=0, column=0, sticky="ew")

        # ---- Gradient accent bar under top bar ----
        t = self._tm.tokens
        self._grad_bar = GradientBar(
            self,
            height=2,
            color_start=t["gradient_start"],
            color_end=t["gradient_end"],
        )
        self._grad_bar.grid(row=0, column=0, sticky="sew")

        # ---- Middle: nav + content + drawer ----
        middle = ttk.Frame(self)
        middle.grid(row=1, column=0, sticky="nsew")
        middle.grid_rowconfigure(0, weight=1)
        middle.grid_columnconfigure(1, minsize=1)  # 1px separator only
        middle.grid_columnconfigure(2, weight=1)

        self.nav_rail = NavRail(
            middle,
            on_navigate=self._handle_navigate,
            on_density_toggle=self._do_density_toggle,
        )
        self.nav_rail.grid(row=0, column=0, sticky="ns")

        # Thin separator after nav rail (no extra gap)
        sep = ttk.Separator(middle, orient="vertical")
        sep.grid(row=0, column=1, sticky="ns", padx=0)

        # Content area — all pages stack here
        self.content = ttk.Frame(middle)
        self.content.grid(row=0, column=2, sticky="nsew")
        self.content.grid_rowconfigure(0, weight=1)
        self.content.grid_columnconfigure(0, weight=1)
        # Center page content with a max width so ultra-wide windows stay readable.
        self._content_host = ttk.Frame(self.content, style="TFrame")
        self._content_host.place(x=0, y=0, relheight=1)
        self._content_host.grid_rowconfigure(0, weight=1)
        self._content_host.grid_columnconfigure(0, weight=1)
        self.content.bind("<Configure>", self._on_content_resize, add="+")

        # Insight drawer
        self.insight_drawer = InsightDrawer(middle, on_close=self.toggle_drawer)
        self.insight_drawer.grid(row=0, column=3, sticky="ns")

        # ---- Status strip ----
        self.status_strip = StatusStrip(self)
        self.status_strip.grid(row=2, column=0, sticky="ew")

        # Subscribe to theme changes for the gradient bar
        self._tm.subscribe(self._on_theme_applied)

    def register_page(self, name: str, page: ttk.Frame):
        self._pages[name] = page
        page.grid(row=0, column=0, sticky="nsew", in_=self._content_host)
        page.grid_remove()

    def show_page(self, name: str):
        if self._active_page and self._active_page in self._pages:
            page = self._pages[self._active_page]
            if hasattr(page, "on_hide"):
                page.on_hide()
            page.grid_remove()
        self._active_page = name
        if name in self._pages:
            self._pages[name].grid()
            if hasattr(self._pages[name], "on_show"):
                self._pages[name].on_show()
        self.nav_rail.set_active(name)

    @property
    def active_page(self) -> Optional[str]:
        """Current nav page name, or None before first navigation."""
        return self._active_page

    def set_page_actions(self, actions: List[ActionSpec]):
        self.top_bar.set_page_actions(actions)

    def update_status(
        self,
        session_id: str = "",
        phase: str = "",
        engine_health: str = "Healthy",
        checkpoint_ts: str = "—",
        workers: int = 0,
        warnings: int = 0,
        storage_mode: str = "",
    ):
        self.status_strip.update_session(
            session_id, phase, engine_health, checkpoint_ts, workers, warnings, storage_mode
        )
        mode = "Scanning" if phase and phase not in ("", "Idle") else "Idle"
        self.top_bar.set_session(session_id, mode)

    def set_drawer_content(self, sections):
        self.insight_drawer.clear()
        for title, rows in sections:
            self.insight_drawer.add_section(title, rows)

    def toggle_drawer(self):
        if self.insight_drawer.is_visible:
            self.insight_drawer.hide()
            self._state.settings.show_insight_drawer = False
        else:
            self.insight_drawer.show()
            self.insight_drawer.grid(row=0, column=3, sticky="ns", in_=self.content.master)
            self._state.settings.show_insight_drawer = True
        try:
            self._state.save()
        except Exception:
            pass

    def _handle_navigate(self, page: str):
        self._on_navigate(page)

    def _do_theme_change(self, key: str):
        self._state.settings.theme_key = key
        self._on_theme_change(key)

    def _do_density_toggle(self):
        s = self._state.settings
        cycle = {"comfortable": "cozy", "cozy": "compact", "compact": "comfortable"}
        s.density = cycle.get(s.density, "cozy")
        self.top_bar.set_density_label(s.density)
        try:
            self._state.save()
        except Exception:
            pass
        self._state.emit("density_changed", s.density)

    def _do_advanced_toggle(self):
        s = self._state.settings
        s.advanced_mode = not s.advanced_mode
        self.top_bar.set_advanced(s.advanced_mode)
        self._state.emit("advanced_mode_changed", s.advanced_mode)
        try:
            self._state.save()
        except Exception:
            pass

    def _on_theme_applied(self, tokens: dict):
        self._grad_bar.update_from_tokens(tokens)
        # Re-set theme combo
        self.top_bar.set_current_theme(self._state.settings.theme_key)

    def _on_content_resize(self, event) -> None:
        avail = max(1, int(event.width))
        target = min(avail, self.MAX_CONTENT_WIDTH)
        x = max((avail - target) // 2, 0)
        self._content_host.place_configure(x=x, width=target, relheight=1)

    def apply_preferences(self) -> None:
        """Apply persisted UI preferences to shell widgets (density, drawer, advanced)."""
        s = self._state.settings
        self.top_bar.set_density_label(s.density)
        self.top_bar.set_advanced(s.advanced_mode)
        if s.show_insight_drawer:
            if not self.insight_drawer.is_visible:
                self.insight_drawer.show()
                self.insight_drawer.grid(row=0, column=3, sticky="ns", in_=self.insight_drawer.master)
        else:
            if self.insight_drawer.is_visible:
                self.insight_drawer.hide()
