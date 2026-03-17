"""
UI intents — declarative user actions for controller handling.

Review intents: SetKeep, ClearKeep, PreviewDeletion, ExecuteDeletion.
Pages emit intents; controller performs the action and updates state.
"""

from .review_intents import (
    SetKeep,
    ClearKeep,
    PreviewDeletion,
    ExecuteDeletion,
)

__all__ = [
    "SetKeep",
    "ClearKeep",
    "PreviewDeletion",
    "ExecuteDeletion",
]
