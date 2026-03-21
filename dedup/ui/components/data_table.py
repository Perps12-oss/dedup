"""
DataTable — styled Treeview wrapper with sticky headers, sort, and density support.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, List, Optional, Tuple

OptionalCallback = Optional[Callable[[], None]]

ColumnSpec = Tuple[str, str, int, str]  # (key, heading, width, anchor)


class DataTable(ttk.Frame):
    """
    Reusable sortable data table.

    Usage
    -----
    table = DataTable(parent, columns=[
        ("name", "Name", 200, "w"),
        ("size", "Size",  80, "e"),
    ])
    table.insert_row(iid="1", values=("foo.txt", "1.2 MB"), tags=("alt",))
    """

    def __init__(
        self,
        parent,
        columns: List[ColumnSpec],
        show_tree: bool = False,
        selectmode: str = "browse",
        height: int = 12,
        sortable: bool = True,
        on_select: Optional[Callable[[str], None]] = None,
        on_double_click: Optional[Callable[[str], None]] = None,
        **kwargs,
    ):
        super().__init__(parent, **kwargs)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self._columns = columns
        self._sortable = sortable
        self._on_select = on_select
        self._on_double_click = on_double_click
        self._sort_col: Optional[str] = None
        self._sort_rev: bool = False

        col_ids = [c[0] for c in columns]
        show = "tree headings" if show_tree else "headings"

        self.tree = ttk.Treeview(
            self,
            columns=col_ids,
            show=show,
            selectmode=selectmode,
            height=height,
        )

        for key, heading, width, anchor in columns:
            if sortable:
                self.tree.heading(key, text=heading, command=lambda c=key: self._sort_by(c))
            else:
                self.tree.heading(key, text=heading)
            self.tree.column(key, width=width, anchor=anchor, stretch=False)

        if show_tree:
            self.tree.column("#0", width=180, anchor="w", stretch=False)

        vsb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(self, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.vsb = vsb
        self.hsb = hsb

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        self.tree.bind("<<TreeviewSelect>>", self._on_sel)
        self.tree.bind("<Double-1>", self._on_dbl)

        # Alternate row tag styling
        self.tree.tag_configure("alt", background="")
        self.tree.tag_configure("safe", background="")
        self.tree.tag_configure("warn", background="")
        self.tree.tag_configure("danger", background="")

    def set_height(self, lines: int) -> None:
        """Set visible Treeview rows (ttk does not auto-expand height with the frame)."""
        lines = max(3, min(48, int(lines)))
        self.tree.configure(height=lines)

    def bind_height_to_parent(
        self,
        parent: tk.Widget,
        *,
        min_lines: int = 4,
        max_lines: int = 28,
        reserve_px: int = 0,
        line_px: int = 22,
        after_change: OptionalCallback = None,
    ) -> None:
        """Resize visible row count when `parent` is resized so the table fills available space."""

        def _on_cfg(event: tk.Event) -> None:
            if event.widget is not parent:
                return
            h = int(event.height) - int(reserve_px)
            if h < 48:
                return
            n = max(min_lines, min(max_lines, h // max(16, line_px)))
            self.set_height(n)
            if after_change:
                try:
                    after_change()
                except Exception:
                    pass

        parent.bind("<Configure>", _on_cfg, add="+")

    def clear(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

    def insert_row(
        self,
        iid: str,
        values: tuple,
        tags: tuple = (),
        text: str = "",
        parent: str = "",
        open_item: bool = False,
    ):
        self.tree.insert(parent, "end", iid=iid, text=text, values=values, tags=tags, open=open_item)

    def insert_child(self, parent_iid: str, iid: str, values: tuple, tags: tuple = (), text: str = ""):
        self.tree.insert(parent_iid, "end", iid=iid, text=text, values=values, tags=tags)

    def selection(self) -> Optional[str]:
        sel = self.tree.selection()
        return sel[0] if sel else None

    def select(self, iid: str):
        if iid and self.tree.exists(iid):
            self.tree.selection_set(iid)
            self.tree.see(iid)

    def _on_sel(self, event):
        if self._on_select:
            sel = self.tree.selection()
            if sel:
                self._on_select(sel[0])

    def _on_dbl(self, event):
        if self._on_double_click:
            sel = self.tree.selection()
            if sel:
                self._on_double_click(sel[0])

    def _sort_by(self, col: str):
        items = [(self.tree.set(k, col), k) for k in self.tree.get_children("")]
        rev = self._sort_rev if self._sort_col == col else False
        try:
            items.sort(key=lambda x: float(x[0].replace(",", "").replace(" ", "").split()[0]), reverse=rev)
        except (ValueError, IndexError):
            items.sort(key=lambda x: x[0].lower(), reverse=rev)
        for i, (_, k) in enumerate(items):
            self.tree.move(k, "", i)
        self._sort_col = col
        self._sort_rev = not rev

    def apply_row_colors(self, tag: str, background: str, foreground: str = ""):
        kw = {"background": background}
        if foreground:
            kw["foreground"] = foreground
        self.tree.tag_configure(tag, **kw)
