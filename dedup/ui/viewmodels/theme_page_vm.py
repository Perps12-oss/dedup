"""
ThemePageViewModel — theme key, gradient stops, contrast summary, accessibility flags.
"""

from __future__ import annotations

from typing import Any, Callable, List, Optional, Tuple

from dedup.core.observable import Observable
from dedup.models.theme import ContrastSummary, ThemeTokens
from dedup.services.interfaces import IThemeManager
from dedup.ui.theme.contrast import contrast_ratio, format_ratio, passes_aa_normal
from dedup.ui.theme.theme_config import ThemeConfig
from dedup.ui.theme.theme_manager import parse_gradient_stops_from_raw

from ..utils.ui_state import UIState


def build_contrast_summary(tokens: ThemeTokens) -> ContrastSummary:
    d = tokens.as_dict()
    bg = str(d.get("bg_base", "#000000"))
    fg = str(d.get("text_primary", "#ffffff"))
    acc = str(d.get("accent_primary", "#888888"))
    r1 = contrast_ratio(fg, bg)
    r2 = contrast_ratio(acc, bg)
    ok1 = passes_aa_normal(r1)
    ok2 = passes_aa_normal(r2)
    lines = (
        f"text_primary / bg_base   {format_ratio(r1)}  ({'AA text' if ok1 else 'below AA normal'})",
        f"accent_primary / bg_base {format_ratio(r2)}  ({'AA text' if ok2 else 'below AA normal'})",
    )
    return ContrastSummary(
        ratio_label="\n".join(lines),
        passes_aa_normal=bool(ok1 and ok2),
        passes_aa_large=True,
        fg_sample=fg,
        bg_sample=bg,
    )


class ThemePageViewModel:
    def __init__(
        self,
        state: UIState,
        theme: IThemeManager,
        *,
        on_theme_change: Callable[[str], None],
        on_preference_changed: Optional[Callable[[], None]] = None,
    ) -> None:
        self._state = state
        self._theme = theme
        self._on_theme_change = on_theme_change
        self._on_preference_changed = on_preference_changed

        s = state.settings
        self.current_theme_key = Observable(str(s.theme_key))
        stops = parse_gradient_stops_from_raw(s.custom_gradient_stops)
        self.custom_gradient_stops = Observable(list(stops) if stops else [])
        self.reduced_motion = Observable(bool(s.reduced_motion))
        self.high_contrast = Observable(bool(s.high_contrast))
        self.reduced_gradients = Observable(bool(s.reduced_gradients))
        self.contrast_summary = Observable(build_contrast_summary(theme.get_tokens()))

        def _on_tokens(toks: ThemeTokens) -> None:
            self.contrast_summary.set(build_contrast_summary(toks))

        self._token_cb = _on_tokens
        self._theme.subscribe(_on_tokens)

    def detach(self) -> None:
        try:
            self._theme.unsubscribe(self._token_cb)
        except Exception:
            pass

    def select_theme(self, key: str) -> None:
        self._state.settings.theme_key = key
        self.current_theme_key.set(key)
        self._on_theme_change(key)

    def apply_gradient_stops(self, stops: List[Tuple[float, str]]) -> None:
        srt = sorted(stops, key=lambda x: x[0])
        if len(srt) < 2:
            return
        self._state.settings.custom_gradient_stops = [[float(p), str(c)] for p, c in srt]
        try:
            self._state.save()
        except Exception:
            pass
        self.custom_gradient_stops.set(list(srt))
        self._on_theme_change(self._state.settings.theme_key)

    def reset_gradient(self) -> None:
        self._state.settings.custom_gradient_stops = None
        try:
            self._state.save()
        except Exception:
            pass
        self.custom_gradient_stops.set([])
        self._on_theme_change(self._state.settings.theme_key)

    def build_export_theme_config(self) -> ThemeConfig:
        s = self._state.settings
        return ThemeConfig(
            theme_key=s.theme_key,
            reduced_motion=s.reduced_motion,
            custom_gradient_stops=parse_gradient_stops_from_raw(s.custom_gradient_stops),
        )

    def apply_import_dict(self, data: dict[str, Any], *, valid_theme_keys: Any) -> str:
        """Apply imported bundle; returns theme key applied."""
        key = str(data.get("theme_key") or "").strip()
        if not key or key not in valid_theme_keys:
            raise ValueError(f"Unknown or missing theme_key: {key!r}")
        tc = ThemeConfig.from_dict(dict(data.get("theme_config") or {}))
        ui = dict(data.get("ui") or {})
        s = self._state.settings
        s.theme_key = key
        s.reduced_motion = bool(ui.get("reduced_motion", tc.reduced_motion))
        s.reduced_gradients = bool(ui.get("reduced_gradients", s.reduced_gradients))
        s.high_contrast = bool(ui.get("high_contrast", s.high_contrast))
        if tc.custom_gradient_stops:
            s.custom_gradient_stops = [[float(p), str(c)] for p, c in tc.custom_gradient_stops]
        else:
            s.custom_gradient_stops = None
        try:
            self._state.save()
        except Exception:
            pass
        self.current_theme_key.set(key)
        self.reduced_motion.set(s.reduced_motion)
        self.high_contrast.set(s.high_contrast)
        stops = parse_gradient_stops_from_raw(s.custom_gradient_stops)
        self.custom_gradient_stops.set(list(stops) if stops else [])
        self._on_theme_change(key)
        if self._on_preference_changed:
            try:
                self._on_preference_changed()
            except Exception:
                pass
        return key
