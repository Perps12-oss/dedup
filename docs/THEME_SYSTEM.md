# Theme system

## Structure

- **Tokens:** `dedup/ui/theme/theme_tokens.py` — semantic dicts per preset (`bg_base`, `text_primary`, `accent_primary`, `gradient_start` / `gradient_end`, etc.).
- **Registry:** `theme_registry.py` maps keys → token dicts (15 multigradient presets + CEREBRO Noir).
- **Application:** `ThemeManager.apply(key, root, gradient_stops=...)` configures `ttk.Style` (`clam`) and root background. Optional **`gradient_stops`** — sorted `(position, #hex)` pairs — merges into a copy of the preset: updates `gradient_start` / `gradient_mid` / `gradient_end` for styles (e.g. Accent buttons) and sets **`_multi_gradient_stops`** for the top **`GradientBar`** strip. Pass `None` to use the preset as-is.
- **Persistence:** `AppSettings.theme_key` and optional **`custom_gradient_stops`** (`[[0.0, "#hex"], …]` with at least two stops) in `ui_settings.json` (via `load_settings` / `save_settings`). Cleared or absent means use the preset gradient only.
- **Extended model:** `dedup/ui/theme/theme_config.py` — `ThemeConfig` dataclass; round-trips through JSON on the Themes page (see below).

## Adding a preset

1. Define a new `ThemeDict` in `theme_tokens.py`.
2. Register in `THEMES` in `theme_registry.py`.
3. Swatches on **Themes** page and Settings pick it up automatically.

## Contrast

`dedup/ui/theme/contrast.py` implements WCAG relative luminance and contrast ratio for `#RRGGBB` colours. The Themes page shows an informative snapshot for `text_primary` and `accent_primary` against `bg_base`.

**Batch audit (presets):** run `python -m dedup.scripts.audit_theme_contrast` (optional `--strict` to exit non-zero on failure; `--md-out docs/THEME_CONTRAST_REPORT.md` to refresh the committed report). Checks align with WCAG AA for **normal** body text (4.5:1) on key semantic pairs; see the script docstring for scope.

## Accent bar gradient (UI)

The **Themes** page includes a **Top accent bar gradient** editor: multi-stop positions (0–1), color picker per stop, preview canvas, **Apply** / **Reset to preset**, and up to eight stops. **Apply** persists `custom_gradient_stops` and reapplies the current preset through `ThemeManager`.

Helpers in `dedup/ui/theme/gradients.py`: **`color_at_gradient_position`**, **`draw_horizontal_multi_stop`** (piecewise-linear between stops). **`GradientBar.update_from_tokens`** draws either multi-stop data from tokens or the default two-color gradient.

## Programmatic API

```python
from dedup.ui.theme.theme_manager import get_theme_manager, parse_gradient_stops_from_raw
from dedup.ui.utils.ui_state import load_settings

settings = load_settings()
stops = parse_gradient_stops_from_raw(settings.custom_gradient_stops)
get_theme_manager().apply("aurora_slate", root_window, gradient_stops=stops)
```

## JSON bundle (`cerebro_theme_config_v1`)

The Themes page **Export** / **Import** buttons read and write a single JSON object:

| Field | Meaning |
|--------|---------|
| `export_format` | Always `"cerebro_theme_config_v1"`. |
| `exported_at_utc` | ISO-8601 UTC timestamp. |
| `theme_key` | Must exist in `THEMES`. |
| `theme_config` | Dict deserialized by `ThemeConfig.from_dict` (`appearance_mode`, `custom_gradient_stops`, etc.). Stop lists from JSON are normalized to `(position, #hex)` pairs. |
| `ui` | Optional: `reduced_motion`, `reduced_gradients`, `high_contrast` — applied to app settings on import. |

Import also restores **`custom_gradient_stops`** into `AppSettings` when present in `theme_config`.

## Deferred / optional

- Draggable gradient stops on canvas (current editor uses numeric positions + color picker).
- Custom full presets or SQLite-backed theme library — product decision; accent overrides cover the common case today.
