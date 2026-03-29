"""Theme registry — the single lookup table for all themes."""

from __future__ import annotations

from typing import Dict, List

from .cinematic_tokens import finalize_cinematic_tokens
from .theme_tokens import (
    ARCTIC_GLASS,
    AURORA_SLATE,
    BRONZE_LEDGER,
    CEREBRO_NOIR,
    EMERALD_FORGE,
    FOREST_NIGHT,
    GRAPHITE_EMBER,
    MIDNIGHT_CIRCUIT,
    NEON_CARBON,
    OBSIDIAN_GOLD,
    OCEAN_DEPTH,
    ORCHID_SMOKE,
    POLAR_MINT,
    SILVER_HORIZON,
    STORM_METAL,
    VIOLET_LEDGER,
    ThemeDict,
)

THEMES: Dict[str, ThemeDict] = {
    "cerebro_noir": CEREBRO_NOIR,
    "aurora_slate": AURORA_SLATE,
    "midnight_circuit": MIDNIGHT_CIRCUIT,
    "emerald_forge": EMERALD_FORGE,
    "graphite_ember": GRAPHITE_EMBER,
    "obsidian_gold": OBSIDIAN_GOLD,
    "violet_ledger": VIOLET_LEDGER,
    "ocean_depth": OCEAN_DEPTH,
    "forest_night": FOREST_NIGHT,
    "neon_carbon": NEON_CARBON,
    "storm_metal": STORM_METAL,
    "orchid_smoke": ORCHID_SMOKE,
    "arctic_glass": ARCTIC_GLASS,
    "polar_mint": POLAR_MINT,
    "bronze_ledger": BRONZE_LEDGER,
    "silver_horizon": SILVER_HORIZON,
}

# Default theme for new installs / fresh settings.
# "Obsidian Gold" is the most premium base for CTK experiments.
DEFAULT_THEME = "obsidian_gold"


def get_theme_names() -> List[str]:
    return list(THEMES.keys())


def get_theme(key: str) -> ThemeDict:
    raw = THEMES.get(key, THEMES[DEFAULT_THEME])
    return finalize_cinematic_tokens(dict(raw))


def get_display_names() -> List[str]:
    return [t["name"] for t in THEMES.values()]


def key_from_display_name(display: str) -> str:
    for key, t in THEMES.items():
        if t["name"] == display:
            return key
    return DEFAULT_THEME
