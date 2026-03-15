"""
Unicode/emoji icon constants used throughout CEREBRO UI.
Single source of truth so icons can be swapped without hunting call sites.
"""


class IC:
    # Navigation
    MISSION      = "◈"
    SCAN         = "⚡"
    REVIEW       = "⊞"
    HISTORY      = "⏱"
    DIAGNOSTICS  = "⚙"
    SETTINGS     = "◉"
    THEMES       = "◐"

    # Status
    OK           = "✓"
    WARN         = "⚠"
    ERROR        = "✗"
    INFO         = "ℹ"
    RUNNING      = "▶"
    PAUSED       = "⏸"
    STOPPED      = "■"
    RESUME       = "↩"
    REBUILD      = "↺"
    RESTART      = "⟳"

    # Phase states
    PENDING      = "○"
    ACTIVE       = "●"
    DONE         = "✓"
    FAILED       = "✗"
    SKIPPED      = "—"

    # Files / data
    FILE         = "▪"
    FOLDER       = "▸"
    TRASH        = "🗑"
    KEEP         = "♦"
    DELETE_TGT   = "✗"
    DUPLICATE    = "⊡"
    IMAGE        = "◻"

    # Actions
    BROWSE       = "…"
    ADD          = "+"
    REMOVE       = "−"
    REFRESH      = "↺"
    EXPORT       = "↗"
    COPY         = "⊕"
    CLOSE        = "✕"
    EXPAND       = "▼"
    COLLAPSE     = "▲"
    DRAWER_OPEN  = "◁"
    DRAWER_CLOSE = "▷"

    # Safety
    SHIELD       = "⛨"
    LOCK         = "⊟"
    AUDIT        = "☑"

    # Metrics
    SPEED        = "≈"
    SAVED        = "↓"
    RECLAIM      = "◎"
    CANDIDATES   = "⊕"
    GROUPS       = "⊞"
    WORKERS      = "⊘"
    CHECKPOINT   = "◆"
    SCHEMA       = "≡"
