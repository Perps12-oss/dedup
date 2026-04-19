"""
CEREBRO design tokens — centralized design system.

Pages use :func:`get_theme_colors` for the ``self._tokens`` dict of (light, dark) pairs.

Cinematic chrome is finalized in ``theme.cinematic_tokens`` (``cinematic_chrome_base`` /
``cinematic_chrome_dark`` on each preset, with computed fallbacks). Use
:func:`ctk_pairs_from_semantic_tokens` to mirror a live :class:`ThemeManager` dict in CTk pairs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

from ..theme.cinematic_tokens import adjust_color

ColorPair = Tuple[str, str]


def resolve_border_token(tokens: dict, *, fallback: str = "#21262D") -> str:
    """Prefer ``border_soft`` (theme registry); fall back to ``border_subtle`` (CTk pair keys)."""
    v = tokens.get("border_soft") or tokens.get("border_subtle", fallback)
    return str(v)


def resolve_border_default_token(tokens: dict, *, fallback: str = "#30363D") -> str:
    """Prefer ``border_strong`` (theme registry); fall back to ``border_default`` (CTk pair keys)."""
    v = tokens.get("border_strong") or tokens.get("border_default", fallback)
    return str(v)


@dataclass(frozen=True)
class ColorPalette:
    """Immutable palette; each field is ``(light, dark)``."""

    bg_base: ColorPair = ("#F8FAFC", "#0A0E14")
    bg_surface: ColorPair = ("#FFFFFF", "#0D1117")
    bg_elevated: ColorPair = ("#F1F5F9", "#161B22")
    bg_panel: ColorPair = ("#E2E8F0", "#1C2128")
    bg_overlay: ColorPair = ("#CBD5E1", "#21262D")

    accent_primary: ColorPair = ("#0891B2", "#22D3EE")
    accent_secondary: ColorPair = ("#0E7490", "#06B6D4")
    accent_muted: ColorPair = ("#164E63", "#083344")

    text_primary: ColorPair = ("#0F172A", "#F1F5F9")
    text_secondary: ColorPair = ("#475569", "#94A3B8")
    text_muted: ColorPair = ("#64748B", "#64748B")
    text_inverse: ColorPair = ("#F8FAFC", "#0F172A")

    border_subtle: ColorPair = ("#E2E8F0", "#21262D")
    border_default: ColorPair = ("#CBD5E1", "#30363D")
    border_accent: ColorPair = ("#0891B2", "#22D3EE")

    success: ColorPair = ("#059669", "#10B981")
    warning: ColorPair = ("#D97706", "#F59E0B")
    error: ColorPair = ("#DC2626", "#EF4444")
    # Destructive actions (e.g. Move to Trash): solid red + darker red hover — not warning/amber.
    danger: ColorPair = ("#E53E3E", "#E53E3E")
    danger_hover: ColorPair = ("#9B2C2C", "#9B2C2C")
    info: ColorPair = ("#2563EB", "#3B82F6")

    gradient_start: ColorPair = ("#0891B2", "#22D3EE")
    gradient_end: ColorPair = ("#7C3AED", "#A78BFA")
    # Duplicated dark value for CTk (light unused when appearance_mode is dark).
    cinematic_chrome_base: ColorPair = ("#E2E8F0", "#2A2F2C")
    cinematic_chrome_dark: ColorPair = ("#CBD5E1", "#1E221F")


@dataclass(frozen=True)
class Typography:
    display: int = 28
    heading: int = 18
    subheading: int = 15
    body: int = 13
    caption: int = 11
    small: int = 10


@dataclass(frozen=True)
class Spacing:
    xxs: int = 4
    xs: int = 8
    sm: int = 12
    md: int = 16
    lg: int = 20
    xl: int = 24
    xxl: int = 32
    xxxl: int = 48


@dataclass(frozen=True)
class BorderRadius:
    sm: int = 6
    md: int = 10
    lg: int = 14
    xl: int = 16
    full: int = 9999


_palette: ColorPalette | None = None
_typography: Typography | None = None
_spacing: Spacing | None = None
_radii: BorderRadius | None = None


def get_palette() -> ColorPalette:
    global _palette
    if _palette is None:
        _palette = ColorPalette()
    return _palette


def get_typography() -> Typography:
    global _typography
    if _typography is None:
        _typography = Typography()
    return _typography


def get_spacing() -> Spacing:
    global _spacing
    if _spacing is None:
        _spacing = Spacing()
    return _spacing


def get_radii() -> BorderRadius:
    global _radii
    if _radii is None:
        _radii = BorderRadius()
    return _radii


_THEME_COLORS_CACHE: Dict[str, ColorPair] | None = None


def get_theme_colors() -> Dict[str, ColorPair]:
    """Token dict for ``self._tokens`` — values are ``(light, dark)`` tuples.

    Builds once from :func:`get_palette`; each call returns a **shallow copy** so pages
    cannot mutate a shared dict instance.
    """
    global _THEME_COLORS_CACHE
    if _THEME_COLORS_CACHE is None:
        p = get_palette()
        _THEME_COLORS_CACHE = {
            "bg_base": p.bg_base,
            "bg_surface": p.bg_surface,
            "bg_elevated": p.bg_elevated,
            "bg_panel": p.bg_panel,
            "bg_overlay": p.bg_overlay,
            # Tinted status-pill foreground tokens (derived at runtime via cinematic_tokens).
            # Static fallbacks here; live values come from theme manager via apply_theme_tokens().
            "tag_safe_fg": p.success,
            "tag_warn_fg": p.warning,
            "tag_danger_fg": p.error,
            "tag_safe": ("#DCFCE7", "#0D2A16"),
            "tag_warn": ("#FEF3C7", "#2A1E00"),
            "tag_danger": ("#FEE2E2", "#2A0D0D"),
            "accent_primary": p.accent_primary,
            "accent_secondary": p.accent_secondary,
            "accent_muted": p.accent_muted,
            "text_primary": p.text_primary,
            "text_secondary": p.text_secondary,
            "text_muted": p.text_muted,
            "text_inverse": p.text_inverse,
            "border_subtle": p.border_subtle,
            # Alias so static CTk builds match theme registry naming.
            "border_soft": p.border_subtle,
            "border_strong": p.border_default,
            "border_default": p.border_default,
            "border_accent": p.border_accent,
            "success": p.success,
            "warning": p.warning,
            "error": p.error,
            "danger": p.danger,
            "danger_hover": p.danger_hover,
            "info": p.info,
            "gradient_start": p.gradient_start,
            "gradient_end": p.gradient_end,
            "cinematic_chrome_base": p.cinematic_chrome_base,
            "cinematic_chrome_dark": p.cinematic_chrome_dark,
        }
    d = dict(_THEME_COLORS_CACHE)
    # Backfill if cache was built before danger tokens existed (hot reload / long-lived shells).
    p = get_palette()
    d.setdefault("danger", p.danger)
    d.setdefault("danger_hover", p.danger_hover)
    return d


def ctk_pairs_from_semantic_tokens(theme_tokens: dict) -> Dict[str, ColorPair]:
    """Build ``(light, dark)`` pairs from a finalized theme dict (same hex both sides for CTk dark UI)."""
    p = get_palette()

    def dup(key: str, fallback: ColorPair) -> ColorPair:
        v = theme_tokens.get(key)
        if isinstance(v, str) and v.startswith("#") and len(v.strip()) >= 7:
            h = v.strip()[:7]
            return (h, h)
        return fallback

    chrome_b = dup("cinematic_chrome_base", p.cinematic_chrome_base)
    chrome_d = dup("cinematic_chrome_dark", p.cinematic_chrome_dark)
    panel_hex = theme_tokens.get("bg_panel")
    elev_hex = theme_tokens.get("bg_elevated")
    if isinstance(panel_hex, str) and panel_hex.startswith("#"):
        ph = panel_hex.strip()[:7]
        panel: ColorPair = (ph, ph)
    else:
        panel = (
            adjust_color(chrome_b[0], brightness=-5),
            adjust_color(chrome_b[1], brightness=-5),
        )
    if isinstance(elev_hex, str) and elev_hex.startswith("#"):
        eh = elev_hex.strip()[:7]
        elevated: ColorPair = (eh, eh)
    else:
        elevated = (
            adjust_color(chrome_b[0], brightness=-2),
            adjust_color(chrome_b[1], brightness=-2),
        )

    return {
        "bg_base": dup("bg_base", p.bg_base),
        "bg_surface": dup("bg_surface", p.bg_surface),
        "bg_elevated": elevated,
        "bg_panel": panel,
        "bg_overlay": dup("bg_overlay", p.bg_overlay),
        "accent_primary": dup("accent_primary", p.accent_primary),
        "accent_secondary": dup("accent_secondary", p.accent_secondary),
        "accent_muted": dup("accent_muted", p.accent_muted),
        "text_primary": dup("text_primary", p.text_primary),
        "text_secondary": dup("text_secondary", p.text_secondary),
        "text_muted": dup("text_muted", p.text_muted),
        "text_inverse": dup("text_inverse", p.text_inverse),
        "border_subtle": dup("border_soft", p.border_subtle),
        "border_default": dup("border_strong", p.border_default),
        "border_accent": dup("border_strong", p.border_accent),
        "success": dup("success", p.success),
        "warning": dup("warning", p.warning),
        "error": dup("danger", p.error),
        "danger": dup("danger", p.danger),
        "danger_hover": dup("danger_hover", p.danger_hover),
        "info": dup("info", p.info),
        "gradient_start": dup("gradient_start", p.gradient_start),
        "gradient_end": dup("gradient_end", p.gradient_end),
        "cinematic_chrome_base": chrome_b,
        "cinematic_chrome_dark": chrome_d,
        # Tinted status-pill tokens — foreground uses saturated accent, background is tinted.
        "tag_safe_fg": dup("tag_safe_fg", p.success),
        "tag_warn_fg": dup("tag_warn_fg", p.warning),
        "tag_danger_fg": dup("tag_danger_fg", p.error),
        "tag_safe": dup("tag_safe", ("#DCFCE7", "#0D2A16")),
        "tag_warn": dup("tag_warn", ("#FEF3C7", "#2A1E00")),
        "tag_danger": dup("tag_danger", ("#FEE2E2", "#2A0D0D")),
    }


PALETTE = get_palette()
TYPOGRAPHY = get_typography()
SPACING = get_spacing()
RADII = get_radii()
