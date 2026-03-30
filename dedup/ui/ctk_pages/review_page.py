"""
CustomTkinter Review page (experimental).

Three-column layout:
- left: scrollable groups grid (text only, no thumbnails)
- center: one container with large side-by-side duplicate comparison (resizes with window)
- right: keep + compare selectors and actions, stretched to match column height
Execution summary sits below the three columns (full width).
"""

from __future__ import annotations

import tkinter
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional

import customtkinter as ctk

from ...engine.media_types import is_image_extension
from ...engine.models import DeletionResult, ScanResult
from ...engine.thumbnails import get_thumbnail_path
from ..state.store import ReviewIndexState, ReviewPlanState, ReviewPreviewState, ReviewSelectionState
from ..utils.formatting import fmt_bytes
from ..utils.review_keep import coerce_keep_selections, default_keep_map_from_result
from ..utils.theme_helpers import theme_pair
from .design_tokens import get_theme_colors, resolve_border_token

if TYPE_CHECKING:
    from ..controller.review_controller import ReviewController
    from ..state.store import UIStateStore

_COMPARE_EMPTY = "—"


class ReviewPageCTK(ctk.CTkFrame):
    """CTK review page: groups | comparison | actions."""

    _HERO_MIN = 280
    _HERO_MAX = 900

    def _ui_alive(self) -> bool:
        """False after destroy — avoids configuring heroes from stale callbacks."""
        try:
            return bool(self.winfo_exists())
        except (tkinter.TclError, RuntimeError):
            return False

    def __init__(
        self,
        parent,
        *,
        on_execute: Optional[Callable[[dict[str, str]], DeletionResult | None]] = None,
        store: Optional["UIStateStore"] = None,
        **kwargs,
    ) -> None:
        super().__init__(parent, **kwargs)
        self._on_execute = on_execute
        self._store = store
        self._review_controller: Optional["ReviewController"] = None
        self._result: ScanResult | None = None
        self._group_map: dict[str, object] = {}
        self._keep_map: dict[str, str] = {}
        self._group_var = ctk.StringVar(value="")
        self._keep_var = ctk.StringVar(value="")
        self._compare_var = ctk.StringVar(value="")
        self._refresh_callback: Callable[[], None] = lambda: None
        self._compare_path: str | None = None
        self._ctk_image_refs: list[ctk.CTkImage] = []
        self._hero_pixel_size = 480
        self._resize_after_id: str | None = None
        self._group_row_frames: dict[str, ctk.CTkFrame] = {}
        self._keep_label_to_path: dict[str, str] = {}
        self._compare_label_to_path: dict[str, str] = {}
        self._tokens = get_theme_colors()

        self.grid_columnconfigure(0, weight=0, minsize=200)
        self.grid_columnconfigure(1, weight=1, minsize=360)
        self.grid_columnconfigure(2, weight=0, minsize=280)
        self.grid_rowconfigure(1, weight=3)
        self.grid_rowconfigure(3, weight=1)
        self._build()

    def _build(self) -> None:
        tk = self._tokens
        top = ctk.CTkFrame(
            self,
            corner_radius=16,
            fg_color=tk["bg_panel"],
            border_width=1,
            border_color=tk["border_subtle"],
        )
        top.grid(row=0, column=0, columnspan=3, sticky="ew", padx=20, pady=(20, 12))
        top.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            top,
            text="📊  Review",
            font=ctk.CTkFont(size=26, weight="bold"),
            text_color=tk["text_primary"],
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(14, 4))
        self._summary_var = ctk.StringVar(value="No scan loaded")
        ctk.CTkLabel(top, textvariable=self._summary_var, text_color=tk["text_secondary"]).grid(
            row=1, column=0, sticky="w", padx=16, pady=(0, 12)
        )

        # --- Column 0: groups (text grid) ---
        self._review_left = ctk.CTkFrame(
            self,
            corner_radius=16,
            width=220,
            fg_color=tk["bg_panel"],
            border_width=1,
            border_color=tk["border_subtle"],
        )
        left = self._review_left
        left.grid(row=1, column=0, sticky="nsew", padx=(20, 8), pady=(0, 12))
        left.grid_rowconfigure(1, weight=1)
        left.grid_propagate(False)
        ctk.CTkLabel(left, text="Groups", font=ctk.CTkFont(size=16, weight="bold"), text_color=tk["text_primary"]).grid(
            row=0, column=0, sticky="w", padx=12, pady=(12, 8)
        )
        self._group_scroll = ctk.CTkScrollableFrame(left, fg_color="transparent")
        self._group_scroll.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 12))

        # --- Column 1: comparison container only ---
        self._review_center = ctk.CTkFrame(
            self,
            corner_radius=16,
            fg_color=tk["bg_panel"],
            border_width=1,
            border_color=tk["border_subtle"],
        )
        center = self._review_center
        center.grid(row=1, column=1, sticky="nsew", padx=8, pady=(0, 12))
        center.grid_columnconfigure(0, weight=1)
        center.grid_columnconfigure(1, weight=1)
        center.grid_rowconfigure(1, weight=1)

        self._preview_title = ctk.CTkLabel(
            center,
            text="File preview",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=tk["text_primary"],
        )
        self._preview_title.grid(row=0, column=0, columnspan=2, pady=(14, 10))

        self._hero_viewport = ctk.CTkFrame(center, fg_color="transparent")
        self._hero_viewport.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=8, pady=4)
        self._hero_viewport.grid_columnconfigure(0, weight=1)
        self._hero_viewport.grid_columnconfigure(1, weight=1)
        self._hero_viewport.grid_rowconfigure(0, weight=1)
        self._hero_viewport.bind("<Configure>", self._on_hero_viewport_configure)

        self._hero_left_label = ctk.CTkLabel(self._hero_viewport, text="Keep preview")
        self._hero_left_label.grid(row=0, column=0, padx=12, pady=8, sticky="nsew")
        self._hero_left_caption = ctk.StringVar(value="")
        ctk.CTkLabel(center, textvariable=self._hero_left_caption, text_color=tk["text_secondary"]).grid(
            row=2, column=0, padx=16, pady=(6, 14)
        )

        self._hero_right_label = ctk.CTkLabel(self._hero_viewport, text="Compare preview")
        self._hero_right_label.grid(row=0, column=1, padx=12, pady=8, sticky="nsew")
        self._hero_right_caption = ctk.StringVar(value="")
        ctk.CTkLabel(center, textvariable=self._hero_right_caption, text_color=tk["text_secondary"]).grid(
            row=2, column=1, padx=16, pady=(6, 14)
        )

        # --- Column 2: actions (top-aligned content + vertical stretch) ---
        self._review_right = ctk.CTkFrame(
            self,
            corner_radius=16,
            width=300,
            fg_color=tk["bg_panel"],
            border_width=1,
            border_color=tk["border_subtle"],
        )
        right = self._review_right
        right.grid(row=1, column=2, sticky="nsew", padx=(8, 20), pady=(0, 12))
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(5, weight=1)

        ctk.CTkLabel(right, text="Keep file", text_color=tk["text_secondary"]).grid(
            row=0, column=0, sticky="w", padx=16, pady=(16, 6)
        )
        self._keep_menu = ctk.CTkOptionMenu(right, variable=self._keep_var, values=[""], command=self._on_keep_change)
        self._keep_menu.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 10))

        ctk.CTkLabel(right, text="Compare file", text_color=tk["text_secondary"]).grid(
            row=2, column=0, sticky="w", padx=16, pady=(4, 6)
        )
        self._compare_menu = ctk.CTkOptionMenu(
            right,
            variable=self._compare_var,
            values=[_COMPARE_EMPTY],
            command=self._on_compare_menu_change,
        )
        self._compare_menu.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 14))

        row = ctk.CTkFrame(right, fg_color="transparent")
        row.grid(row=4, column=0, sticky="ew", padx=16, pady=(0, 12))
        danger = tk["danger"]
        danger_hover = tk["danger_hover"]
        self._execute_btn = ctk.CTkButton(
            row,
            text="🗑️ Move to Trash",
            fg_color=danger,
            hover_color=danger_hover,
            text_color=("#FFFFFF", "#0A0E14"),
            command=self._execute,
        )
        self._execute_btn.pack(side="left", padx=(0, 8))
        self._refresh_btn = ctk.CTkButton(
            row,
            text="Refresh Last Scan",
            fg_color=tk["bg_elevated"],
            hover_color=tk["bg_overlay"],
            text_color=tk["text_secondary"],
            border_width=1,
            border_color=tk["border_subtle"],
            command=self._refresh_callback,
        )
        self._refresh_btn.pack(side="left")

        ctk.CTkFrame(right, fg_color="transparent").grid(row=5, column=0, sticky="nsew")

        self._result_panel = ctk.CTkFrame(
            self,
            corner_radius=16,
            fg_color=tk["bg_panel"],
            border_width=1,
            border_color=tk["border_subtle"],
        )
        self._result_panel.grid_columnconfigure(0, weight=1)
        self._result_var = ctk.StringVar(value="")
        ctk.CTkLabel(
            self._result_panel,
            text="Execution Result",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=tk["text_primary"],
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(12, 6))
        ctk.CTkLabel(self._result_panel, textvariable=self._result_var, text_color=tk["text_secondary"]).grid(
            row=1, column=0, sticky="w", padx=16, pady=(0, 12)
        )

        self._details = ctk.CTkTextbox(
            self,
            wrap="word",
            corner_radius=12,
            fg_color=tk["bg_surface"],
            text_color=tk["text_secondary"],
            border_width=1,
            border_color=tk["border_subtle"],
        )
        self._details.grid(row=3, column=0, columnspan=3, sticky="nsew", padx=20, pady=(0, 20))
        self._details.insert("end", "Load a scan result to review duplicate groups.\n")
        self._details.configure(state="disabled")

        self._review_empty = ctk.CTkFrame(
            self,
            corner_radius=16,
            fg_color=tk["bg_panel"],
            border_width=1,
            border_color=tk["border_subtle"],
        )
        self._review_empty.grid_columnconfigure(0, weight=1)
        self._review_empty.grid_rowconfigure(0, weight=1)
        empty_inner = ctk.CTkFrame(self._review_empty, fg_color="transparent")
        empty_inner.grid(row=0, column=0, sticky="nsew", padx=40, pady=48)
        ctk.CTkLabel(
            empty_inner,
            text="📭",
            font=ctk.CTkFont(size=48),
        ).pack(pady=(0, 12))
        ctk.CTkLabel(
            empty_inner,
            text="No scan to review",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=tk["text_primary"],
        ).pack()
        ctk.CTkLabel(
            empty_inner,
            text="Run a scan from Home or Scan, open a result from History,\nor refresh if you already completed a scan in this session.",
            font=ctk.CTkFont(size=14),
            text_color=tk["text_secondary"],
            wraplength=520,
            justify="center",
        ).pack(pady=(12, 0))

        self._themed_sections = [top, left, center, right, self._result_panel, self._review_empty]
        self._layout_review_empty(True)
        self._group_row_normal = "transparent"
        self._group_row_hover = self._tokens["bg_overlay"]
        self._group_row_selected = self._tokens["bg_elevated"]
        self._result_panel.grid_remove()

    def _layout_review_empty(self, show: bool) -> None:
        """Toggle full-page empty state vs the three-column review layout."""
        if not hasattr(self, "_review_empty"):
            return
        if show:
            self._review_left.grid_remove()
            self._review_center.grid_remove()
            self._review_right.grid_remove()
            self._review_empty.grid(row=1, column=0, columnspan=3, sticky="nsew", padx=20, pady=(0, 12))
        else:
            self._review_empty.grid_remove()
            self._review_left.grid(row=1, column=0, sticky="nsew", padx=(20, 8), pady=(0, 12))
            self._review_center.grid(row=1, column=1, sticky="nsew", padx=8, pady=(0, 12))
            self._review_right.grid(row=1, column=2, sticky="nsew", padx=(8, 20), pady=(0, 12))

    def apply_theme_tokens(self, tokens: dict) -> None:
        panel = str(tokens.get("bg_panel", "#161b22"))
        base = str(tokens.get("bg_base", "#0f131c"))
        surf = str(tokens.get("bg_surface", str(tokens.get("bg_elevated", "#21262d"))))
        self.configure(fg_color=panel)
        if hasattr(self, "_scroll"):
            self._scroll.configure(fg_color=surf, label_fg_color=base)
        elev = str(tokens.get("bg_elevated", "#21262d"))
        br = resolve_border_token(tokens)
        txt = str(tokens.get("text_secondary", "#94A3B8"))
        for f in self._themed_sections:
            f.configure(fg_color=panel, border_color=br)
        self._execute_btn.configure(
            fg_color=str(tokens.get("danger", "#E53E3E")),
            hover_color=str(tokens.get("danger_hover", "#9B2C2C")),
        )
        if hasattr(self, "_preview_title"):
            self._preview_title.configure(text_color=str(tokens.get("text_primary", "#F1F5F9")))
        self._refresh_btn.configure(fg_color=elev, border_color=br)
        self._details.configure(fg_color=surf, text_color=txt, border_color=br)

        self._group_row_hover = theme_pair(tokens.get("bg_overlay"), self._tokens["bg_overlay"])
        self._group_row_selected = theme_pair(tokens.get("bg_elevated"), self._tokens["bg_elevated"])
        cur = self._group_var.get()
        if cur and self._group_row_frames:
            self._highlight_group_row(cur)

        # Update all text labels with live token colors
        self._update_label_colors(self, tokens)

    def _update_label_colors(self, widget, tokens: dict) -> None:
        """Recursively update all label text colors in widget tree with live tokens."""
        txt_primary = str(tokens.get("text_primary", "#F1F5F9"))
        txt_secondary = str(tokens.get("text_secondary", "#94A3B8"))
        txt_muted = str(tokens.get("text_muted", "#6B7280"))
        acc = str(tokens.get("accent_primary", "#E53E3E"))

        try:
            for child in widget.winfo_children():
                if child.__class__.__name__ == "CTkLabel":
                    try:
                        current_color = child.cget("text_color")
                        if current_color and isinstance(current_color, tuple) and len(current_color) == 2:
                            child.configure(text_color=(txt_primary, "#0A0E14"))
                        elif "accent" in str(current_color).lower():
                            child.configure(text_color=acc)
                        elif "muted" in str(current_color).lower():
                            child.configure(text_color=txt_muted)
                        elif "secondary" in str(current_color).lower():
                            child.configure(text_color=txt_secondary)
                        elif current_color:
                            child.configure(text_color=txt_primary)
                    except Exception:
                        pass
                elif child.__class__.__name__ in ("CTkFrame", "CTkScrollableFrame"):
                    self._update_label_colors(child, tokens)
        except Exception:
            pass

    def set_refresh_callback(self, callback: Callable[[], ScanResult | None]) -> None:
        self._refresh_callback = lambda: self.load_result(callback())

    def set_review_controller(self, ctrl: "ReviewController") -> None:
        self._review_controller = ctrl

    # --- IReviewCallbacks (ReviewController) ---
    def get_current_result(self) -> Any:
        return self._result

    def set_preview_result(self, msg: str) -> None:
        self._result_var.set(msg)

    def refresh_review_ui(self) -> None:
        if not self._store or not self._result:
            return
        from ..state.selectors import review_selection

        sel = review_selection(self._store.state)
        if not sel:
            return
        raw = dict(getattr(sel, "keep_selections", None) or {})
        if raw:
            self._keep_map.update(coerce_keep_selections(self._result, raw))
        cur = self._group_var.get()
        if cur and cur in self._group_map:
            self._rebuild_keep_menu(cur)
            self._sync_compare_default(cur)
            self._rebuild_compare_menu(cur)
            self._render_group_details(cur)
            self._refresh_heroes()

    def _ctk_confirm(self, title: str, message: str) -> bool:
        """Themed confirmation (matches CTK chrome; avoids native messagebox on dark UI)."""
        tk = self._tokens
        bg = tk["bg_base"]
        txt = tk["text_primary"]
        muted = tk["text_secondary"]
        danger = tk["danger"]
        danger_hover = tk["danger_hover"]
        root = self.winfo_toplevel()
        out: list[bool] = [False]

        dlg = ctk.CTkToplevel(root)
        dlg.title(title)
        dlg.geometry("440x260")
        dlg.configure(fg_color=bg)
        dlg.transient(root)
        dlg.grab_set()

        ctk.CTkLabel(
            dlg,
            text=title,
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=txt,
        ).pack(pady=(16, 8))
        ctk.CTkLabel(
            dlg,
            text=message,
            wraplength=400,
            justify="left",
            font=ctk.CTkFont(size=13),
            text_color=muted,
        ).pack(padx=20, pady=(0, 16))

        row = ctk.CTkFrame(dlg, fg_color="transparent")
        row.pack(pady=(0, 16))
        ctk.CTkButton(
            row,
            text="Cancel",
            width=120,
            fg_color=tk["bg_elevated"],
            hover_color=tk["bg_overlay"],
            text_color=muted,
            command=dlg.destroy,
        ).pack(side="left", padx=8)
        ctk.CTkButton(
            row,
            text="Move to Trash",
            width=140,
            fg_color=danger,
            hover_color=danger_hover,
            text_color=("#FFFFFF", "#0A0E14"),
            command=lambda: (out.__setitem__(0, True), dlg.destroy()),
        ).pack(side="left", padx=8)

        dlg.protocol("WM_DELETE_WINDOW", dlg.destroy)
        try:
            dlg.focus_force()
        except (tkinter.TclError, RuntimeError):
            pass
        dlg.wait_window()
        return out[0]

    def _show_result_panel(self) -> None:
        """Show execution summary after a delete run (hidden until first outcome)."""
        if hasattr(self, "_result_panel"):
            self._result_panel.grid(row=2, column=0, columnspan=3, sticky="ew", padx=20, pady=(0, 12))

    def confirm_deletion(self, plan: Any, prev: dict) -> str:
        n = prev.get("total_files", "?")
        sz = prev.get("human_readable_size", "?")
        msg = (
            f"Move {n} duplicate file(s) to Trash?\n\n"
            f"Total size: ~{sz}\n\n"
            "Files can be restored from the Recycle Bin or Trash until you empty it."
        )
        if not self._ctk_confirm("Move to Trash", msg):
            return "cancel"
        return "proceed"

    def on_execute_start(self) -> None:
        self._execute_btn.configure(state="disabled", text="Working…")
        self.update_idletasks()

    def on_execute_done(self, result: DeletionResult) -> None:
        self._execute_btn.configure(state="normal", text="🗑️ Move to Trash")
        self._show_result_panel()
        self._result_var.set(
            f"Deleted {len(result.deleted_files)} · Failed {len(result.failed_files)} · Reclaimed {fmt_bytes(result.bytes_reclaimed)}"
        )
        self._set_details(
            f"Deleted: {len(result.deleted_files)} files\n"
            f"Failed: {len(result.failed_files)} files\n"
            f"Reclaimed: {fmt_bytes(result.bytes_reclaimed)}"
        )

    def get_loaded_result(self) -> ScanResult | None:
        """Result currently shown in Review (e.g. opened from History), not only coordinator memory."""
        return self._result

    @staticmethod
    def _menu_labels_for_paths(paths: list[str]) -> tuple[list[str], dict[str, str]]:
        """
        Build short OptionMenu labels (basename) and label -> absolute path.
        Same basename in one group becomes name, name (#2), etc.
        """
        labels: list[str] = []
        label_to_path: dict[str, str] = {}
        per_name: dict[str, int] = {}
        for p in paths:
            name = Path(p).name
            per_name[name] = per_name.get(name, 0) + 1
            n = per_name[name]
            label = name if n == 1 else f"{name}  (#{n})"
            while label in label_to_path:
                n += 1
                label = f"{name}  (#{n})"
            labels.append(label)
            label_to_path[label] = p
        return labels, label_to_path

    def _label_for_path(self, path: str | None, mapping: dict[str, str]) -> str | None:
        if not path:
            return None
        for lbl, p in mapping.items():
            if p == path:
                return lbl
        return None

    def _resolve_keep_path(self, menu_value: str) -> str:
        if not menu_value:
            return ""
        return self._keep_label_to_path.get(menu_value, menu_value)

    def _resolve_compare_path(self, menu_value: str) -> str | None:
        if menu_value in ("", _COMPARE_EMPTY):
            return None
        return self._compare_label_to_path.get(menu_value, menu_value)

    def _on_hero_viewport_configure(self, event: tkinter.Event) -> None:
        if event.widget != self._hero_viewport:
            return
        if self._resize_after_id is not None:
            self.after_cancel(self._resize_after_id)
        self._resize_after_id = self.after(100, self._apply_hero_resize)

    def _apply_hero_resize(self) -> None:
        self._resize_after_id = None
        if not self._ui_alive():
            return
        try:
            w = int(self._hero_viewport.winfo_width())
            h = int(self._hero_viewport.winfo_height())
        except (tkinter.TclError, ValueError, TypeError, OSError):
            return
        if w < 80 or h < 80:
            return
        per_col = max(60, (w - 48) // 2)
        side = min(self._HERO_MAX, max(self._HERO_MIN, min(per_col, h - 16)))
        if abs(side - self._hero_pixel_size) >= 24:
            self._hero_pixel_size = side
            self._refresh_heroes()

    def load_result(self, result: ScanResult | None) -> None:
        self._result = result
        if hasattr(self, "_result_panel"):
            self._result_panel.grid_remove()
        if not result or not result.duplicate_groups:
            self._layout_review_empty(True)
            self._summary_var.set("No duplicate groups available")
            self._group_map = {}
            self._keep_map = {}
            self._group_var.set("")
            self._clear_group_rows()
            self._keep_menu.configure(values=[""])
            self._keep_var.set("")
            self._keep_label_to_path.clear()
            self._compare_label_to_path.clear()
            self._compare_menu.configure(values=[_COMPARE_EMPTY])
            self._compare_var.set(_COMPARE_EMPTY)
            self._clear_compare_ui()
            self._set_details("No duplicate groups in last scan.")
            if hasattr(self, "_preview_title"):
                self._preview_title.configure(text="File preview")
            return
        self._group_map = {
            str(g.group_id): g for g in result.duplicate_groups if len(getattr(g, "files", []) or []) >= 2
        }
        if not self._group_map:
            self._layout_review_empty(False)
            reclaim = int(getattr(result, "total_reclaimable_bytes", 0) or 0)
            self._summary_var.set(
                f"No duplicate groups of 2+ files · {fmt_bytes(reclaim)} reclaimable (scan result)"
                if reclaim
                else "No duplicate groups of 2+ files in this scan"
            )
            self._keep_map = {}
            self._group_var.set("")
            self._clear_group_rows()
            self._show_no_duplicates_empty()
            self._keep_menu.configure(values=[""])
            self._keep_var.set("")
            self._keep_label_to_path.clear()
            self._compare_label_to_path.clear()
            self._compare_menu.configure(values=[_COMPARE_EMPTY])
            self._compare_var.set(_COMPARE_EMPTY)
            self._clear_compare_ui()
            self._set_details("No groups with at least two files to compare.")
            if hasattr(self, "_preview_title"):
                self._preview_title.configure(text="File preview")
            if self._store:
                self._store.set_review_selection(ReviewSelectionState(keep_selections={}, selected_group_id=None))
            self._push_review_slices_to_store()
            return
        self._layout_review_empty(False)
        self._keep_map = {gid: self._default_keep_for_group(self._group_map[gid]) for gid in self._group_map}
        if self._store:
            km = default_keep_map_from_result(result)
            km = coerce_keep_selections(result, km)
            gids = list(self._group_map.keys())
            self._store.set_review_selection(
                ReviewSelectionState(keep_selections=km, selected_group_id=gids[0] if gids else None)
            )
        total_groups = len(self._group_map)
        self._summary_var.set(
            f"{total_groups:,} groups · {fmt_bytes(getattr(result, 'total_reclaimable_bytes', 0) or 0)} reclaimable"
        )
        gids = list(self._group_map.keys())
        self._group_var.set(gids[0])
        self._rebuild_group_rows(gids)
        self._select_group(gids[0])
        self.after_idle(self._apply_hero_resize)
        self._bind_review_shortcuts()
        self._push_review_slices_to_store()

    def apply_default_policy(self, policy: str) -> None:
        if not self._group_map:
            return
        for gid, group in self._group_map.items():
            keep = self._pick_by_policy(group, policy)
            if keep:
                self._keep_map[gid] = keep
        cur = self._group_var.get()
        if cur:
            self._rebuild_keep_menu(cur)
            self._sync_compare_default(cur)
            self._rebuild_compare_menu(cur)
            self._render_group_details(cur)
            self._refresh_heroes()

    def _clear_group_rows(self) -> None:
        for w in self._group_scroll.winfo_children():
            w.destroy()
        self._group_row_frames.clear()

    def _show_no_duplicates_empty(self) -> None:
        """In-list empty state when a result is loaded but no 2+ file groups exist."""
        empty = ctk.CTkFrame(self._group_scroll, fg_color="transparent")
        empty.pack(fill="both", expand=True)
        ctk.CTkLabel(
            empty,
            text="🎉 No duplicates found!\n\nYour files are well-organized.",
            justify="center",
            wraplength=200,
            text_color=self._tokens["text_secondary"],
            font=ctk.CTkFont(size=13),
        ).pack(expand=True, pady=24)

    @staticmethod
    def _group_card_labels(group: object, *, ordinal: int | None = None) -> tuple[str, str]:
        """User-facing title/sub for a duplicate group (ordinal + extensions + size, not raw UUIDs)."""
        files = list(getattr(group, "files", []) or [])
        n = len(files)
        exts = sorted({Path(getattr(f, "path", "") or "").suffix.lower() for f in files if getattr(f, "path", "")})
        exts = [e for e in exts if e]
        if not exts:
            ext_label = "files"
        elif len(exts) <= 4:
            ext_label = ", ".join(exts)
        else:
            ext_label = f"{exts[0]}, … ({len(exts)} types)"
        size_b = int(getattr(group, "total_size", 0) or 0)
        if size_b <= 0:
            size_b = sum(int(getattr(f, "size", 0) or 0) for f in files)
        prefix = f"#{ordinal} · " if ordinal is not None else ""
        title = f"{prefix}{n} × {ext_label}"
        sub = fmt_bytes(size_b) if size_b else "—"
        return title, sub

    def _rebuild_group_rows(self, gids: list[str]) -> None:
        self._clear_group_rows()
        for i, gid in enumerate(gids):
            group = self._group_map[gid]
            title_txt, sub_txt = self._group_card_labels(group, ordinal=i + 1)
            inner = ctk.CTkFrame(self._group_scroll, corner_radius=8, fg_color=self._group_row_normal)
            inner.pack(fill="x", pady=4)
            title_lbl = ctk.CTkLabel(
                inner,
                text=title_txt,
                font=ctk.CTkFont(weight="bold"),
                text_color=self._tokens["text_primary"],
                anchor="w",
            )
            title_lbl.pack(anchor="w", padx=10, pady=(8, 0))
            sub = ctk.CTkLabel(inner, text=sub_txt, text_color=self._tokens["text_secondary"], anchor="w")
            sub.pack(anchor="w", padx=10, pady=(0, 8))
            for w in (inner, title_lbl, sub):
                w.bind("<Button-1>", lambda _e, g=gid: self._select_group(g))
            inner.bind("<Enter>", lambda _e, g=gid, fr=inner: self._on_group_row_enter(fr, g))
            inner.bind("<Leave>", lambda _e, fr=inner, g=gid: self._group_row_leave(fr, g))
            self._group_row_frames[gid] = inner
        self._highlight_group_row(self._group_var.get())

    def _on_group_row_enter(self, fr: ctk.CTkFrame, gid: str) -> None:
        if self._group_var.get() != gid:
            fr.configure(fg_color=self._group_row_hover)

    def _group_row_leave(self, fr: ctk.CTkFrame, gid: str) -> None:
        if self._group_var.get() == gid:
            fr.configure(fg_color=self._group_row_selected)
        else:
            fr.configure(fg_color=self._group_row_normal)

    def _highlight_group_row(self, gid: str) -> None:
        for g, fr in self._group_row_frames.items():
            if g == gid:
                fr.configure(fg_color=self._group_row_selected)
            else:
                fr.configure(fg_color=self._group_row_normal)

    def _select_group(self, gid: str) -> None:
        if gid not in self._group_map:
            return
        self._group_var.set(gid)
        self._highlight_group_row(gid)
        self._rebuild_keep_menu(gid)
        self._sync_compare_default(gid)
        self._rebuild_compare_menu(gid)
        self._render_group_details(gid)
        self._refresh_heroes()
        self._update_preview_heading(gid)
        self._push_review_slices_to_store()

    def _update_preview_heading(self, gid: str) -> None:
        if not hasattr(self, "_preview_title"):
            return
        group = self._group_map.get(gid)
        if group is None:
            self._preview_title.configure(text="File preview")
            return
        has_img = False
        for f in getattr(group, "files", []) or []:
            p = getattr(f, "path", "") or ""
            if p and is_image_extension(Path(p).suffix.lower().lstrip(".")):
                has_img = True
                break
        self._preview_title.configure(text="Image comparison" if has_img else "File preview")

    def _push_review_slices_to_store(self) -> None:
        """Publish review index / preview / plan slices for subscribers (store-first contract)."""
        if not self._store:
            return
        gids = list(self._group_map.keys())
        cur = self._group_var.get() if gids else ""
        try:
            ix = gids.index(cur) if cur in gids else 0
        except ValueError:
            ix = 0
        keep_p = self._keep_map.get(cur, "") if cur else ""
        self._store.set_review_index(
            ReviewIndexState(
                current_group_index=ix,
                groups_total=len(gids),
                current_group_id=cur or None,
                filter_text="",
            )
        )
        self._store.set_review_preview(
            ReviewPreviewState(
                preview_target_path=keep_p or None,
                compare_target_path=self._compare_path,
                view_mode="compare",
                preview_metadata={"hero_px": self._hero_pixel_size},
            )
        )
        reclaim = int(getattr(self._result, "total_reclaimable_bytes", 0) or 0) if self._result else 0
        self._store.set_review_plan(
            ReviewPlanState(
                reclaimable_bytes=reclaim,
                plan_summary=self._summary_var.get() if hasattr(self, "_summary_var") else "",
            )
        )

    def _image_paths_in_group(self, group) -> list[str]:
        out: list[str] = []
        for f in getattr(group, "files", []) or []:
            p = getattr(f, "path", "") or ""
            if p and is_image_extension(Path(p).suffix.lower().lstrip(".")):
                out.append(p)
        return out

    def _sync_compare_default(self, gid: str) -> None:
        """Set _compare_path only; caller rebuilds compare menu and syncs the visible label."""
        group = self._group_map.get(gid)
        if group is None:
            self._compare_path = None
            return
        keep = self._keep_map.get(gid, "")
        imgs = self._image_paths_in_group(group)
        others = [p for p in imgs if p != keep]
        if others:
            self._compare_path = others[0]
            return
        if imgs:
            self._compare_path = imgs[0]
            return
        self._compare_path = None

    def _rebuild_compare_menu(self, gid: str) -> None:
        group = self._group_map.get(gid)
        if group is None:
            self._compare_label_to_path.clear()
            self._compare_menu.configure(values=[_COMPARE_EMPTY])
            self._compare_var.set(_COMPARE_EMPTY)
            return
        keep = self._keep_map.get(gid, "")
        imgs = self._image_paths_in_group(group)
        options = [p for p in imgs if p != keep]
        if not options and imgs:
            options = list(imgs)
        if not options:
            self._compare_label_to_path.clear()
            self._compare_menu.configure(values=[_COMPARE_EMPTY])
            self._compare_var.set(_COMPARE_EMPTY)
            self._compare_path = None
            return
        labels, self._compare_label_to_path = self._menu_labels_for_paths(options)
        self._compare_menu.configure(values=labels)
        lbl = self._label_for_path(self._compare_path, self._compare_label_to_path)
        if lbl:
            self._compare_var.set(lbl)
        else:
            self._compare_path = options[0]
            lbl0 = self._label_for_path(self._compare_path, self._compare_label_to_path)
            self._compare_var.set(lbl0 or labels[0])

    def _on_compare_menu_change(self, choice: str) -> None:
        path = self._resolve_compare_path(choice)
        if path is None:
            self._compare_path = None
            self._refresh_heroes()
            self._push_review_slices_to_store()
            return
        self._compare_path = path
        gid = self._group_var.get()
        if gid:
            self._render_group_details(gid)
        self._refresh_heroes()
        self._push_review_slices_to_store()

    def _on_keep_change(self, choice: str) -> None:
        gid = self._group_var.get()
        if not gid or not choice:
            return
        path = self._resolve_keep_path(choice)
        self._keep_map[gid] = path
        if self._review_controller:
            self._review_controller.handle_set_keep(gid, path)
        if self._compare_path == path:
            self._sync_compare_default(gid)
        self._rebuild_compare_menu(gid)
        self._render_group_details(gid)
        self._refresh_heroes()
        self._push_review_slices_to_store()

    def _rebuild_keep_menu(self, gid: str) -> None:
        group = self._group_map.get(gid)
        if group is None:
            self._keep_label_to_path.clear()
            self._keep_menu.configure(values=[""])
            self._keep_var.set("")
            return
        files = [f.path for f in getattr(group, "files", [])]
        if not files:
            self._keep_label_to_path.clear()
            self._keep_menu.configure(values=[""])
            self._keep_var.set("")
            return
        labels, self._keep_label_to_path = self._menu_labels_for_paths(files)
        self._keep_menu.configure(values=labels)
        want = self._keep_map.get(gid, files[0] if files else "")
        lbl = self._label_for_path(want, self._keep_label_to_path)
        if lbl:
            self._keep_var.set(lbl)
        elif labels:
            self._keep_map[gid] = self._keep_label_to_path[labels[0]]
            self._keep_var.set(labels[0])
        else:
            self._keep_var.set("")

    def _clear_compare_ui(self) -> None:
        self._hero_left_label.configure(image=None, text="Keep preview")
        self._hero_right_label.configure(image=None, text="Compare preview")
        self._hero_left_caption.set("")
        self._hero_right_caption.set("")

    def _pil_to_ctk(self, path: Path, max_size: tuple[int, int]) -> ctk.CTkImage | None:
        if not self._ui_alive():
            return None
        cached = get_thumbnail_path(str(path), size=max_size)
        if not cached or not cached.exists():
            return None
        try:
            from PIL import Image  # type: ignore

            with Image.open(cached) as im:
                im = im.copy()
            cimg = ctk.CTkImage(light_image=im, dark_image=im, size=im.size)
            self._ctk_image_refs.append(cimg)
            if len(self._ctk_image_refs) > 64:
                self._ctk_image_refs.pop(0)
            return cimg
        except Exception:
            return None

    def _hero_size_tuple(self) -> tuple[int, int]:
        s = self._hero_pixel_size
        return (s, s)

    def _refresh_heroes(self) -> None:
        if not self._ui_alive():
            return
        gid = self._group_var.get()
        keep = self._keep_map.get(gid, "") if gid else ""
        compare = self._compare_path or ""
        size = self._hero_size_tuple()

        def set_hero(lbl: ctk.CTkLabel, path: str, fallback: str, cap: ctk.StringVar) -> None:
            if path and Path(path).exists() and is_image_extension(Path(path).suffix.lower().lstrip(".")):
                cimg = self._pil_to_ctk(Path(path), size)
                if cimg:
                    lbl.configure(image=cimg, text="")
                    lbl.image = cimg  # type: ignore[attr-defined]
                    cap.set(Path(path).name)
                    return
            lbl.configure(image=None, text=fallback)
            cap.set(Path(path).name if path else "—")

        set_hero(self._hero_left_label, keep, "No keep preview", self._hero_left_caption)
        set_hero(self._hero_right_label, compare, "Pick compare file", self._hero_right_caption)

    def _render_group_details(self, gid: str) -> None:
        group = self._group_map.get(gid)
        if group is None:
            self._set_details("No group selected.")
            return
        keep = self._keep_map.get(gid, "")
        gids = list(self._group_map.keys())
        ord_i = gids.index(gid) + 1
        head, _sz = self._group_card_labels(group, ordinal=ord_i)
        lines = [head, f"Keep: {Path(keep).name if keep else '—'}", ""]
        for f in getattr(group, "files", []):
            marker = "KEEP" if f.path == keep else "DEL "
            lines.append(f"[{marker}] {f.path}")
        self._set_details("\n".join(lines))

    def _execute(self) -> None:
        if self._review_controller:
            self._review_controller.handle_execute_deletion()
            return
        if not self._on_execute:
            self._set_details("Review execution is not wired.")
            return
        if not self._keep_map:
            self._set_details("Nothing to execute.")
            return
        if not self._confirm_execute():
            return
        result = self._on_execute(dict(self._keep_map))
        if result is None:
            self._set_details("Deletion execution failed or no plan generated.")
            return
        self._show_result_panel()
        self._result_var.set(
            f"Deleted {len(result.deleted_files)} · Failed {len(result.failed_files)} · Reclaimed {fmt_bytes(result.bytes_reclaimed)}"
        )
        self._set_details(
            f"Deleted: {len(result.deleted_files)} files\n"
            f"Failed: {len(result.failed_files)} files\n"
            f"Reclaimed: {fmt_bytes(result.bytes_reclaimed)}"
        )

    def _confirm_execute(self) -> bool:
        files_to_delete = 0
        reclaimable = 0
        for gid, group in self._group_map.items():
            keep = self._keep_map.get(gid, "")
            files = list(getattr(group, "files", []) or [])
            for f in files:
                if f.path != keep:
                    files_to_delete += 1
                    reclaimable += int(getattr(f, "size", 0) or 0)
        msg = (
            f"Move {files_to_delete} file(s) to Trash?\n\n"
            f"Estimated space to free: {fmt_bytes(reclaimable)}\n\n"
            "Files go to the Recycle Bin or Trash (not permanently deleted) unless your system policy says otherwise."
        )
        return self._ctk_confirm("Move to Trash", msg)

    def _default_keep_for_group(self, group) -> str:
        files = list(getattr(group, "files", []) or [])
        return files[0].path if files else ""

    def _pick_by_policy(self, group, policy: str) -> str:
        files = list(getattr(group, "files", []) or [])
        if not files:
            return ""
        if policy == "newest":
            return max(files, key=lambda f: int(getattr(f, "mtime_ns", 0) or 0)).path
        if policy == "oldest":
            return min(files, key=lambda f: int(getattr(f, "mtime_ns", 0) or 0)).path
        if policy == "largest":
            return max(files, key=lambda f: int(getattr(f, "size", 0) or 0)).path
        if policy == "smallest":
            return min(files, key=lambda f: int(getattr(f, "size", 0) or 0)).path
        return files[0].path

    def _set_details(self, text: str) -> None:
        self._details.configure(state="normal")
        self._details.delete("1.0", "end")
        self._details.insert("end", text + "\n")
        self._details.configure(state="disabled")

    def _bind_review_shortcuts(self) -> None:
        """Bind review page specific keyboard shortcuts."""
        # Use page-local bindings instead of global to avoid conflicts
        self.bind("<space>", lambda e: self._keep_selected_file())
        self.bind("<Delete>", lambda e: self._delete_selected_file())
        self.bind("<Control-Key-a>", lambda e: self._select_all_files())
        self.bind("<Control-Key-d>", lambda e: self._deselect_all_files())

    def _keep_selected_file(self) -> None:
        """Keep the currently selected file in the comparison."""
        if self._compare_path and self._compare_var.get() != _COMPARE_EMPTY:
            current_gid = self._group_var.get()
            if current_gid and current_gid in self._group_map:
                self._keep_map[current_gid] = self._compare_path
                self._update_keep_selection(current_gid)
                self._set_details(f"Kept: {self._compare_path}")

    def _delete_selected_file(self) -> None:
        """Mark the currently selected file for deletion."""
        if self._compare_path and self._compare_var.get() != _COMPARE_EMPTY:
            current_gid = self._group_var.get()
            if current_gid and current_gid in self._group_map:
                # In review context, "delete" means don't keep this file
                if self._keep_map.get(current_gid) == self._compare_path:
                    # If this was the keep file, pick a different one
                    group = self._group_map[current_gid]
                    files = list(getattr(group, "files", []) or [])
                    other_files = [f.path for f in files if f.path != self._compare_path]
                    if other_files:
                        self._keep_map[current_gid] = other_files[0]
                        self._update_keep_selection(current_gid)
                        self._set_details(f"Marked for deletion: {self._compare_path}")

    def _select_all_files(self) -> None:
        """Select all duplicate groups."""
        if self._group_map:
            gids = list(self._group_map.keys())
            self._set_details(f"Selected all {len(gids)} groups")

    def _deselect_all_files(self) -> None:
        """Deselect all groups."""
        self._group_var.set("")
        self._clear_group_rows()
        self._set_details("Deselected all groups")
