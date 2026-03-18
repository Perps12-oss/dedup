# Button hierarchy (design system)

One explicit hierarchy so action priorities are obvious at a glance. Use these styles consistently; do not mix TButton where a semantic style is intended.

| Role | ttk style | Use when |
|------|-----------|----------|
| **Primary** | `Accent.TButton` | One main action per context (e.g. Start New Scan, Start Scan). |
| **Secondary** | `Ghost.TButton` | Alternative or supporting actions (Resume, Open Last Review, Preview effects, Cancel, Refresh). |
| **Destructive** | `Danger.TButton` | Irreversible or high-impact action (Execute deletion). One per context; never hidden in a menu without warning. |
| **Disabled** | Same style with `state="disabled"` | Action not available; use tooltip or label to explain why when helpful. |
| **Warning-context** | `Ghost.TButton` or `TButton` with warning label | Actions in a warning/degraded context (e.g. “Retry”, “View details”). Prefer Ghost to avoid competing with danger. |
| **Nav** | `Nav.TButton` | Navigation rail items (handled by NavRail; not used in page content). |

## Rules

- **One primary per block:** In a card or toolbar, at most one Accent (or one Danger) as the lead action.
- **Secondary = alternatives:** Resume, Preview, Cancel, Refresh, Open Last Review are secondary.
- **Destructive only when deliberate:** Execute deletion is the only destructive action in the main flow; keep it visible but clearly labeled (e.g. “Execute deletion”).
- **No hidden destructive actions:** Do not put Danger actions in a dropdown or behind a generic “More” without a clear warning.
- **Disabled state:** Use `state="disabled"` on the same style; do not switch to a different style for disabled.

## Implementation

- Theme manager configures `TButton`, `Accent.TButton`, `Danger.TButton`, `Ghost.TButton`, `Nav.TButton`.
- Pages and components use these styles by name; no ad-hoc foreground/background overrides for hierarchy.
- When adding a new action, choose Primary / Secondary / Destructive / Warning-context and apply the matching style.
