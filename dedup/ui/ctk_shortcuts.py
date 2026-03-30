"""
Keyboard shortcuts for CustomTkinter app.

Provides global shortcuts for navigation and common actions.
"""

from __future__ import annotations

from tkinter import Event
from typing import Callable, List, Tuple

import customtkinter as ctk

Handler = Callable[[Event], object]

Entry = Tuple[str, str, Handler]


class CTKShortcutRegistry:
    """Registry for global keyboard shortcuts in CTK app."""

    def __init__(self, root: ctk.CTk) -> None:
        self._root = root
        self._entries: List[Tuple[str, str]] = []

    def register(self, sequence: str, description: str, handler: Handler, add: str = "+") -> None:
        """Register a keyboard shortcut."""
        self._entries.append((sequence, description))
        self._root.bind(sequence, handler, add=add)

    def describe_lines(self) -> List[str]:
        """Get formatted description lines for help."""
        lines = []
        for seq, desc in self._entries:
            # Convert tkinter key sequences to user-friendly format
            friendly_key = seq.replace("<Control-Key-", "Ctrl+")
            friendly_key = friendly_key.replace("<Key-", "")
            friendly_key = friendly_key.replace(">", "")
            friendly_key = friendly_key.replace("comma", ",")

            lines.append(f"  {friendly_key:<22} {desc}")
        return lines
