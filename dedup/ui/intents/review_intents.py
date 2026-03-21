"""
Review intents — user actions for the review/deletion workflow.

Emitted by ReviewPage and SafetyPanel; handled by ReviewController.
Naming aligned with scan intent/controller style.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SetKeep:
    """User chose which file to keep in a duplicate group."""

    group_id: str
    path: str


@dataclass(frozen=True)
class ClearKeep:
    """User cleared the keep selection for a group."""

    group_id: str


@dataclass(frozen=True)
class PreviewDeletion:
    """User requested a dry-run preview of deletion effects (no files changed)."""

    pass


@dataclass(frozen=True)
class ExecuteDeletion:
    """User confirmed and requested execution of the deletion plan."""

    pass
