"""
ReviewWorkspace — mode-specific workspace views for duplicate review.

Provides:
  - ReviewWorkspaceStack: stacked Table / Gallery / Compare views
  - ReviewTableView: dense file metadata table (existing behavior)
  - ReviewGalleryView: thumbnail grid for selected group
  - ReviewCompareView: side-by-side large preview for selected group
"""

from __future__ import annotations

import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import ttk
from typing import Any, Callable, List, Optional

from ...engine.media_types import is_image_extension
from ...engine.models import DuplicateGroup
from ...engine.thumbnails import generate_thumbnails_async, get_cache_dir
from ..utils.formatting import fmt_bytes, truncate_path
from ..utils.icons import IC
from .data_table import DataTable
from .empty_state import EmptyState

_GAP_XS = 4
_GAP_MD = 16


def _thumb_size_for_group(n: int) -> tuple:
    """Adaptive thumbnail size (width, height) based on group size."""
    if n <= 2:
        return (220, 220)
    if n <= 4:
        return (160, 160)
    return (110, 110)


class ReviewTableView(ttk.Frame):
    """Dense file metadata table for duplicate review."""

    def __init__(
        self,
        parent,
        on_keep: Callable[[], None],
        on_select: Optional[Callable[[str], None]] = None,
        on_double_click: Optional[Callable[[str], None]] = None,
        **kwargs,
    ):
        super().__init__(parent, **kwargs)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self._on_keep = on_keep
        self._file_meta: dict[str, Any] = {}
        self._quick_peek_tip: Optional[tk.Toplevel] = None

        self._file_table = DataTable(
            self,
            columns=[
                ("action", "Plan", 128, "w"),
                ("name", "Name", 160, "w"),
                ("path", "Path", 200, "w"),
                ("size", "Size", 70, "e"),
                ("mtime", "Modified", 100, "w"),
                ("type", "Type", 60, "w"),
                ("status", "Status", 60, "w"),
            ],
            height=12,
            on_select=on_select,
            on_double_click=on_double_click,
        )
        self._file_table.grid(row=1, column=0, sticky="nsew")
        self._file_table.tree.bind("<Motion>", self._on_table_hover, add="+")
        self._file_table.tree.bind("<Leave>", lambda e: self._hide_quick_peek(), add="+")

        act = ttk.Frame(self, style="Panel.TFrame")
        act.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        ttk.Button(
            act,
            text=f"{IC.KEEP}  Keep this file",
            style="Ghost.TButton",
            command=on_keep,
        ).pack(side="left", padx=(0, 6))

        self._empty = EmptyState(
            self,
            icon=IC.REVIEW,
            heading="No group selected",
            message="Choose a duplicate group from the left panel.",
        )
        self._empty.grid(row=1, column=0, sticky="nsew")
        self._empty.hide()

    def load_group(
        self,
        group: Optional[DuplicateGroup],
        keep_path: str = "",
    ) -> None:
        if not group:
            self._file_table.clear()
            self._empty.show()
            self._file_table.grid_remove()
            return
        self._empty.hide()
        self._file_table.grid()
        self._file_table.clear()
        for f in group.files:
            self._file_meta[f.path] = f
            is_keep = f.path == keep_path
            action = "Keep this copy" if is_keep else "Delete (duplicate)"
            tag = "safe" if is_keep else "warn"
            modified = datetime.fromtimestamp(getattr(f, "mtime_ns", 0) / 1_000_000_000).strftime("%Y-%m-%d")
            self._file_table.insert_row(
                f.path,
                (
                    action,
                    f.filename,
                    truncate_path(f.path, 40),
                    fmt_bytes(f.size),
                    modified,
                    Path(f.path).suffix or "—",
                    "OK",
                ),
                tags=(tag,),
            )

    def selection(self) -> Optional[str]:
        return self._file_table.selection()

    def _on_table_hover(self, event) -> None:
        iid = self._file_table.tree.identify_row(event.y)
        if not iid:
            self._hide_quick_peek()
            return
        f = self._file_meta.get(iid)
        if not f:
            self._hide_quick_peek()
            return
        self._show_quick_peek(event.x_root + 12, event.y_root + 12, f)

    def _show_quick_peek(self, x: int, y: int, f: Any) -> None:
        text = f"{f.filename}\n{fmt_bytes(f.size)}\n{truncate_path(f.path, 60)}"
        if self._quick_peek_tip is None or not self._quick_peek_tip.winfo_exists():
            tip = tk.Toplevel(self)
            tip.wm_overrideredirect(True)
            lbl = tk.Label(
                tip,
                text=text,
                justify="left",
                background="#1f1f1f",
                foreground="#dfe7ff",
                padx=8,
                pady=6,
                font=("Segoe UI", 8),
            )
            lbl.pack()
            self._quick_peek_tip = tip
        else:
            lbl = self._quick_peek_tip.winfo_children()[0]
            lbl.configure(text=text)
        self._quick_peek_tip.geometry(f"+{x}+{y}")

    def _hide_quick_peek(self) -> None:
        if self._quick_peek_tip is not None and self._quick_peek_tip.winfo_exists():
            self._quick_peek_tip.destroy()
        self._quick_peek_tip = None


_HERO_SIZE = (680, 380)


class ReviewGalleryView(ttk.Frame):
    """Large hero preview for the group + per-file sizes + keep selection."""

    def __init__(
        self,
        parent,
        on_keep: Callable[[str], None],
        **kwargs,
    ):
        super().__init__(parent, **kwargs)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self._on_keep = on_keep
        self._keeper_var = tk.StringVar(value="")
        self._thumb_refs: List[Any] = []
        self._thumb_cancel = threading.Event()
        self.bind("<Destroy>", self._on_destroy, add="+")

        self._canvas = tk.Canvas(self, highlightthickness=0, bd=0)
        self._scroll_v = ttk.Scrollbar(self, orient="vertical", command=self._canvas.yview)
        self._inner = ttk.Frame(self._canvas, style="Panel.TFrame")
        self._canvas.create_window((0, 0), window=self._inner, anchor="nw")
        self._inner.bind("<Configure>", self._on_inner_configure)
        self._canvas.configure(yscrollcommand=self._scroll_v.set)

        self._canvas.grid(row=0, column=0, sticky="nsew")
        self._scroll_v.grid(row=0, column=1, sticky="ns")

        self._empty = EmptyState(
            self,
            icon=IC.REVIEW,
            heading="No group selected",
            message="Choose a duplicate group from the left panel.",
        )
        self._empty.grid(row=0, column=0, sticky="nsew")
        self._empty.hide()

    def _on_inner_configure(self, _event):
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_destroy(self, _event=None):
        self._thumb_cancel.set()

    def load_group(
        self,
        group: Optional[DuplicateGroup],
        keep_path: str = "",
    ) -> None:
        self._thumb_cancel.set()
        self._thumb_cancel = threading.Event()
        self._thumb_refs.clear()
        for w in self._inner.winfo_children():
            w.destroy()

        if not group:
            self._keep_choice_frame = None
            self._empty.show()
            self._canvas.grid_remove()
            self._scroll_v.grid_remove()
            return

        self._empty.hide()
        self._canvas.grid(row=0, column=0, sticky="nsew")
        self._scroll_v.grid(row=0, column=1, sticky="ns")

        files = list(group.files)
        paths = [f.path for f in files]
        default_keep = keep_path if keep_path in paths else (paths[0] if paths else "")
        self._keeper_var.set(default_keep)

        hero_wrap = ttk.Frame(self._inner, style="Panel.TFrame", padding=4)
        hero_wrap.pack(fill="x", pady=(0, _GAP_MD))
        hero_h = min(400, _HERO_SIZE[1])
        hero_box = tk.Frame(hero_wrap, height=hero_h, bg="#1a1a1a")
        hero_box.pack(fill="x")
        hero_box.pack_propagate(False)

        hero_lbl = ttk.Label(hero_box, text="", style="Panel.TLabel", anchor="center")
        hero_lbl.place(relx=0.5, rely=0.5, anchor="center")

        hero_path: Optional[str] = None
        for f in files:
            if is_image_extension(Path(f.path).suffix.lower().lstrip(".")):
                hero_path = f.path
                break
        if hero_path is None and files:
            hero_path = files[0].path

        if hero_path and is_image_extension(Path(hero_path).suffix.lower().lstrip(".")):

            def on_hero(_fpath: str, cache_path: Optional[Path]):
                def upd():
                    if self._thumb_cancel.is_set():
                        return
                    if not cache_path or not cache_path.exists():
                        return
                    try:
                        from tkinter import PhotoImage

                        img = PhotoImage(file=str(cache_path))
                        self._thumb_refs.append(img)
                        hero_lbl.configure(image=img)
                        hero_lbl.image = img
                    except Exception:
                        hero_lbl.configure(text="Preview unavailable", style="Panel.Muted.TLabel")

                self.after(0, upd)

            generate_thumbnails_async(
                [hero_path],
                on_hero,
                size=_HERO_SIZE,
                cache_dir=get_cache_dir(),
                max_count=1,
                cancel_event=self._thumb_cancel,
            )
        else:
            hero_lbl.configure(
                text=f"📄\n{Path(hero_path).name if hero_path else '—'}",
                font=("Segoe UI", 14),
                justify="center",
            )

        sizes_hdr = ttk.Label(self._inner, text="Files in this group", style="Panel.Secondary.TLabel")
        sizes_hdr.pack(anchor="w", pady=(0, _GAP_XS))
        sizes_fr = ttk.Frame(self._inner, style="Panel.TFrame")
        sizes_fr.pack(fill="x", pady=(0, _GAP_MD))
        for f in files:
            line = f"{f.filename}  —  {fmt_bytes(f.size)}"
            ttk.Label(sizes_fr, text=line, style="Panel.Muted.TLabel", font=("Segoe UI", 9)).pack(anchor="w", pady=1)

        keep_hdr = ttk.Label(self._inner, text="Keep one copy", style="Panel.Secondary.TLabel")
        keep_hdr.pack(anchor="w", pady=(0, _GAP_XS))
        keep_fr = ttk.Frame(self._inner, style="Panel.TFrame")
        keep_fr.pack(fill="x")
        self._keep_choice_frame = keep_fr
        for f in files:
            ttk.Radiobutton(
                keep_fr,
                text=f"{f.filename}  ({fmt_bytes(f.size)})",
                value=f.path,
                variable=self._keeper_var,
                command=lambda: self._on_keep(self._keeper_var.get()),
            ).pack(anchor="w", pady=2)

        self._inner.update_idletasks()
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))


class ReviewCompareView(ttk.Frame):
    """Side-by-side large preview for selected duplicate group."""

    def __init__(
        self,
        parent,
        on_keep_left: Callable[[], None],
        on_keep_right: Callable[[], None],
        **kwargs,
    ):
        super().__init__(parent, **kwargs)
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)
        self.rowconfigure(3, weight=0)
        self._on_keep_left = on_keep_left
        self._on_keep_right = on_keep_right
        self._thumb_refs: List[Any] = []
        self._thumb_cancel = threading.Event()
        self._pair_index = 0
        self._left_idx = 0
        self._right_idx = 1
        self._del_left = tk.BooleanVar(value=False)
        self._del_right = tk.BooleanVar(value=False)
        self._syncing_del_checks = False
        self.bind("<Destroy>", self._on_destroy, add="+")

        self.configure(style="Panel.TFrame")

        self._left_frame = ttk.Frame(self, style="Panel.TFrame", padding=8)
        self._right_frame = ttk.Frame(self, style="Panel.TFrame", padding=8)
        self._left_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 4))
        self._right_frame.grid(row=1, column=1, sticky="nsew", padx=(4, 0))

        for f in (self._left_frame, self._right_frame):
            f.columnconfigure(0, weight=1)
            f.rowconfigure(0, weight=1)

        nav = ttk.Frame(self, style="Panel.TFrame")
        nav.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 4))
        nav.columnconfigure(1, weight=1)
        self._prev_btn = ttk.Button(nav, text="◀ Previous", style="Ghost.TButton")
        self._next_btn = ttk.Button(nav, text="Next ▶", style="Ghost.TButton")
        self._prev_btn.grid(row=0, column=0, padx=(0, 8))
        self._next_btn.grid(row=0, column=2, padx=(8, 0))
        self._pair_lbl = ttk.Label(nav, text="", style="Panel.Muted.TLabel")
        self._pair_lbl.grid(row=0, column=1)

        act = ttk.Frame(self, style="Panel.TFrame")
        act.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        act.columnconfigure(0, weight=1)
        ttk.Label(
            act,
            text=(
                "Check Delete on one side to mark that file for removal; the other side stays protected. "
                "This overrides Smart Select for this group. If neither box is checked, the left file is protected."
            ),
            style="Panel.Muted.TLabel",
            wraplength=520,
        ).grid(row=0, column=0, sticky="w")

        # Tier 3: Multi-compare strip (up to 6)
        mc = ttk.Frame(self, style="Panel.TFrame")
        mc.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        mc.columnconfigure(0, weight=1)
        ttk.Label(mc, text="Multi-Compare (up to 6): promote to left/right", style="Panel.Muted.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        self._multi_grid = ttk.Frame(mc, style="Panel.TFrame")
        self._multi_grid.grid(row=1, column=0, sticky="ew", pady=(4, 0))

        self._empty = EmptyState(
            self,
            icon=IC.REVIEW,
            heading="No group selected",
            message="Choose a duplicate group from the left panel.",
        )
        self._empty.grid(row=1, column=0, columnspan=2, sticky="nsew")
        self._empty.hide()

    def _on_destroy(self, _event=None):
        self._thumb_cancel.set()

    def load_group(
        self,
        group: Optional[DuplicateGroup],
        keep_path: str = "",
    ) -> None:
        self._thumb_cancel.set()
        self._thumb_cancel = threading.Event()
        self._thumb_refs.clear()
        for w in self._left_frame.winfo_children():
            w.destroy()
        for w in self._right_frame.winfo_children():
            w.destroy()

        if not group or len(group.files) < 2:
            self._empty.show()
            self._left_frame.grid_remove()
            self._right_frame.grid_remove()
            self._prev_btn.grid_remove()
            self._next_btn.grid_remove()
            return

        self._group = group
        self._keep_path = keep_path
        self._pair_index = 0
        self._left_idx = 0
        self._right_idx = 1
        self._empty.hide()
        self._left_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 4))
        self._right_frame.grid(row=1, column=1, sticky="nsew", padx=(4, 0))

        files = list(group.files)
        n = len(files)
        self._prev_btn.configure(command=self._prev_pair)
        self._next_btn.configure(command=self._next_pair)
        if n > 2:
            self._prev_btn.grid(row=0, column=0, padx=(0, 8))
            self._next_btn.grid(row=0, column=2, padx=(8, 0))
        else:
            self._prev_btn.grid_remove()
            self._next_btn.grid_remove()

        self._render_pair()
        self._render_multi_compare()

    def _prev_pair(self) -> None:
        if not hasattr(self, "_group"):
            return
        n = len(self._group.files)
        if n > 2:
            self._pair_index = (self._pair_index - 1) % (n - 1)
            self._left_idx = self._pair_index
            self._right_idx = self._pair_index + 1
            self._render_pair()

    def _next_pair(self) -> None:
        if not hasattr(self, "_group"):
            return
        n = len(self._group.files)
        if n > 2:
            self._pair_index = (self._pair_index + 1) % (n - 1)
            self._left_idx = self._pair_index
            self._right_idx = self._pair_index + 1
            self._render_pair()

    def _render_pair(self) -> None:
        if not hasattr(self, "_group"):
            return
        files = list(self._group.files)
        n = len(files)
        if n < 2:
            return
        if n == 2:
            left_f, right_f = files[0], files[1]
            self._left_idx, self._right_idx = 0, 1
        else:
            li = max(0, min(self._left_idx, n - 1))
            ri = max(0, min(self._right_idx, n - 1))
            if li == ri:
                ri = min(n - 1, li + 1)
            left_f, right_f = files[li], files[ri]
            self._left_idx, self._right_idx = li, ri
        self._pair_lbl.configure(text=f"Comparing {self._left_idx + 1} vs {self._right_idx + 1}")

        def add_preview(frame: ttk.Frame, f, side: str):
            for w in frame.winfo_children():
                w.destroy()
            size = (320, 320)
            ttk.Label(
                frame, text=f.filename, style="Panel.Secondary.TLabel", font=("Segoe UI", 9), wraplength=300
            ).grid(row=0, column=0)
            ext = Path(f.path).suffix.lower().lstrip(".")
            if is_image_extension(ext):

                def on_thumb(_p, thumb_path):
                    def upd():
                        if thumb_path and thumb_path.exists():
                            try:
                                from tkinter import PhotoImage

                                img = PhotoImage(file=str(thumb_path))
                                self._thumb_refs.append(img)
                                lbl = ttk.Label(frame, image=img, style="Panel.TLabel")
                                lbl.image = img
                                lbl.grid(row=1, column=0)
                            except Exception:
                                ttk.Label(frame, text="[preview]", style="Panel.Muted.TLabel").grid(row=1, column=0)
                        else:
                            ttk.Label(frame, text="[no preview]", style="Panel.Muted.TLabel").grid(row=1, column=0)

                    if not self._thumb_cancel.is_set():
                        self.after(0, upd)

                generate_thumbnails_async(
                    [f.path],
                    on_thumb,
                    size=size,
                    cache_dir=get_cache_dir(),
                    max_count=1,
                    cancel_event=self._thumb_cancel,
                )
            else:
                ttk.Label(frame, text="📄 " + ext.upper(), style="Panel.Muted.TLabel", font=("Segoe UI", 14)).grid(
                    row=1, column=0
                )
            ttk.Label(frame, text=f"{fmt_bytes(f.size)}", style="Panel.Muted.TLabel", font=("Segoe UI", 8)).grid(
                row=2, column=0
            )
            ttk.Label(
                frame, text=truncate_path(f.path, 50), style="Panel.Muted.TLabel", font=("Segoe UI", 7), wraplength=300
            ).grid(row=3, column=0)
            var = self._del_left if side == "left" else self._del_right
            chk = ttk.Frame(frame, style="Panel.TFrame")
            chk.grid(row=4, column=0, sticky="ew", pady=(8, 0))
            ttk.Checkbutton(
                chk,
                text="Delete this copy (Trash later; other preview is kept)",
                variable=var,
                command=self._on_compare_delete_toggle,
            ).pack(anchor="w")

        add_preview(self._left_frame, left_f, "left")
        add_preview(self._right_frame, right_f, "right")
        self._sync_del_checks_from_keep(left_f, right_f)

    def _on_compare_delete_toggle(self) -> None:
        if self._syncing_del_checks:
            return
        if self._del_left.get() and self._del_right.get():
            self._syncing_del_checks = True
            self._del_right.set(False)
            self._syncing_del_checks = False
        elif self._del_left.get():
            self._syncing_del_checks = True
            self._del_right.set(False)
            self._syncing_del_checks = False
        elif self._del_right.get():
            self._syncing_del_checks = True
            self._del_left.set(False)
            self._syncing_del_checks = False
        self._apply_compare_keep_from_checks()

    def _apply_compare_keep_from_checks(self) -> None:
        if not hasattr(self, "_group"):
            return
        if self._del_left.get():
            self._on_keep_right()
        elif self._del_right.get():
            self._on_keep_left()
        else:
            self._on_keep_left()

    def _sync_del_checks_from_keep(self, left_f, right_f) -> None:
        self._syncing_del_checks = True
        try:
            k = (self._keep_path or "").strip()
            if k == left_f.path:
                self._del_left.set(False)
                self._del_right.set(True)
            elif k == right_f.path:
                self._del_left.set(True)
                self._del_right.set(False)
            else:
                self._del_left.set(False)
                self._del_right.set(True)
        finally:
            self._syncing_del_checks = False

    def _render_multi_compare(self) -> None:
        for w in self._multi_grid.winfo_children():
            w.destroy()
        if not hasattr(self, "_group"):
            return
        files = list(self._group.files)[:6]
        for idx, f in enumerate(files):
            card = ttk.Frame(self._multi_grid, style="Panel.TFrame", padding=4)
            card.grid(row=0, column=idx, padx=4, sticky="nw")
            ttk.Label(card, text=f.filename[:14], style="Panel.Muted.TLabel").grid(row=0, column=0, columnspan=2)
            ttk.Label(card, text=fmt_bytes(f.size), style="Panel.Muted.TLabel").grid(row=1, column=0, columnspan=2)
            ttk.Button(card, text="Set Left", style="Ghost.TButton", command=lambda i=idx: self._promote_left(i)).grid(
                row=2, column=0, padx=(0, 2)
            )
            ttk.Button(
                card, text="Set Right", style="Ghost.TButton", command=lambda i=idx: self._promote_right(i)
            ).grid(row=2, column=1, padx=(2, 0))

    def _promote_left(self, idx: int) -> None:
        self._left_idx = idx
        if self._right_idx == idx:
            self._right_idx = min(idx + 1, len(self._group.files) - 1)
        self._render_pair()

    def _promote_right(self, idx: int) -> None:
        self._right_idx = idx
        if self._left_idx == idx:
            self._left_idx = max(0, idx - 1)
        self._render_pair()


class ReviewWorkspaceStack(ttk.Frame):
    """Stacked workspace: Table | Gallery | Compare. Mode switch swaps visible view."""

    def __init__(
        self,
        parent,
        on_keep: Callable[[str], None],
        on_clear_keep: Optional[Callable[[], None]] = None,
        **kwargs,
    ):
        super().__init__(parent, **kwargs)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self._on_keep = on_keep
        self._on_clear_keep = on_clear_keep or (lambda: None)

        # Toolbar: Clear selection (shown when a group has a keep choice)
        self._clear_toolbar = ttk.Frame(self, style="Panel.TFrame")
        self._clear_btn = ttk.Button(
            self._clear_toolbar,
            text=f"{IC.REMOVE}  Clear selection",
            style="Ghost.TButton",
            command=self._on_clear_keep,
        )
        self._clear_btn.pack(side="left", padx=(0, 6))
        self._quick_cmp_btn = ttk.Button(
            self._clear_toolbar,
            text="Compare Icon",
            style="Ghost.TButton",
            command=self.open_quick_compare_overlay,
        )
        self._quick_cmp_btn.pack(side="left", padx=(0, 6))
        self._clear_toolbar.grid(row=0, column=0, sticky="w", pady=(0, 4))
        self._clear_toolbar.grid_remove()
        self._clear_toolbar_visible = False

        def _table_keep():
            sel = self._table.selection()
            if sel:
                on_keep(sel)

        self._table = ReviewTableView(self, on_keep=_table_keep)
        self._gallery = ReviewGalleryView(self, on_keep=on_keep)
        self._compare = ReviewCompareView(
            self,
            on_keep_left=lambda: self._keep_compare(0),
            on_keep_right=lambda: self._keep_compare(1),
        )

        self._views = [self._table, self._gallery, self._compare]
        for v in self._views:
            v.grid(row=1, column=0, sticky="nsew")
        self._current = 0
        self._show_index(0)

    def _keep_compare(self, idx: int) -> None:
        if not hasattr(self._compare, "_group"):
            return
        files = list(self._compare._group.files)
        n = len(files)
        if n < 2:
            return
        if n == 2:
            path = files[idx].path
        else:
            li = max(0, min(getattr(self._compare, "_left_idx", 0), n - 1))
            ri = max(0, min(getattr(self._compare, "_right_idx", 1), n - 1))
            path = files[li].path if idx == 0 else files[ri].path
        self._on_keep(path)

    def set_mode(self, mode: str) -> None:
        idx = {"table": 0, "gallery": 1, "compare": 2}.get(mode, 0)
        self._show_index(idx)

    def compare_next(self) -> None:
        self._compare._next_pair()

    def compare_prev(self) -> None:
        self._compare._prev_pair()

    def open_quick_compare_overlay(self) -> None:
        """Tier 1 quick compare overlay without switching workspace mode."""
        if not hasattr(self._compare, "_group"):
            return
        files = list(self._compare._group.files)
        if len(files) < 2:
            return
        li = max(0, min(getattr(self._compare, "_left_idx", 0), len(files) - 1))
        ri = max(0, min(getattr(self._compare, "_right_idx", 1), len(files) - 1))
        left = files[li]
        right = files[ri]
        top = tk.Toplevel(self)
        top.title("Quick Compare")
        top.transient(self.winfo_toplevel())
        top.geometry("680x300")
        wrap = ttk.Frame(top, padding=10)
        wrap.pack(fill="both", expand=True)
        wrap.columnconfigure(0, weight=1)
        wrap.columnconfigure(1, weight=1)
        for col, f in enumerate((left, right)):
            pane = ttk.Frame(wrap, style="Panel.TFrame", padding=8)
            pane.grid(row=0, column=col, sticky="nsew", padx=4)
            ttk.Label(pane, text=f.filename, style="Panel.Secondary.TLabel", wraplength=280).pack(anchor="w")
            ttk.Label(pane, text=fmt_bytes(f.size), style="Panel.Muted.TLabel").pack(anchor="w")
            ttk.Label(pane, text=truncate_path(f.path, 70), style="Panel.Muted.TLabel", wraplength=280).pack(anchor="w")
        ttk.Button(wrap, text="Close", style="Ghost.TButton", command=top.destroy).grid(
            row=1, column=0, columnspan=2, sticky="e", pady=(8, 0)
        )

    def _show_index(self, idx: int) -> None:
        self._views[self._current].grid_remove()
        self._current = idx
        self._views[self._current].grid(row=1, column=0, sticky="nsew")

    def load_group(
        self,
        group: Optional[DuplicateGroup],
        keep_path: str = "",
        mode: str = "table",
    ) -> None:
        for v in self._views:
            v.load_group(group, keep_path)
        idx = {"table": 0, "gallery": 1, "compare": 2}.get(mode, 0)
        self._show_index(idx)
        # Show Clear selection when group has a keep choice
        self._clear_toolbar_visible = bool(group and keep_path)
        if self._clear_toolbar_visible:
            self._clear_toolbar.grid(row=0, column=0, sticky="w", pady=(0, 4))
        else:
            self._clear_toolbar.grid_remove()

    @property
    def table_view(self) -> ReviewTableView:
        return self._table
