"""
Central registry for global keyboard shortcuts (descriptions + bind_all).

Review-specific shortcuts remain on ReviewPage; this covers shell-wide navigation.
"""
from __future__ import annotations

import tkinter as tk
from typing import Callable, List, Tuple

Handler = Callable[[tk.Event], object]

Entry = Tuple[str, str, Handler]


class ShortcutRegistry:
    def __init__(self, root: tk.Misc) -> None:
        self._root = root
        self._entries: List[Tuple[str, str]] = []

    def register(self, sequence: str, description: str, handler: Handler, add: str = "+") -> None:
        self._entries.append((sequence, description))
        self._root.bind_all(sequence, handler, add=add)

    def describe_lines(self) -> List[str]:
        return [f"  {seq:<22} {desc}" for seq, desc in self._entries]
