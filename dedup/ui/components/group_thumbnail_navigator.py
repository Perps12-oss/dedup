"""
Virtualized thumbnail grid for the Review page group navigator.

Renders only visible cells; loads image thumbnails lazily per visible group.
"""

from __future__ import annotations

import math
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import TYPE_CHECKING, Callable, List, Optional

from ...engine.media_types import is_image_extension
from ...engine.thumbnails import generate_thumbnails_async, get_cache_dir
from ..theme.theme_manager import get_theme_manager
from ..utils.formatting import fmt_bytes, truncate_path

if TYPE_CHECKING:
    from ...engine.models import DuplicateGroup

THUMB_PX = 80
NCOLS = 2
CELL_W = 108
CELL_H = 118


def _safe_int_for_display(obj, attr: str, default: int = 0) -> int:
    try:
        return int(getattr(obj, attr, default))
    except (TypeError, ValueError):
        return default


def _fmt_group_size(obj) -> str:
    return fmt_bytes(_safe_int_for_display(obj, "group_size", 0))


class GroupThumbnailNavigator(ttk.Frame):
    """Scrollable 2-column thumbnail grid with windowed rendering."""

    def __init__(
        self,
        parent,
        *,
        on_select: Callable[[str], None],
        resolve_duplicate_group: Callable[[str], Optional["DuplicateGroup"]],
        **kwargs,
    ):
        super().__init__(parent, **kwargs)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self._on_select = on_select
        self._resolve_duplicate_group = resolve_duplicate_group
        self._groups: List = []
        self._selected_id: Optional[str] = None
        self._get_decision_state: Optional[Callable] = None
        self._pool: List[ttk.Frame] = []
        self._thumb_refs: List[object] = []
        self._thumb_cancel = threading.Event()
        self._pending_thumb_token = 0
        self._tm = get_theme_manager()

        self._canvas = tk.Canvas(self, highlightthickness=0, bd=0)
        self._scroll = ttk.Scrollbar(self, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=self._yscroll_set)

        self._inner = ttk.Frame(self._canvas, style="Panel.TFrame")
        self._win = self._canvas.create_window((0, 0), window=self._inner, anchor="nw")

        self._canvas.grid(row=0, column=0, sticky="nsew")
        self._scroll.grid(row=0, column=1, sticky="ns")

        self._canvas.bind("<Configure>", self._on_canvas_configure)
        self._inner.bind("<Configure>", self._on_inner_configure)
        self._canvas.bind("<MouseWheel>", self._on_wheel, add="+")
        self._canvas.bind("<Button-4>", self._on_wheel, add="+")
        self._canvas.bind("<Button-5>", self._on_wheel, add="+")
        self._canvas.bind("<Button-1>", lambda e: self._canvas.focus_set(), add="+")
        self._canvas.configure(takefocus=True)

        self.bind("<Destroy>", self._on_destroy, add="+")

    def _on_destroy(self, _e=None) -> None:
        self._thumb_cancel.set()

    def _yscroll_set(self, first: str, last: str) -> None:
        self._scroll.set(first, last)
        self.after_idle(self._sync_viewport)

    def _on_wheel(self, event) -> None:
        if self._canvas.winfo_height() / max(1, self._inner.winfo_height()) >= 1.0:
            return
        if getattr(event, "delta", 0):
            self._canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
        elif getattr(event, "num", 0) == 4:
            self._canvas.yview_scroll(-1, "units")
        elif getattr(event, "num", 0) == 5:
            self._canvas.yview_scroll(1, "units")
        self.after_idle(self._sync_viewport)
        return "break"

    def _on_canvas_configure(self, _event) -> None:
        self._canvas.itemconfigure(self._win, width=self._canvas.winfo_width())
        self._ensure_pool_size()
        self._sync_viewport()

    def _on_inner_configure(self, event) -> None:
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def set_groups(
        self,
        groups: List,
        selected_id: Optional[str],
        get_decision_state: Callable[[str, bool], str],
    ) -> None:
        self._thumb_cancel.set()
        self._thumb_cancel = threading.Event()
        self._pending_thumb_token += 1
        self._groups = list(groups)
        self._selected_id = selected_id
        self._get_decision_state = get_decision_state
        self._layout_inner_size()
        self._ensure_pool_size()
        self._sync_viewport()

    def _layout_inner_size(self) -> None:
        n = len(self._groups)
        rows = max(1, (n + NCOLS - 1) // NCOLS)
        w = NCOLS * CELL_W
        h = rows * CELL_H
        self._inner.configure(width=w, height=h)
        self._canvas.itemconfigure(self._win, width=w, height=h)
        self.update_idletasks()
        self._canvas.configure(scrollregion=(0, 0, w, h))

    def _ensure_pool_size(self) -> None:
        ch = max(1, self._canvas.winfo_height())
        visible_rows = max(1, int(math.ceil(ch / CELL_H)) + 2)
        need = visible_rows * NCOLS
        while len(self._pool) < need:
            self._pool.append(self._make_cell_shell())

    def _make_cell_shell(self) -> ttk.Frame:
        outer = ttk.Frame(self._inner, style="Panel.TFrame", padding=2)
        return outer

    def _sync_viewport(self) -> None:
        if not self._groups or not self._pool:
            return
        self._ensure_pool_size()
        try:
            y_off = float(self._canvas.canvasy(0))
        except tk.TclError:
            return
        first_row = max(0, int(y_off // CELL_H))
        first_idx = first_row * NCOLS
        ch = max(1, self._canvas.winfo_height())
        visible_rows = max(1, int(math.ceil(ch / CELL_H)) + 2)
        n_slots = visible_rows * NCOLS
        token = self._pending_thumb_token

        for i in range(min(n_slots, len(self._pool))):
            gi = first_idx + i
            slot = self._pool[i]
            if gi >= len(self._groups):
                slot.place_forget()
                continue
            ge = self._groups[gi]
            r, c = divmod(gi, NCOLS)
            slot.place(x=c * CELL_W, y=r * CELL_H, width=CELL_W, height=CELL_H)
            self._fill_cell(slot, ge, token)

    def _fill_cell(self, outer: ttk.Frame, ge, token: int) -> None:
        for w in outer.winfo_children():
            w.destroy()
        gid = ge.group_id
        dg = self._resolve_duplicate_group(gid)
        state = self._get_decision_state(gid, ge.has_risk) if self._get_decision_state else "unresolved"
        sel = gid == self._selected_id
        accent = self._tm.tokens.get("accent_primary", "#58a6ff")
        danger = self._tm.tokens.get("danger", "#f85149")
        warn = self._tm.tokens.get("warning", "#d29922")
        ok = self._tm.tokens.get("success", "#3fb950")
        if sel:
            hl = accent
        elif state == "warning":
            hl = warn
        elif state == "ready":
            hl = ok
        else:
            hl = danger if state == "unresolved" else self._tm.tokens.get("border_soft", "#444")

        wrap = tk.Frame(outer, highlightthickness=2, highlightbackground=hl, highlightcolor=hl)
        wrap.pack(fill="both", expand=True)
        wrap.columnconfigure(0, weight=1)

        img_holder = ttk.Frame(wrap, style="Panel.TFrame", width=THUMB_PX, height=THUMB_PX)
        img_holder.grid(row=0, column=0, pady=(0, 2))
        img_holder.grid_propagate(False)

        title = ge.primary_filename or gid[:12]
        ttk.Label(
            wrap,
            text=truncate_path(title, 22),
            style="Panel.Muted.TLabel",
            font=("Segoe UI", 8),
            wraplength=CELL_W - 8,
        ).grid(row=1, column=0, sticky="w")
        ttk.Label(
            wrap,
            text=f"{_fmt_group_size(ge)} · {_safe_int_for_display(ge, 'file_count', 0)} files",
            style="Panel.Muted.TLabel",
            font=("Segoe UI", 7),
        ).grid(row=2, column=0, sticky="w")

        def _go(_e=None):
            self._on_select(gid)

        for w in (wrap, img_holder):
            w.bind("<Button-1>", _go)

        thumb_path: Optional[str] = None
        if dg and dg.files:
            for f in dg.files:
                if is_image_extension(Path(f.path).suffix.lower().lstrip(".")):
                    thumb_path = f.path
                    break
            if thumb_path is None:
                thumb_path = dg.files[0].path

        ph = ttk.Label(img_holder, text="📄", font=("Segoe UI", 28), anchor="center")
        ph.place(relx=0.5, rely=0.5, anchor="center")

        if thumb_path and is_image_extension(Path(thumb_path).suffix.lower().lstrip(".")):

            def on_done(_fpath: str, cache_path: Optional[Path]):

                def upd():
                    if token != self._pending_thumb_token or self._thumb_cancel.is_set():
                        return
                    if not cache_path or not cache_path.exists():
                        return
                    try:
                        from tkinter import PhotoImage

                        img = PhotoImage(file=str(cache_path))
                        self._thumb_refs.append(img)
                        ph.destroy()
                        lbl = ttk.Label(img_holder, image=img)
                        lbl.image = img
                        lbl.place(relx=0.5, rely=0.5, anchor="center")
                        lbl.bind("<Button-1>", _go)
                    except Exception:
                        pass

                self.after(0, upd)

            generate_thumbnails_async(
                [thumb_path],
                on_done,
                size=(THUMB_PX, THUMB_PX),
                cache_dir=get_cache_dir(),
                max_count=32,
                cancel_event=self._thumb_cancel,
            )
        else:
            ph.bind("<Button-1>", _go)

    def set_selected_id(self, selected_id: Optional[str]) -> None:
        """Update highlight without rebuilding the group list."""
        self._selected_id = selected_id
        self._sync_viewport()

    def scroll_to_group_id(self, group_id: str) -> None:
        idx = next((i for i, g in enumerate(self._groups) if g.group_id == group_id), None)
        if idx is None:
            return
        row = idx // NCOLS
        y = row * CELL_H
        inner_h = max(1, self._inner.winfo_height())
        ch = max(1, self._canvas.winfo_height())
        if inner_h <= ch:
            return
        total = inner_h - ch
        frac = max(0.0, min(1.0, (y - ch * 0.35) / total))
        self._canvas.yview_moveto(frac)
        self.after_idle(self._sync_viewport)
