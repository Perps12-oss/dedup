# Theme system

## Structure

- **Tokens:** `dedup/ui/theme/theme_tokens.py` — semantic dicts per preset (`bg_base`, `text_primary`, `accent_primary`, `gradient_start` / `gradient_end`, etc.).
- **Registry:** `theme_registry.py` maps keys → token dicts (15 multigradient presets + CEREBRO Noir).
- **Application:** `ThemeManager.apply(key, root)` configures `ttk.Style` (`clam`) and root background; observers receive updated tokens (e.g. `GradientBar`, `ThemePage` contrast panel).
- **Persistence:** `AppSettings.theme_key` in `ui_settings.json` (via `load_settings` / `save_settings`).
- **Extended model:** `dedup/ui/theme/theme_config.py` — `ThemeConfig` dataclass for future custom gradients, history, import/export (not yet wired to persistence).

## Adding a preset

1. Define a new `ThemeDict` in `theme_tokens.py`.
2. Register in `THEMES` in `theme_registry.py`.
3. Swatches on **Themes** page and Settings pick it up automatically.

## Contrast

`dedup/ui/theme/contrast.py` implements WCAG relative luminance and contrast ratio for `#RRGGBB` colours. The Themes page shows an informative snapshot for `text_primary` and `accent_primary` against `bg_base`.

## Programmatic API

```python
from dedup.ui.theme import get_theme_manager
get_theme_manager().apply("aurora_slate", root_window)
```

## Skipped / planned

- Multi-stop gradient editor UI, draggable stops, JSON import/export → see `docs/PHASE_ROLLOUT.md`.
- `ThemeConfig` persisted in SQLite — deferred until editor lands.
