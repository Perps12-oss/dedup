"""FilterBar — search + sort + filter controls strip."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional, List


class FilterBar(ttk.Frame):
    """Compact filter/search bar."""

    def __init__(self, parent, on_search: Optional[Callable[[str], None]] = None,
                 filters: Optional[List[tuple]] = None,
                 style: str = "Panel.TFrame", **kwargs):
        super().__init__(parent, style=style, padding=(8, 4), **kwargs)
        self._on_search = on_search

        # Search entry
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", self._on_type)
        search_entry = ttk.Entry(self, textvariable=self._search_var, width=22)
        search_entry.pack(side="left", padx=(0, 8))
        ttk.Label(self, text="Search", style="Panel.Muted.TLabel",
                  font=("Segoe UI", 8)).pack(side="left", padx=(0, 8))

        # Optional filter dropdowns
        self._filter_vars: List[tk.StringVar] = []
        for label, options in (filters or []):
            ttk.Label(self, text=label + ":", style="Panel.Muted.TLabel",
                      font=("Segoe UI", 8)).pack(side="left", padx=(8, 2))
            var = tk.StringVar(value=options[0])
            cb = ttk.Combobox(self, textvariable=var, values=options,
                              state="readonly", width=12)
            cb.pack(side="left", padx=(0, 4))
            self._filter_vars.append(var)

    def _on_type(self, *_):
        if self._on_search:
            self._on_search(self._search_var.get())

    @property
    def search_text(self) -> str:
        return self._search_var.get()

    def get_filter(self, index: int) -> str:
        if index < len(self._filter_vars):
            return self._filter_vars[index].get()
        return ""
