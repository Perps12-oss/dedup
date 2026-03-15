"""Theme registry — the single lookup table for all themes."""
from __future__ import annotations
from typing import Dict, List
from .theme_tokens import (
    AURORA_SLATE, MIDNIGHT_CIRCUIT, EMERALD_FORGE, GRAPHITE_EMBER,
    OBSIDIAN_GOLD, VIOLET_LEDGER, OCEAN_DEPTH, FOREST_NIGHT,
    NEON_CARBON, STORM_METAL, ORCHID_SMOKE,
    ARCTIC_GLASS, POLAR_MINT, BRONZE_LEDGER, SILVER_HORIZON,
    ThemeDict,
)

THEMES: Dict[str, ThemeDict] = {
    "aurora_slate":    AURORA_SLATE,
    "midnight_circuit":MIDNIGHT_CIRCUIT,
    "emerald_forge":   EMERALD_FORGE,
    "graphite_ember":  GRAPHITE_EMBER,
    "obsidian_gold":   OBSIDIAN_GOLD,
    "violet_ledger":   VIOLET_LEDGER,
    "ocean_depth":     OCEAN_DEPTH,
    "forest_night":    FOREST_NIGHT,
    "neon_carbon":     NEON_CARBON,
    "storm_metal":     STORM_METAL,
    "orchid_smoke":    ORCHID_SMOKE,
    "arctic_glass":    ARCTIC_GLASS,
    "polar_mint":      POLAR_MINT,
    "bronze_ledger":   BRONZE_LEDGER,
    "silver_horizon":  SILVER_HORIZON,
}

DEFAULT_THEME = "aurora_slate"


def get_theme_names() -> List[str]:
    return list(THEMES.keys())


def get_theme(key: str) -> ThemeDict:
    return THEMES.get(key, THEMES[DEFAULT_THEME])


def get_display_names() -> List[str]:
    return [t["name"] for t in THEMES.values()]


def key_from_display_name(display: str) -> str:
    for key, t in THEMES.items():
        if t["name"] == display:
            return key
    return DEFAULT_THEME
