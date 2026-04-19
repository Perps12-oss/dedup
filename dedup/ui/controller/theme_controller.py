"""ThemeController — applies and persists theme tokens to CTK shell widgets."""

from __future__ import annotations

import logging
import sys
from typing import Any, Callable

from ..state.store import UiDegradedFlags
from ..theme.gradients import cinematic_chrome_color, paint_cinematic_backdrop
from ..theme.theme_manager import parse_gradient_stops_from_raw

_log = logging.getLogger(__name__)


class ThemeController:
    """Owns all theme-application logic; wired to shell widgets after build."""

    def __init__(self, tm: Any, state: Any, store: Any, toast_fn: Callable[[str], None], root: Any) -> None:
        self._tm = tm
        self._state = state
        self._store = store
        self._toast = toast_fn
        self._root = root
        # Widget refs — set via wire() after build
        self._top_gradient = None
        self._nav = None
        self._main_stack = None
        self._content = None
        self._content_host = None
        self._pages: dict = {}
        self._nav_buttons: dict = {}
        self._active_page_getter: Callable[[], str] = lambda: ""
        self._backdrop_after_id: str | None = None
        self._cinematic_canvas = None

    def wire(
        self,
        *,
        top_gradient: Any,
        nav: Any,
        main_stack: Any,
        content: Any,
        content_host: Any,
        pages: dict,
        nav_buttons: dict,
        active_page_getter: Callable[[], str],
        cinematic_canvas: Any,
    ) -> None:
        self._top_gradient = top_gradient
        self._nav = nav
        self._main_stack = main_stack
        self._content = content
        self._content_host = content_host
        self._pages = pages
        self._nav_buttons = nav_buttons
        self._active_page_getter = active_page_getter
        self._cinematic_canvas = cinematic_canvas

    def apply_from_settings(self) -> None:
        from ..theme.theme_registry import DEFAULT_THEME

        key = (self._state.settings.theme_key or "").strip() or DEFAULT_THEME
        stops = parse_gradient_stops_from_raw(self._state.settings.custom_gradient_stops)
        try:
            self._tm.apply(key, self._root, gradient_stops=stops)
            self._store.clear_theme_degraded()
        except Exception as e:
            _log.warning("Theme apply failed (degraded styling): %s", e)
            self._store.set_ui_degraded(UiDegradedFlags(theme_apply_failed=True, theme_last_error=str(e)[:400]))

    def main_chrome_color(self, tokens: dict) -> str:
        """Solid fill for the main column (must match gradient tokens — CTk cannot show Canvas through)."""
        return cinematic_chrome_color(
            tokens,
            reduced=bool(getattr(self._state.settings, "reduced_gradients", False)),
        )

    def on_tokens(self, tokens: dict) -> None:
        """Apply token changes to CTK surfaces (nav/content)."""
        try:
            bg = str(tokens.get("bg_base", "#0f131c"))
            sidebar = str(tokens.get("bg_base", "#141924"))
            panel_bg = str(tokens.get("bg_panel", "#1C2128"))
            acc = str(tokens.get("accent_primary", "#3B8ED0"))
            chrome = self.main_chrome_color(tokens)
            if self._top_gradient is not None:
                try:
                    self._top_gradient.configure(bg=bg)
                    self._top_gradient.update_from_tokens(tokens)
                except Exception as e:
                    _log.warning("Top gradient update failed: %s", e)
            try:
                self._root.configure(fg_color=bg)
            except Exception as e:
                _log.debug("Root fg_color configure: %s", e)
            try:
                self._root.configure(background=bg)
            except Exception as e:
                _log.debug("Root background configure: %s", e)
            if self._nav is not None:
                self._nav.configure(fg_color=sidebar)
            if self._main_stack is not None:
                try:
                    self._main_stack.configure(bg=bg)
                except Exception as e:
                    _log.warning("Main stack bg update failed: %s", e)
            self.paint_backdrop()
            if self._content is not None:
                self._content.configure(fg_color=chrome)
            if self._content_host is not None:
                self._content_host.configure(fg_color=chrome)
            for page in self._pages.values():
                try:
                    page.configure(fg_color=panel_bg)
                except Exception:
                    pass
                if hasattr(page, "apply_theme_tokens"):
                    try:
                        page.apply_theme_tokens(tokens)
                    except Exception as e:
                        _log.warning("Page apply_theme_tokens failed: %s", e)
            inactive = sidebar
            active_page = self._active_page_getter()
            for name, btn in self._nav_buttons.items():
                if name == active_page:
                    btn.configure(fg_color=acc, text_color=str(tokens.get("text_primary", "#ffffff")))
                else:
                    btn.configure(fg_color=inactive, text_color=str(tokens.get("text_secondary", "#b3b3b3")))
        except Exception as e:
            _log.warning("Full theme token pass failed: %s", e)
        self._sync_dwm_titlebar(tokens)

    def paint_backdrop(self, _event: object = None) -> None:
        """Spine 2: full-area Tk Canvas behind an inset CTk shell (multi-stop wash). Debounced 30ms."""
        if self._backdrop_after_id is not None:
            self._root.after_cancel(self._backdrop_after_id)
        self._backdrop_after_id = self._root.after(30, self._do_paint_backdrop)

    def _do_paint_backdrop(self) -> None:
        self._backdrop_after_id = None
        c = self._cinematic_canvas
        if c is None:
            return
        try:
            w = max(2, int(c.winfo_width() or 0))
            h = max(2, int(c.winfo_height() or 0))
            if w < 8 or h < 8:
                return
            paint_cinematic_backdrop(
                c,
                w,
                h,
                self._tm.tokens,
                reduced=bool(getattr(self._state.settings, "reduced_gradients", False)),
            )
        except Exception as e:
            _log.warning("Cinematic backdrop paint failed: %s", e)

    def on_theme_change(self, key: str) -> None:
        """Handle theme selection change - persist theme_key to settings."""
        self._state.settings.theme_key = key
        self._state.settings.custom_gradient_stops = None
        self._state.save()
        self.apply_from_settings()
        self._toast(f"Theme: {key}")

    def on_theme_preference_changed(self) -> None:
        """Handle theme preference changes from Themes page - persist custom gradients."""
        custom_stops = self._tm.get_custom_gradient_stops()
        if custom_stops:
            self._state.settings.custom_gradient_stops = [[float(pos), str(col)] for pos, col in custom_stops]
        else:
            self._state.settings.custom_gradient_stops = None
        self._state.save()

    def on_settings_changed(self) -> None:
        """Handle settings changes from Settings page."""
        self._store.set_ui_mode("advanced" if self._state.settings.advanced_mode else "simple")
        try:
            self.on_tokens(self._tm.tokens)
        except Exception as e:
            _log.warning("Settings-changed theme refresh failed: %s", e)

    def _sync_dwm_titlebar(self, tokens: dict) -> None:
        """Set Windows title-bar color to match bg_base and enable immersive dark mode.

        Eliminates the OS accent-color clash ("olive bar above the app").
        Silently skipped on non-Windows or when DWM is unavailable (pre-Win10).
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20  (Win 10 20H1+)
        DWMWA_CAPTION_COLOR            = 35  (Win 11 22000+)
        """
        if sys.platform != "win32":
            return
        try:
            import ctypes
            import ctypes.wintypes

            dwmapi = ctypes.windll.dwmapi  # type: ignore[attr-defined]
            hwnd = self._root.winfo_id()

            # Force dark title-bar chrome (light close/min/max icons on dark bg)
            mode = str(tokens.get("mode", "dark")).lower()
            dark = ctypes.c_int(0 if mode == "light" else 1)
            dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark), ctypes.sizeof(dark))

            # Match caption background to app surface-0 (bg_base)
            raw = str(tokens.get("bg_base", "#0c0d0e")).strip().lstrip("#")
            if len(raw) == 6:
                r, g, b = int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)
                colorref = ctypes.c_int(r | (g << 8) | (b << 16))  # COLORREF = 0x00BBGGRR
                dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(colorref), ctypes.sizeof(colorref))
        except Exception as e:
            _log.debug("DWM title-bar sync skipped (non-fatal): %s", e)
