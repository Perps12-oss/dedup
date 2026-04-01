"""CustomTkinter Review page with async thumbnails and stable layout."""

from __future__ import annotations

import logging
import threading
import tkinter
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional

import customtkinter as ctk

from ...engine.media_types import is_image_extension
from ...engine.models import DeletionResult, ScanResult
from ...engine.thumbnails import generate_thumbnails_async, get_thumbnail_path
from ..state.store import ReviewIndexState, ReviewPlanState, ReviewPreviewState, ReviewSelectionState
from ..utils.formatting import fmt_bytes
from ..utils.review_keep import coerce_keep_selections, default_keep_map_from_result
from ..utils.theme_helpers import theme_pair
from .design_tokens import get_theme_colors, resolve_border_token

_log = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ..controller.review_controller import ReviewController
    from ..state.store import UIStateStore

_COMPARE_EMPTY = "—"


class ReviewPageCTK(ctk.CTkFrame):
    """CTK review page: groups | comparison | actions."""

    _HERO_MIN = 280
    _HERO_MAX = 900
    _GROUP_THUMB_SIZE = (48, 48)
    _MIDDLE_SELECTION_THRESHOLD = 1000

    def _ui_alive(self) -> bool:
        """False after destroy — avoids configuring widgets from stale callbacks."""
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
        self._hero_after_id: str | None = None
        self._group_row_frames: dict[str, ctk.CTkFrame] = {}
        self._group_thumb_labels: dict[str, ctk.CTkLabel] = {}
        self._group_thumb_refs: dict[str, ctk.CTkImage] = {}
        self._keep_label_to_path: dict[str, str] = {}
        self._compare_label_to_path: dict[str, str] = {}
        self._hero_target_labels: dict[str, set[str]] = {}
        self._hero_image_refs: dict[str, ctk.CTkImage] = {}
        self._group_thumb_cancel_event: threading.Event | None = None
        self._hero_thumb_cancel_event: threading.Event | None = None
        self._tokens = get_theme_colors()
        self._applied_theme_signature: tuple[tuple[str, str], ...] | None = None

        self.grid_columnconfigure(0, weight=0, minsize=240)
        self.grid_columnconfigure(1, weight=1, minsize=420)
        self.grid_columnconfigure(2, weight=0, minsize=320)
        self.grid_rowconfigure(1, weight=3)
        self.grid_rowconfigure(3, weight=1)
        self._build()

    def destroy(self) -> None:
        self._cancel_async_jobs()
        if self._resize_after_id is not None:
            try:
                self.after_cancel(self._resize_after_id)
            except (tkinter.TclError, RuntimeError):
                pass
            self._resize_after_id = None
        if self._hero_after_id is not None:
            try:
                self.after_cancel(self._hero_after_id)
            except (tkinter.TclError, RuntimeError):
                pass
            self._hero_after_id = None
        super().destroy()

    def _cancel_async_jobs(self) -> None:
        if self._group_thumb_cancel_event is not None:
            self._group_thumb_cancel_event.set()
            self._group_thumb_cancel_event = None
        if self._hero_thumb_cancel_event is not None:
            self._hero_thumb_cancel_event.set()
            self._hero_thumb_cancel_event = None

    def _build(self) -> None:
        tk = self._tokens

        self._header = ctk.CTkFrame(
            self,
            corner_radius=16,
            fg_color=tk["bg_panel"],
            border_width=1,
            border_color=tk["border_subtle"],
        )
        self._header.grid(row=0, column=0, columnspan=3, sticky="ew", padx=20, pady=(20, 12))
        self._header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            self._header,
            text="Review Studio",
            font=ctk.CTkFont(size=26, weight="bold"),
            text_color=tk["text_primary"],
        ).grid(row=0, column=0, sticky="w", padx=18, pady=(14, 4))
        self._summary_var = ctk.StringVar(value="No scan loaded")
        ctk.CTkLabel(
            self._header,
            textvariable=self._summary_var,
            text_color=tk["text_secondary"],
            font=ctk.CTkFont(size=13),
        ).grid(row=1, column=0, sticky="w", padx=18, pady=(0, 12))

        self._review_left = ctk.CTkFrame(
            self,
            corner_radius=16,
            width=240,
            fg_color=tk["bg_panel"],
            border_width=1,
            border_color=tk["border_subtle"],
        )
        self._review_left.grid(row=1, column=0, sticky="nsew", padx=(20, 8), pady=(0, 12))
        self._review_left.grid_rowconfigure(1, weight=1)
        self._review_left.grid_propagate(False)
        ctk.CTkLabel(
            self._review_left,
            text="Groups",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=tk["text_primary"],
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(12, 8))
        self._group_scroll = ctk.CTkScrollableFrame(self._review_left, fg_color="transparent")
        self._group_scroll.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 12))

        self._review_center = ctk.CTkFrame(
            self,
            corner_radius=16,
            fg_color=tk["bg_panel"],
            border_width=1,
            border_color=tk["border_subtle"],
        )
        self._review_center.grid(row=1, column=1, sticky="nsew", padx=8, pady=(0, 12))
        self._review_center.grid_columnconfigure(0, weight=1)
        self._review_center.grid_rowconfigure(1, weight=1)

        self._preview_title = ctk.CTkLabel(
            self._review_center,
            text="Inline comparison",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=tk["text_primary"],
        )
        self._preview_title.grid(row=0, column=0, sticky="w", padx=16, pady=(14, 8))

        self._hero_viewport = ctk.CTkFrame(self._review_center, fg_color="transparent")
        self._hero_viewport.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self._hero_viewport.grid_columnconfigure(0, weight=1)
        self._hero_viewport.grid_columnconfigure(1, weight=1)
        self._hero_viewport.grid_rowconfigure(0, weight=1)
        self._hero_viewport.bind("<Configure>", self._on_hero_viewport_configure)

        self._hero_left_card = ctk.CTkFrame(
            self._hero_viewport,
            corner_radius=14,
            fg_color=tk["bg_surface"],
            border_width=1,
            border_color=tk["border_subtle"],
        )
        self._hero_left_card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self._hero_left_card.grid_rowconfigure(0, weight=1)
        self._hero_left_card.grid_columnconfigure(0, weight=1)
        self._hero_left_label = ctk.CTkLabel(
            self._hero_left_card,
            text="Keep preview",
            text_color=tk["text_secondary"],
        )
        self._hero_left_label.grid(row=0, column=0, sticky="nsew", padx=12, pady=(12, 8))
        self._hero_left_caption = ctk.StringVar(value="")
        ctk.CTkLabel(
            self._hero_left_card,
            textvariable=self._hero_left_caption,
            text_color=tk["text_secondary"],
            font=ctk.CTkFont(size=12),
        ).grid(row=1, column=0, sticky="w", padx=12, pady=(0, 12))

        self._hero_right_card = ctk.CTkFrame(
            self._hero_viewport,
            corner_radius=14,
            fg_color=tk["bg_surface"],
            border_width=1,
            border_color=tk["border_subtle"],
        )
        self._hero_right_card.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        self._hero_right_card.grid_rowconfigure(0, weight=1)
        self._hero_right_card.grid_columnconfigure(0, weight=1)
        self._hero_right_label = ctk.CTkLabel(
            self._hero_right_card,
            text="Compare preview",
            text_color=tk["text_secondary"],
        )
        self._hero_right_label.grid(row=0, column=0, sticky="nsew", padx=12, pady=(12, 8))
        self._hero_right_caption = ctk.StringVar(value="")
        ctk.CTkLabel(
            self._hero_right_card,
            textvariable=self._hero_right_caption,
            text_color=tk["text_secondary"],
            font=ctk.CTkFont(size=12),
        ).grid(row=1, column=0, sticky="w", padx=12, pady=(0, 12))

        self._empty_overlay = ctk.CTkFrame(
            self._review_center,
            corner_radius=16,
            fg_color=tk["bg_panel"],
            border_width=1,
            border_color=tk["border_subtle"],
        )
        ctk.CTkLabel(
            self._empty_overlay,
            text="No scan to review",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=tk["text_primary"],
        ).pack(pady=(70, 10))
        ctk.CTkLabel(
            self._empty_overlay,
            text="Run a scan, open a result from History, or refresh the last completed scan.",
            text_color=tk["text_secondary"],
            wraplength=420,
            justify="center",
        ).pack(padx=24)

        self._review_right = ctk.CTkFrame(
            self,
            corner_radius=16,
            width=320,
            fg_color=tk["bg_panel"],
            border_width=1,
            border_color=tk["border_subtle"],
        )
        self._review_right.grid(row=1, column=2, sticky="nsew", padx=(8, 20), pady=(0, 12))
        self._review_right.grid_columnconfigure(0, weight=1)
        self._review_right.grid_rowconfigure(7, weight=1)

        ctk.CTkLabel(
            self._review_right,
            text="Keep file",
            text_color=tk["text_secondary"],
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(16, 6))
        self._keep_menu = ctk.CTkOptionMenu(
            self._review_right,
            variable=self._keep_var,
            values=[""],
            command=self._on_keep_change,
        )
        self._keep_menu.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 10))

        ctk.CTkLabel(
            self._review_right,
            text="Compare file",
            text_color=tk["text_secondary"],
        ).grid(row=2, column=0, sticky="w", padx=16, pady=(2, 6))
        self._compare_menu = ctk.CTkOptionMenu(
            self._review_right,
            variable=self._compare_var,
            values=[_COMPARE_EMPTY],
            command=self._on_compare_menu_change,
        )
        self._compare_menu.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 12))

        self._selection_card = ctk.CTkFrame(
            self._review_right,
            corner_radius=14,
            fg_color=tk["bg_surface"],
            border_width=1,
            border_color=tk["border_subtle"],
        )
        self._selection_card.grid(row=4, column=0, sticky="ew", padx=16, pady=(0, 12))
        self._selection_card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            self._selection_card,
            text="Selection",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=tk["text_primary"],
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(12, 6))
        self._selection_summary_var = ctk.StringVar(value="No group selected")
        ctk.CTkLabel(
            self._selection_card,
            textvariable=self._selection_summary_var,
            text_color=tk["text_secondary"],
            justify="left",
            wraplength=250,
        ).grid(row=1, column=0, sticky="w", padx=12, pady=(0, 12))
        self._reset_group_btn = ctk.CTkButton(
            self._selection_card,
            text="Reset this group",
            fg_color=tk["bg_elevated"],
            hover_color=tk["bg_overlay"],
            text_color=tk["text_secondary"],
            border_width=1,
            border_color=tk["border_subtle"],
            command=self._reset_current_group_keep,
        )
        self._reset_group_btn.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 12))

        self._action_row = ctk.CTkFrame(self._review_right, fg_color="transparent")
        self._action_row.grid(row=5, column=0, sticky="ew", padx=16, pady=(0, 12))
        danger = tk["danger"]
        danger_hover = tk["danger_hover"]
        self._execute_btn = ctk.CTkButton(
            self._action_row,
            text="Move to Trash",
            fg_color=danger,
            hover_color=danger_hover,
            text_color=("#FFFFFF", "#0A0E14"),
            command=self._execute,
        )
        self._execute_btn.pack(side="left", padx=(0, 8))
        self._refresh_btn = ctk.CTkButton(
            self._action_row,
            text="Refresh",
            fg_color=tk["bg_elevated"],
            hover_color=tk["bg_overlay"],
            text_color=tk["text_secondary"],
            border_width=1,
            border_color=tk["border_subtle"],
            command=self._refresh_callback,
        )
        self._refresh_btn.pack(side="left")

        ctk.CTkFrame(self._review_right, fg_color="transparent").grid(row=7, column=0, sticky="nsew")

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
        ctk.CTkLabel(
            self._result_panel,
            textvariable=self._result_var,
            text_color=tk["text_secondary"],
        ).grid(row=1, column=0, sticky="w", padx=16, pady=(0, 12))

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

        self._themed_sections = [
            self._header,
            self._review_left,
            self._review_center,
            self._review_right,
            self._selection_card,
            self._hero_left_card,
            self._hero_right_card,
            self._result_panel,
            self._empty_overlay,
        ]
        self._group_row_normal = "transparent"
        self._group_row_hover = self._tokens["bg_overlay"]
        self._group_row_selected = self._tokens["bg_elevated"]
        self._layout_review_empty(True)
        self._result_panel.grid_remove()

    def _layout_review_empty(self, show: bool) -> None:
        if show:
            self._empty_overlay.place(relx=0.0, rely=0.0, relwidth=1.0, relheight=1.0)
            self._preview_title.configure(text="Review")
        else:
            self._empty_overlay.place_forget()

    def apply_theme_tokens(self, tokens: dict) -> None:
        signature = tuple(sorted((str(k), str(v)) for k, v in tokens.items()))
        if signature == self._applied_theme_signature:
            return
        self._applied_theme_signature = signature
        self._tokens = {**self._tokens, **{k: str(v) for k, v in tokens.items()}}
        panel = str(tokens.get("bg_panel", self._tokens["bg_panel"]))
        elev = str(tokens.get("bg_elevated", self._tokens["bg_elevated"]))
        surf = str(tokens.get("bg_surface", tokens.get("bg_elevated", self._tokens["bg_surface"])))
        overlay = str(tokens.get("bg_overlay", self._tokens["bg_overlay"]))
        border = resolve_border_token(tokens)
        txt_primary = str(tokens.get("text_primary", self._tokens["text_primary"]))
        txt_secondary = str(tokens.get("text_secondary", self._tokens["text_secondary"]))
        danger = str(tokens.get("danger", self._tokens["danger"]))
        danger_hover = str(tokens.get("danger_hover", self._tokens["danger_hover"]))

        self.configure(fg_color=panel)
        for frame in self._themed_sections:
            try:
                frame.configure(fg_color=panel, border_color=border)
            except Exception:
                _log.warning("review theme apply failed for %r", frame, exc_info=True)
        for frame in (self._selection_card, self._hero_left_card, self._hero_right_card):
            frame.configure(fg_color=surf, border_color=border)

        self._execute_btn.configure(fg_color=danger, hover_color=danger_hover)
        self._refresh_btn.configure(fg_color=elev, hover_color=overlay, border_color=border, text_color=txt_secondary)
        self._reset_group_btn.configure(
            fg_color=elev,
            hover_color=overlay,
            border_color=border,
            text_color=txt_secondary,
        )
        self._details.configure(fg_color=surf, text_color=txt_secondary, border_color=border)
        self._group_row_hover = theme_pair(tokens.get("bg_overlay"), self._tokens["bg_overlay"])
        self._group_row_selected = theme_pair(tokens.get("bg_elevated"), self._tokens["bg_elevated"])
        cur = self._group_var.get()
        if cur and self._group_row_frames:
            self._highlight_group_row(cur)

        self._update_label_colors(self, {"text_primary": txt_primary, "text_secondary": txt_secondary})

    def _update_label_colors(self, widget, tokens: dict) -> None:
        from ..utils.theme_utils import apply_label_colors

        apply_label_colors(widget, tokens)

    def set_refresh_callback(self, callback: Callable[[], ScanResult | None]) -> None:
        self._refresh_callback = lambda: self.load_result(callback())
        if hasattr(self, "_refresh_btn"):
            self._refresh_btn.configure(command=self._refresh_callback)

    def set_review_controller(self, ctrl: "ReviewController") -> None:
        self._review_controller = ctrl

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
            self._schedule_hero_refresh()
            self._update_preview_heading(cur)
            self._push_review_slices_to_store()

    def _ctk_confirm(self, title: str, message: str) -> bool:
        tk = self._tokens
        bg = tk["bg_panel"]
        txt = tk["text_primary"]
        muted = tk["text_secondary"]
        danger = tk["danger"]
        danger_hover = tk["danger_hover"]
        root = self.winfo_toplevel()
        out: list[bool] = [False]

        dlg = ctk.CTkToplevel(root)
        dlg.title(title)
        dlg.geometry("460x280")
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
            wraplength=410,
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
        return "proceed" if self._ctk_confirm("Move to Trash", msg) else "cancel"

    def on_execute_start(self) -> None:
        self._execute_btn.configure(state="disabled", text="Working…")
        self.update_idletasks()

    def on_execute_done(self, result: DeletionResult) -> None:
        self._execute_btn.configure(state="normal", text="Move to Trash")
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
        return self._result

    @staticmethod
    def _menu_labels_for_paths(paths: list[str]) -> tuple[list[str], dict[str, str]]:
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
            self._schedule_hero_refresh()

    def load_result(self, result: ScanResult | None) -> None:
        self._cancel_async_jobs()
        self._result = result
        self._result_panel.grid_remove()
        self._clear_group_thumbs()

        if not result or not getattr(result, "duplicate_groups", None):
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
            self._compare_path = None
            self._selection_summary_var.set("No group selected")
            self._clear_compare_ui()
            self._set_details("No duplicate groups in last scan.")
            self._push_review_slices_to_store()
            return

        self._group_map = {
            str(g.group_id): g
            for g in result.duplicate_groups
            if len(getattr(g, "files", []) or []) >= 2
        }
        if not self._group_map:
            self._layout_review_empty(False)
            reclaim = int(getattr(result, "total_reclaimable_bytes", 0) or 0)
            self._summary_var.set(
                f"No duplicate groups of 2+ files · {fmt_bytes(reclaim)} reclaimable" if reclaim
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
            self._compare_path = None
            self._selection_summary_var.set("No reviewable groups")
            self._clear_compare_ui()
            self._set_details("No groups with at least two files to compare.")
            if self._store:
                self._store.set_review_selection(ReviewSelectionState(keep_selections={}, selected_group_id=None))
            self._push_review_slices_to_store()
            return

        self._layout_review_empty(False)
        self._keep_map = {gid: self._default_keep_for_group(self._group_map[gid]) for gid in self._group_map}
        gids = list(self._group_map.keys())
        if self._store:
            km = default_keep_map_from_result(result)
            km = coerce_keep_selections(result, km)
            self._store.set_review_selection(
                ReviewSelectionState(keep_selections=km, selected_group_id=gids[0] if gids else None)
            )

        total_groups = len(self._group_map)
        self._summary_var.set(
            f"{total_groups:,} groups · {fmt_bytes(getattr(result, 'total_reclaimable_bytes', 0) or 0)} reclaimable"
        )
        self._rebuild_group_rows(gids)
        first_gid = self._resolve_initial_group_id(gids)
        self._select_group(first_gid)
        self.after_idle(self._load_group_thumbnails_async)
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
            self._schedule_hero_refresh()
            self._push_review_slices_to_store()

    def _clear_group_rows(self) -> None:
        for widget in self._group_scroll.winfo_children():
            widget.destroy()
        self._group_row_frames.clear()
        self._group_thumb_labels.clear()

    def _clear_group_thumbs(self) -> None:
        self._group_thumb_refs.clear()
        self._hero_image_refs.clear()
        self._hero_target_labels.clear()

    def _show_no_duplicates_empty(self) -> None:
        empty = ctk.CTkFrame(self._group_scroll, fg_color="transparent")
        empty.pack(fill="both", expand=True)
        ctk.CTkLabel(
            empty,
            text="No duplicate groups\nwith 2 or more files.",
            justify="center",
            wraplength=210,
            text_color=self._tokens["text_secondary"],
            font=ctk.CTkFont(size=13),
        ).pack(expand=True, pady=24)

    @staticmethod
    def _group_card_labels(group: object, *, ordinal: int | None = None) -> tuple[str, str]:
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
        for index, gid in enumerate(gids):
            group = self._group_map[gid]
            title_txt, sub_txt = self._group_card_labels(group, ordinal=index + 1)
            card = ctk.CTkFrame(self._group_scroll, corner_radius=10, fg_color=self._group_row_normal)
            card.pack(fill="x", pady=4)

            thumb = ctk.CTkLabel(
                card,
                text="…",
                width=self._GROUP_THUMB_SIZE[0],
                height=self._GROUP_THUMB_SIZE[1],
                corner_radius=8,
                fg_color=self._tokens["bg_surface"],
                text_color=self._tokens["text_secondary"],
            )
            thumb.grid(row=0, column=0, rowspan=2, padx=(10, 8), pady=10, sticky="nw")

            title_lbl = ctk.CTkLabel(
                card,
                text=title_txt,
                font=ctk.CTkFont(weight="bold"),
                text_color=self._tokens["text_primary"],
                anchor="w",
            )
            title_lbl.grid(row=0, column=1, sticky="ew", padx=(0, 10), pady=(10, 2))
            sub_lbl = ctk.CTkLabel(
                card,
                text=sub_txt,
                text_color=self._tokens["text_secondary"],
                anchor="w",
            )
            sub_lbl.grid(row=1, column=1, sticky="ew", padx=(0, 10), pady=(0, 10))
            card.grid_columnconfigure(1, weight=1)

            for widget in (card, thumb, title_lbl, sub_lbl):
                widget.bind("<Button-1>", lambda _e, g=gid: self._select_group(g))
            card.bind("<Enter>", lambda _e, g=gid, fr=card: self._on_group_row_enter(fr, g))
            card.bind("<Leave>", lambda _e, fr=card, g=gid: self._group_row_leave(fr, g))

            self._group_row_frames[gid] = card
            self._group_thumb_labels[gid] = thumb
        self._highlight_group_row(self._group_var.get())

    def _on_group_row_enter(self, frame: ctk.CTkFrame, gid: str) -> None:
        if self._group_var.get() != gid:
            frame.configure(fg_color=self._group_row_hover)

    def _group_row_leave(self, frame: ctk.CTkFrame, gid: str) -> None:
        frame.configure(fg_color=self._group_row_selected if self._group_var.get() == gid else self._group_row_normal)

    def _highlight_group_row(self, gid: str) -> None:
        for group_id, frame in self._group_row_frames.items():
            frame.configure(fg_color=self._group_row_selected if group_id == gid else self._group_row_normal)

    def _resolve_initial_group_id(self, gids: list[str]) -> str:
        current = self._group_var.get()
        return current if current in self._group_map else (gids[0] if gids else "")

    def _select_group_by_index(self, index: int) -> None:
        gids = list(self._group_map.keys())
        if not gids:
            return
        index = max(0, min(index, len(gids) - 1))
        self._select_group(gids[index])

    def _select_group(self, gid: str) -> None:
        if gid not in self._group_map:
            return
        self._group_var.set(gid)
        self._highlight_group_row(gid)
        self._rebuild_keep_menu(gid)
        self._sync_compare_default(gid)
        self._rebuild_compare_menu(gid)
        self._render_group_details(gid)
        self._update_preview_heading(gid)
        self._schedule_hero_refresh()
        self._push_review_slices_to_store()

    def _update_preview_heading(self, gid: str) -> None:
        group = self._group_map.get(gid)
        if group is None:
            self._preview_title.configure(text="Review")
            return
        has_image = bool(self._image_paths_in_group(group))
        self._preview_title.configure(text="Inline image comparison" if has_image else "File comparison")

    def _update_selection_summary(self, gid: str) -> None:
        group = self._group_map.get(gid)
        if group is None:
            self._selection_summary_var.set("No group selected")
            return
        keep = self._keep_map.get(gid, "")
        files = list(getattr(group, "files", []) or [])
        delete_count = max(0, len(files) - (1 if keep else 0))
        group_size = sum(int(getattr(f, "size", 0) or 0) for f in files if getattr(f, "path", "") != keep)
        keep_name = Path(keep).name if keep else "—"
        self._selection_summary_var.set(
            f"Keep: {keep_name}\nDelete candidates: {delete_count}\nThis group reclaimable: {fmt_bytes(group_size)}"
        )

    def _push_review_slices_to_store(self) -> None:
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
            path = getattr(f, "path", "") or ""
            if path and is_image_extension(Path(path).suffix.lower().lstrip(".")):
                out.append(path)
        return out

    def _sync_compare_default(self, gid: str) -> None:
        group = self._group_map.get(gid)
        if group is None:
            self._compare_path = None
            return
        keep = self._keep_map.get(gid, "")
        images = self._image_paths_in_group(group)
        others = [path for path in images if path != keep]
        if others:
            self._compare_path = others[0]
        elif images:
            self._compare_path = images[0]
        else:
            self._compare_path = None

    def _rebuild_compare_menu(self, gid: str) -> None:
        group = self._group_map.get(gid)
        if group is None:
            self._compare_label_to_path.clear()
            self._compare_menu.configure(values=[_COMPARE_EMPTY])
            self._compare_var.set(_COMPARE_EMPTY)
            return
        keep = self._keep_map.get(gid, "")
        images = self._image_paths_in_group(group)
        options = [path for path in images if path != keep] or list(images)
        if not options:
            self._compare_label_to_path.clear()
            self._compare_menu.configure(values=[_COMPARE_EMPTY])
            self._compare_var.set(_COMPARE_EMPTY)
            self._compare_path = None
            return
        labels, self._compare_label_to_path = self._menu_labels_for_paths(options)
        self._compare_menu.configure(values=labels)
        label = self._label_for_path(self._compare_path, self._compare_label_to_path)
        if label:
            self._compare_var.set(label)
        else:
            self._compare_path = options[0]
            first = self._label_for_path(self._compare_path, self._compare_label_to_path)
            self._compare_var.set(first or labels[0])

    def _on_compare_menu_change(self, choice: str) -> None:
        self._compare_path = self._resolve_compare_path(choice)
        gid = self._group_var.get()
        if gid:
            self._render_group_details(gid)
        self._schedule_hero_refresh()
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
        self._schedule_hero_refresh()
        self._push_review_slices_to_store()

    def _rebuild_keep_menu(self, gid: str) -> None:
        group = self._group_map.get(gid)
        if group is None:
            self._keep_label_to_path.clear()
            self._keep_menu.configure(values=[""])
            self._keep_var.set("")
            return
        files = [file.path for file in getattr(group, "files", [])]
        if not files:
            self._keep_label_to_path.clear()
            self._keep_menu.configure(values=[""])
            self._keep_var.set("")
            return
        labels, self._keep_label_to_path = self._menu_labels_for_paths(files)
        self._keep_menu.configure(values=labels)
        wanted = self._keep_map.get(gid, files[0])
        label = self._label_for_path(wanted, self._keep_label_to_path)
        if label:
            self._keep_var.set(label)
        else:
            self._keep_map[gid] = self._keep_label_to_path[labels[0]]
            self._keep_var.set(labels[0])

    def _clear_compare_ui(self) -> None:
        self._hero_left_label.configure(image=None, text="Keep preview")
        self._hero_right_label.configure(image=None, text="Compare preview")
        self._hero_left_caption.set("")
        self._hero_right_caption.set("")
        self._hero_left_label.image = None  # type: ignore[attr-defined]
        self._hero_right_label.image = None  # type: ignore[attr-defined]

    def _pil_to_ctk(
        self,
        path: Path,
        max_size: tuple[int, int],
        *,
        thumb_path: Path | None = None,
    ) -> ctk.CTkImage | None:
        if not self._ui_alive():
            return None
        cached = thumb_path or get_thumbnail_path(str(path), size=max_size)
        if not cached or not cached.exists():
            return None
        try:
            from PIL import Image  # type: ignore

            with Image.open(cached) as image:
                image = image.copy()
            cimg = ctk.CTkImage(light_image=image, dark_image=image, size=max_size)
            self._ctk_image_refs.append(cimg)
            if len(self._ctk_image_refs) > 128:
                self._ctk_image_refs = self._ctk_image_refs[-96:]
            return cimg
        except Exception:
            _log.warning("review inline preview load failed for %s", path, exc_info=True)
            return None

    def _hero_size_tuple(self) -> tuple[int, int]:
        side = self._hero_pixel_size
        return (side, side)

    def _schedule_hero_refresh(self) -> None:
        if self._hero_after_id is not None:
            try:
                self.after_cancel(self._hero_after_id)
            except (tkinter.TclError, RuntimeError):
                pass
        self._hero_after_id = self.after_idle(self._refresh_heroes_async)

    def _refresh_heroes_async(self) -> None:
        self._hero_after_id = None
        if not self._ui_alive():
            return
        if self._hero_thumb_cancel_event is not None:
            self._hero_thumb_cancel_event.set()
        self._hero_thumb_cancel_event = threading.Event()
        self._hero_target_labels.clear()

        gid = self._group_var.get()
        keep = self._keep_map.get(gid, "") if gid else ""
        compare = self._compare_path or ""
        size = self._hero_size_tuple()

        self._apply_hero_fallback(self._hero_left_label, keep, "Keep preview", self._hero_left_caption)
        self._apply_hero_fallback(self._hero_right_label, compare, "Compare preview", self._hero_right_caption)

        load_paths: list[str] = []
        for path, target in ((keep, "left"), (compare, "right")):
            if not path:
                continue
            suffix = Path(path).suffix.lower().lstrip(".")
            if not is_image_extension(suffix):
                continue
            self._hero_target_labels.setdefault(path, set()).add(target)
            if path not in load_paths:
                load_paths.append(path)

        if not load_paths:
            return

        cancel_event = self._hero_thumb_cancel_event

        def _callback(path: str, thumb_path: Optional[Path]) -> None:
            if cancel_event.is_set() or not self._ui_alive():
                return
            try:
                self.after(0, lambda p=path, tp=thumb_path: self._set_hero_from_thumb(p, tp, size, cancel_event))
            except (tkinter.TclError, RuntimeError):
                return

        generate_thumbnails_async(
            load_paths,
            _callback,
            size=size,
            max_count=len(load_paths),
            cancel_event=cancel_event,
        )

    def _apply_hero_fallback(
        self,
        label: ctk.CTkLabel,
        path: str,
        fallback: str,
        caption: ctk.StringVar,
    ) -> None:
        label.configure(image=None, text=fallback)
        label.image = None  # type: ignore[attr-defined]
        caption.set(Path(path).name if path else "—")

    def _set_hero_from_thumb(
        self,
        path: str,
        thumb_path: Optional[Path],
        size: tuple[int, int],
        cancel_event: threading.Event,
    ) -> None:
        if cancel_event.is_set() or not self._ui_alive():
            return
        target_names = self._hero_target_labels.get(path, set())
        if not thumb_path or not target_names:
            return
        image = self._pil_to_ctk(Path(path), size, thumb_path=thumb_path)
        if image is None:
            return
        self._hero_image_refs[path] = image
        if "left" in target_names:
            self._hero_left_label.configure(image=image, text="")
            self._hero_left_label.image = image  # type: ignore[attr-defined]
            self._hero_left_caption.set(Path(path).name)
        if "right" in target_names:
            self._hero_right_label.configure(image=image, text="")
            self._hero_right_label.image = image  # type: ignore[attr-defined]
            self._hero_right_caption.set(Path(path).name)

    def _lead_image_for_group(self, gid: str) -> str | None:
        group = self._group_map.get(gid)
        if group is None:
            return None
        images = self._image_paths_in_group(group)
        return images[0] if images else None

    def _load_group_thumbnails_async(self) -> None:
        if not self._ui_alive() or not self._group_map:
            return
        if self._group_thumb_cancel_event is not None:
            self._group_thumb_cancel_event.set()
        self._group_thumb_cancel_event = threading.Event()
        cancel_event = self._group_thumb_cancel_event

        path_to_gid: dict[str, str] = {}
        paths: list[str] = []
        for gid in self._group_map:
            lead = self._lead_image_for_group(gid)
            if not lead or lead in path_to_gid:
                continue
            path_to_gid[lead] = gid
            paths.append(lead)

        if not paths:
            return

        def _callback(path: str, thumb_path: Optional[Path]) -> None:
            if cancel_event.is_set() or not self._ui_alive():
                return
            gid = path_to_gid.get(path)
            if not gid:
                return
            try:
                self.after(0, lambda g=gid, p=path, tp=thumb_path: self._set_group_thumb(g, p, tp, cancel_event))
            except (tkinter.TclError, RuntimeError):
                return

        generate_thumbnails_async(
            paths,
            _callback,
            size=self._GROUP_THUMB_SIZE,
            max_count=len(paths),
            cancel_event=cancel_event,
        )

    def _set_group_thumb(
        self,
        gid: str,
        source_path: str,
        thumb_path: Optional[Path],
        cancel_event: threading.Event,
    ) -> None:
        if cancel_event.is_set() or not self._ui_alive():
            return
        label = self._group_thumb_labels.get(gid)
        if label is None:
            return
        if not thumb_path:
            label.configure(text="IMG", image=None)
            return
        image = self._pil_to_ctk(Path(source_path), self._GROUP_THUMB_SIZE, thumb_path=thumb_path)
        if image is None:
            label.configure(text="IMG", image=None)
            return
        self._group_thumb_refs[gid] = image
        label.configure(image=image, text="")
        label.image = image  # type: ignore[attr-defined]

    def _render_group_details(self, gid: str) -> None:
        group = self._group_map.get(gid)
        if group is None:
            self._selection_summary_var.set("No group selected")
            self._set_details("No group selected.")
            return
        keep = self._keep_map.get(gid, "")
        gids = list(self._group_map.keys())
        ordinal = gids.index(gid) + 1
        heading, _ = self._group_card_labels(group, ordinal=ordinal)
        lines = [heading, f"Keep: {Path(keep).name if keep else '—'}", ""]
        for file_meta in getattr(group, "files", []):
            marker = "KEEP" if file_meta.path == keep else "DEL "
            lines.append(f"[{marker}] {file_meta.path}")
        self._update_selection_summary(gid)
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
            for file_meta in list(getattr(group, "files", []) or []):
                if file_meta.path != keep:
                    files_to_delete += 1
                    reclaimable += int(getattr(file_meta, "size", 0) or 0)
        msg = (
            f"Move {files_to_delete} file(s) to Trash?\n\n"
            f"Estimated space to free: {fmt_bytes(reclaimable)}\n\n"
            "Files go to the Recycle Bin or Trash unless your system policy says otherwise."
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
            return max(files, key=lambda file_meta: int(getattr(file_meta, "mtime_ns", 0) or 0)).path
        if policy == "oldest":
            return min(files, key=lambda file_meta: int(getattr(file_meta, "mtime_ns", 0) or 0)).path
        if policy == "largest":
            return max(files, key=lambda file_meta: int(getattr(file_meta, "size", 0) or 0)).path
        if policy == "smallest":
            return min(files, key=lambda file_meta: int(getattr(file_meta, "size", 0) or 0)).path
        return files[0].path

    def _set_details(self, text: str) -> None:
        self._details.configure(state="normal")
        self._details.delete("1.0", "end")
        self._details.insert("end", text + "\n")
        self._details.configure(state="disabled")

    def _bind_review_shortcuts(self) -> None:
        self.bind("<space>", lambda e: self._keep_selected_file())
        self.bind("<Delete>", lambda e: self._delete_selected_file())
        self.bind("<Control-Key-a>", lambda e: self._select_all_files())
        self.bind("<Control-Key-d>", lambda e: self._deselect_all_files())

    def _update_keep_selection(self, gid: str) -> None:
        if gid not in self._group_map:
            return
        self._rebuild_keep_menu(gid)
        self._sync_compare_default(gid)
        self._rebuild_compare_menu(gid)
        self._render_group_details(gid)
        self._schedule_hero_refresh()
        self._push_review_slices_to_store()

    def _keep_selected_file(self) -> None:
        if self._compare_path and self._compare_var.get() != _COMPARE_EMPTY:
            current_gid = self._group_var.get()
            if current_gid and current_gid in self._group_map:
                self._keep_map[current_gid] = self._compare_path
                if self._review_controller:
                    self._review_controller.handle_set_keep(current_gid, self._compare_path)
                self._update_keep_selection(current_gid)
                self._set_details(f"Kept: {self._compare_path}")

    def _delete_selected_file(self) -> None:
        if self._compare_path and self._compare_var.get() != _COMPARE_EMPTY:
            current_gid = self._group_var.get()
            if current_gid and current_gid in self._group_map and self._keep_map.get(current_gid) == self._compare_path:
                group = self._group_map[current_gid]
                files = list(getattr(group, "files", []) or [])
                other_files = [file_meta.path for file_meta in files if file_meta.path != self._compare_path]
                if other_files:
                    self._keep_map[current_gid] = other_files[0]
                    if self._review_controller:
                        self._review_controller.handle_set_keep(current_gid, other_files[0])
                    self._update_keep_selection(current_gid)
                    self._set_details(f"Marked for deletion: {self._compare_path}")

    def _select_all_files(self) -> None:
        if self._group_map:
            gids = list(self._group_map.keys())
            self._set_details(f"Selected all {len(gids)} groups")

    def _deselect_all_files(self) -> None:
        self._group_var.set("")
        self._highlight_group_row("")
        self._selection_summary_var.set("No group selected")
        self._clear_compare_ui()
        self._set_details("Deselected all groups")
        self._push_review_slices_to_store()

    def _reset_current_group_keep(self) -> None:
        gid = self._group_var.get()
        if not gid:
            return
        if self._review_controller:
            self._review_controller.handle_clear_keep(gid)
            return
        self._keep_map[gid] = self._default_keep_for_group(self._group_map[gid])
        self._update_keep_selection(gid)
