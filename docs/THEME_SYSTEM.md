# Theme system

## Structure

- **Tokens:** `dedup/ui/theme/theme_tokens.py` — semantic dicts per preset (`bg_base`, `text_primary`, `accent_primary`, `gradient_start` / `gradient_end`, etc.).
- **Registry:** `theme_registry.py` maps keys → token dicts (15 multigradient presets + CEREBRO Noir).
- **Application:** `ThemeManager.apply(key, root)` configures `ttk.Style` (`clam`) and root background; observers receive updated tokens (e.g. `GradientBar`, `ThemePage` contrast panel).
- **Persistence:** `AppSettings.theme_key` in `ui_settings.json` (via `load_settings` / `save_settings`).
- **Extended model:** `dedup/ui/theme/theme_config.py` — `ThemeConfig` dataclass; round-trips through JSON on the Themes page (see below).

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

## JSON bundle (`cerebro_theme_config_v1`)

The Themes page **Export** / **Import** buttons read and write a single JSON object:

| Field | Meaning |
|--------|---------|
| `format` | Always `"cerebro_theme_config_v1"`. |
| `exported_at` | ISO-8601 UTC timestamp. |
| `theme_key` | Must exist in `THEMES`. |
| `theme_config` | Dict deserialized by `ThemeConfig.from_dict` (`appearance_mode`, `custom_gradient_stops`, etc.). Stop lists from JSON are normalized to `(position, #hex)` pairs. |
| `ui` | Optional: `reduced_motion`, `reduced_gradients`, `high_contrast` — applied to app settings on import. |

## Skipped / planned

- Multi-stop gradient editor UI and draggable stops → see `docs/PHASE_ROLLOUT.md`.
- `ThemeConfig` / custom presets persisted in SQLite — deferred until editor lands.
