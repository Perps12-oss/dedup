"""
CEREBRO design tokens — centralized design system.

Pages use :func:`get_theme_colors` for the ``self._tokens`` dict of (light, dark) pairs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

ColorPair = Tuple[str, str]


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
    info: ColorPair = ("#2563EB", "#3B82F6")

    gradient_start: ColorPair = ("#0891B2", "#22D3EE")
    gradient_end: ColorPair = ("#7C3AED", "#A78BFA")


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
            "accent_primary": p.accent_primary,
            "accent_secondary": p.accent_secondary,
            "accent_muted": p.accent_muted,
            "text_primary": p.text_primary,
            "text_secondary": p.text_secondary,
            "text_muted": p.text_muted,
            "text_inverse": p.text_inverse,
            "border_subtle": p.border_subtle,
            "border_default": p.border_default,
            "border_accent": p.border_accent,
            "success": p.success,
            "warning": p.warning,
            "error": p.error,
            "info": p.info,
            "gradient_start": p.gradient_start,
            "gradient_end": p.gradient_end,
        }
    return dict(_THEME_COLORS_CACHE)


PALETTE = get_palette()
TYPOGRAPHY = get_typography()
SPACING = get_spacing()
RADII = get_radii()
