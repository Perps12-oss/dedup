# Button hierarchy (design system)

One explicit hierarchy so action priorities are obvious at a glance. The CTK shell uses CustomTkinter controls themed via `ThemeManager`; map actions to **roles** below and reuse existing page patterns (`ctk_pages/`) before inventing new styles.

| Role | Intent | Typical use |
|------|--------|-------------|
| **Primary** | Main action in this context | Start scan, Start New Scan, Apply (when there is one clear commit). |
| **Secondary** | Alternatives or low-risk follow-ups | Resume, Open last review, Preview, Cancel, Refresh, secondary nav. |
| **Destructive** | Irreversible or high-impact | Execute deletion. At most one per context; never hide without a clear warning. |
| **Disabled** | Unavailable | Same control with disabled state; add a short label or tooltip when the reason is non-obvious. |
| **Warning-context** | Retry / recover in a degraded state | Prefer secondary styling; do not compete with destructive for attention. |

## Rules

- **One primary per block:** In a card or toolbar, at most one primary (or one destructive) as the lead action.
- **Secondary = alternatives:** Resume, Preview, Cancel, Refresh, Open Last Review stay secondary.
- **No hidden destructive actions:** Do not tuck destructive actions behind generic “More” without context.
- **Nav:** Rail and top-bar chrome follow `CerebroCTKApp` / `NavRail` patterns; page content uses the table above.

## Implementation

- Prefer shared helpers and existing CTkButton factories on each page; avoid one-off `fg_color` / `hover_color` unless aligned with theme tokens.
- When adding a new action, pick Primary / Secondary / Destructive / Warning-context and match neighboring controls.
