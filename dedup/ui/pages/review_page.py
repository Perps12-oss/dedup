"""
Review Page — 3-pane duplicate review and deletion workflow.

Layout:
  Top: Provenance Ribbon
  Body:
    Left (3):  Group Navigator (list + filters)
    Center(6): Review Workspace (Table | Gallery | Compare)
    Right (3): Decision & Safety Rail (Smart Rules + Safety Panel)

Refactor Note: Smart Rules moved from Header to Right Rail (Blueprint 5.2).
State filter dropdown removed in favor of Chip filters (Blueprint 3.4).

UI Refactor (v4): Modern visual design pass.
  - Header: icon badge + stacked title block, accent separator, right-aligned mode switcher.
  - View-mode selector: cleaner framed radiobutton group, consistent width.
  - Group Navigator: chip row with active tracking, search bar refinement.
  - Workspace summary band: left/right split info layout, prominent reclaim value.
  - Smart Rules rail: labelled combo, stacked action buttons.
  - Zero-state: centered icon + title + CTA grouping.
  - Confirmation dialog: structured summary table, spacious footer bar.
  - All spacing on 8px grid.
"""

from __future__ import annotations

import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Callable, Optional

from ...engine.models import DeletionPlan, DeletionResult, ScanResult
from ...orchestration.coordinator import ScanCoordinator
from ..components import (
    FilterBar,
    ProvenanceRibbon,
    SafetyPanel,
    SectionCard,
)
from ..components.group_thumbnail_navigator import GroupThumbnailNavigator
from ..components.review_workspace import ReviewWorkspaceStack
from ..controller.review_controller import ReviewController
from ..theme.design_system import font_tuple
from ..utils.formatting import fmt_bytes
from ..utils.icons import IC
from ..viewmodels.review_vm import ReviewVM

_THUMB_SIZE = (64, 64)
REVIEW_NAVIGATOR_MAX_ROWS = 2000


# ---------------------------------------------------------------------------
# Spacing helpers — 8-pt grid
# ---------------------------------------------------------------------------
def _S(n: int) -> int:
    return n * 4


_PAD_PAGE  = _S(6)   # 24px
_PAD_CARD  = _S(4)   # 16px
_GAP_XS    = _S(1)   # 4px
_GAP_SM    = _S(2)   # 8px
_GAP_MD    = _S(4)   # 16px
_GAP_LG    = _S(6)   # 24px
_GAP_XL    = _S(8)   # 32px
_BTN_PAD_X = _S(4)   # 16px
_ROW_H     = _S(9)   # 36px


class ReviewPage(ttk.Frame):
    """Review & deletion planning page."""

    def __init__(
        self,
        parent,
        on_delete_complete: Callable[[DeletionResult], None],
        on_new_scan: Optional[Callable[[], None]] = None,
        on_view_history: Optional[Callable[[], None]] = None,
        review_controller: Optional[ReviewController] = None,
        store=None,
        coordinator: Optional[ScanCoordinator] = None,
        **kwargs,
    ):
        super().__init__(parent, **kwargs)
        self.coordinator        = coordinator
        self.on_delete_complete = on_delete_complete
        self._review_controller = review_controller
        self._store             = store
        self._on_new_scan       = on_new_scan or (lambda: None)
        self._on_view_history   = on_view_history or (lambda: None)
        self.vm                 = ReviewVM()
        self._current_result: Optional[ScanResult] = None
        self._thumbnail_refs: list = []
        self._active_chip_key: str = "all"
        self._ui_mode: str         = "simple"
        self._build()

    # --- IReviewCallbacks: public contract for ReviewController ---
    def get_current_result(self):
        return self._current_result

    def set_preview_result(self, msg: str) -> None:
        self._safety_panel.set_dry_run_result(msg)

    def refresh_review_ui(self) -> None:
        self._sync_review_from_store_and_refresh()

    def confirm_deletion(self, plan, prev: dict) -> str:
        return self._show_delete_confirmation(plan, prev)

    def on_execute_start(self) -> None:
        self._safety_panel._delete_btn.configure(state="disabled", text="Executing…")
        if hasattr(self, "_workspace_delete_btn"):
            self._workspace_delete_btn.configure(state="disabled", text="Executing…")
        self.update()

    def on_execute_done(self, result) -> None:
        self._on_execute_done(result)

    # ----------------------------------------------------------------
    # Build
    # ----------------------------------------------------------------
    def _build(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        # ── Page Header ────────────────────────────────────────────────
        hdr = ttk.Frame(self, padding=(_PAD_PAGE, _GAP_LG, _PAD_PAGE, _GAP_MD))
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.columnconfigure(1, weight=1)

        # Accent badge
        badge = ttk.Frame(hdr, style="Accent.TFrame", padding=(_GAP_SM, _GAP_XS, _GAP_SM, _GAP_XS))
        badge.grid(row=0, column=0, rowspan=2, sticky="ns", padx=(0, _GAP_MD))
        ttk.Label(
            badge,
            text=IC.REVIEW,
            style="Accent.TLabel",
            font=font_tuple("section_title"),
        ).pack()

        # Title block
        title_block = ttk.Frame(hdr)
        title_block.grid(row=0, column=1, sticky="w")
        ttk.Label(
            title_block,
            text="Decision Studio",
            font=font_tuple("page_title"),
        ).pack(side="top", anchor="w")
        ttk.Label(
            title_block,
            text="Groups  ·  Workspace  ·  Decision & Safety",
            style="Muted.TLabel",
            font=font_tuple("page_subtitle"),
        ).pack(side="top", anchor="w", pady=(_GAP_XS, 0))

        # State hint
        self._state_hint = tk.StringVar(
            value="No review data yet. Run a scan, then return here to make decisions."
        )
        ttk.Label(
            hdr,
            textvariable=self._state_hint,
            style="Muted.TLabel",
            font=font_tuple("caption"),
        ).grid(row=1, column=1, sticky="w", pady=(_GAP_XS, 0))

        # View-mode segmented control — framed group of radiobuttons, right-aligned
        self._mode_var = tk.StringVar(value="table")
        mode_frame = ttk.Frame(
            hdr, style="Card.TFrame", padding=(_GAP_XS, _GAP_XS, _GAP_XS, _GAP_XS)
        )
        mode_frame.grid(row=0, column=2, rowspan=2, sticky="e", padx=(_GAP_MD, 0))
        self._compare_mode_rb: Optional[ttk.Radiobutton] = None
        for label, val in [("⊞ Table", "table"), ("⊟ Gallery", "gallery"), ("⧉ Compare", "compare")]:
            rb = ttk.Radiobutton(
                mode_frame,
                text=label,
                variable=self._mode_var,
                value=val,
                command=self._on_mode_change,
                width=10,
            )
            rb.pack(side="left", padx=(_GAP_XS, _GAP_XS), ipady=_GAP_XS)
            if val == "compare":
                self._compare_mode_rb = rb

        # Thin accent separator beneath header
        ttk.Separator(self, orient="horizontal").grid(
            row=0, column=0, sticky="ews", padx=_PAD_PAGE,
        )

        # ── Provenance ribbon ──────────────────────────────────────────
        self._prov = ProvenanceRibbon(self)
        self._prov.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=_PAD_PAGE,
            pady=(_GAP_XS, _GAP_MD),
        )

        # ── 3-pane body ────────────────────────────────────────────────
        body = ttk.Frame(self)
        body.grid(row=2, column=0, sticky="nsew", padx=_PAD_PAGE, pady=(0, _PAD_PAGE))
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1, minsize=110)
        body.columnconfigure(1, weight=2, minsize=220)
        body.columnconfigure(2, weight=1, minsize=110)

        # Left: Group Navigator
        left = SectionCard(body, title=f"{IC.GROUPS}  Group Navigator")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, _GAP_MD))
        self._build_group_navigator(left.body)

        # Center: Workspace
        center = SectionCard(body, title=f"{IC.REVIEW}  Workspace")
        center.grid(row=0, column=1, sticky="nsew", padx=(0, _GAP_MD))
        self._build_workspace(center.body)

        # Right: Decision & Safety Rail
        right_frame = ttk.Frame(body)
        right_frame.grid(row=0, column=2, sticky="nsew")
        right_frame.rowconfigure(1, weight=1)
        right_frame.columnconfigure(0, weight=1)

        smart_card = SectionCard(right_frame, title=f"{IC.SETTINGS}  Smart Rules")
        smart_card.grid(row=0, column=0, sticky="ew", pady=(0, _GAP_MD))
        self._build_smart_rules_rail(smart_card.body)

        self._safety_panel = SafetyPanel(
            right_frame,
            on_dry_run=self._on_preview_intent,
            on_execute=self._on_execute_intent,
            on_undo_hint=self._on_undo_hint,
        )
        self._safety_panel.grid(row=1, column=0, sticky="nsew")

        # ── Zero-state panel ───────────────────────────────────────────
        self._zero_panel = ttk.Frame(
            self,
            style="Panel.TFrame",
            padding=(_PAD_PAGE, _GAP_LG, _PAD_PAGE, _GAP_LG),
        )
        self._zero_panel.grid(row=3, column=0, sticky="ew", padx=_PAD_PAGE, pady=(0, _PAD_PAGE))
        self._zero_panel.columnconfigure(0, weight=1)

        # Icon + title + subtitle + CTA — stacked, left-aligned
        ttk.Label(
            self._zero_panel,
            text="✓",
            style="Panel.Success.TLabel",
            font=font_tuple("page_title"),
        ).grid(row=0, column=0, sticky="w", pady=(0, _GAP_XS))
        self._zero_title = ttk.Label(
            self._zero_panel,
            text="All clear",
            style="Panel.Success.TLabel",
            font=font_tuple("section_title"),
        )
        self._zero_title.grid(row=1, column=0, sticky="w")
        ttk.Label(
            self._zero_panel,
            text="No duplicates found in your last scan. Ready to scan again?",
            style="Muted.TLabel",
            font=font_tuple("body"),
        ).grid(row=2, column=0, sticky="w", pady=(_GAP_XS, _GAP_MD))
        zbtn = ttk.Frame(self._zero_panel, style="Panel.TFrame")
        zbtn.grid(row=3, column=0, sticky="w")
        ttk.Button(
            zbtn,
            text="New Scan",
            style="Accent.TButton",
            command=self._on_new_scan,
        ).pack(side="left", padx=(0, _GAP_SM))
        ttk.Button(
            zbtn,
            text="View History",
            style="Ghost.TButton",
            command=self._on_view_history,
        ).pack(side="left")
        self._zero_panel.grid_remove()

        # Keyboard shortcut bindings
        self._bind_key_next        = lambda e: self._on_key_next_group()
        self._bind_key_prev        = lambda e: self._on_key_prev_group()
        self._bind_key_down        = lambda e: self._on_key_arrow_down(e)
        self._bind_key_up          = lambda e: self._on_key_arrow_up(e)
        self._bind_key_return      = lambda e: self._on_key_activate_group(e)
        self._bind_mode_gallery    = lambda e: self._set_mode_shortcut("gallery")
        self._bind_mode_table      = lambda e: self._set_mode_shortcut("table")
        self._bind_mode_compare    = lambda e: self._set_mode_shortcut("compare")
        self._bind_quick_look      = lambda e: self._quick_look()
        self._bind_execute         = lambda e: self._on_execute_intent()
        self._bind_set_keep        = lambda e: self._set_keep_selected()
        self._bind_clear_keep      = lambda e: self._on_clear_keep()
        self._bind_preview         = lambda e: self._on_preview_intent()
        self._bind_undo_hint       = lambda e: self._on_undo_hint()
        self._bind_apply_smart     = lambda e: self._on_apply_smart_rule_intent()
        self._bind_compare_prev    = lambda e: self._run_if_compare_allowed(self._workspace.compare_prev)
        self._bind_compare_next    = lambda e: self._run_if_compare_allowed(self._workspace.compare_next)
        self._bind_quick_compare   = lambda e: self._run_if_compare_allowed(
            self._workspace.open_quick_compare_overlay
        )

    # ----------------------------------------------------------------
    # Sub-builders
    # ----------------------------------------------------------------
    def _build_group_navigator(self, body: ttk.Frame):
        body.columnconfigure(0, weight=1)
        body.rowconfigure(4, weight=1)

        # Search bar
        self._filter_bar = FilterBar(
            body,
            on_search=self._on_search,
            filters=[],
            style="Panel.TFrame",
        )
        self._filter_bar.grid(row=0, column=0, sticky="ew", pady=(0, _GAP_SM))

        # ── State-filter chips ─────────────────────────────────────────
        chips = ttk.Frame(body, style="Panel.TFrame")
        chips.grid(row=1, column=0, sticky="ew", pady=(0, _GAP_MD))
        self._chip_vars: dict[str, tk.StringVar]     = {}
        self._chip_buttons: dict[str, ttk.Button]    = {}
        chip_specs = [
            ("unresolved", "Unresolved"),
            ("ready",      "Ready"),
            ("warning",    "Warning"),
            ("skipped",    "Skipped"),
            ("all",        "All"),
        ]
        for i, (state_key, label) in enumerate(chip_specs):
            chips.columnconfigure(i, weight=1)
            var           = tk.StringVar(value=label)
            initial_style = "Accent.TButton" if state_key == "all" else "Ghost.TButton"
            btn = ttk.Button(
                chips,
                textvariable=var,
                style=initial_style,
                command=lambda s=state_key: self._set_state_filter(s),
            )
            btn.grid(
                row=0,
                column=i,
                sticky="ew",
                padx=(0, _GAP_XS) if i < len(chip_specs) - 1 else 0,
                ipady=_GAP_XS,
            )
            self._chip_vars[state_key]    = var
            self._chip_buttons[state_key] = btn

        # ── Sort row ───────────────────────────────────────────────────
        sort_row = ttk.Frame(body, style="Panel.TFrame")
        sort_row.grid(row=2, column=0, sticky="ew", pady=(0, _GAP_SM))
        ttk.Label(
            sort_row,
            text="Sort:",
            style="Panel.Muted.TLabel",
            font=font_tuple("caption"),
        ).pack(side="left")
        self._sort_var = tk.StringVar(value="priority")
        sort = ttk.Combobox(
            sort_row,
            state="readonly",
            width=18,
            textvariable=self._sort_var,
            values=["priority", "reclaimable size", "file count", "confidence"],
        )
        sort.pack(side="left", padx=(_GAP_SM, 0))
        sort.bind("<<ComboboxSelected>>", self._on_sort_change)

        # Group count label
        self._group_count_var = tk.StringVar(value="0 groups")
        ttk.Label(
            body,
            textvariable=self._group_count_var,
            style="Panel.Muted.TLabel",
            font=font_tuple("caption"),
        ).grid(row=3, column=0, sticky="w", pady=(0, _GAP_XS))

        # Thumbnail navigator (virtualized)
        self._group_nav = GroupThumbnailNavigator(
            body,
            on_select=self._dispatch_group_select,
            resolve_duplicate_group=self._resolve_duplicate_group_for_nav,
        )
        self._group_nav.grid(row=4, column=0, sticky="nsew")
        body.rowconfigure(4, weight=1)

    def _build_workspace(self, body: ttk.Frame):
        body.columnconfigure(0, weight=1)
        body.rowconfigure(2, weight=1)

        # ── Primary DELETE — full width, prominent ─────────────────────
        self._workspace_delete_btn = ttk.Button(
            body,
            text="DELETE — select keep files to enable",
            style="Danger.TButton",
            command=self._on_execute_intent,
            state="disabled",
        )
        self._workspace_delete_btn.grid(
            row=0, column=0, sticky="ew", pady=(0, _GAP_MD), ipady=_GAP_MD
        )

        # ── Summary band ──────────────────────────────────────────────
        band = ttk.Frame(
            body,
            style="Panel.TFrame",
            padding=(_GAP_MD, _GAP_SM, _GAP_MD, _GAP_SM),
        )
        band.grid(row=1, column=0, sticky="ew", pady=(0, _GAP_MD))
        band.columnconfigure(0, weight=1)
        band.columnconfigure(1, weight=0)

        self._group_summary_var = tk.StringVar(value="No group selected")
        self._group_reason_var  = tk.StringVar(value="Reason: —")
        self._group_keep_var    = tk.StringVar(value="Keep: not selected")
        self._group_reclaim_var = tk.StringVar(value="Reclaimable: —")
        self._group_rule_var    = tk.StringVar(value="Rule: off")

        # Left: group name + reason
        left_info = ttk.Frame(band, style="Panel.TFrame")
        left_info.grid(row=0, column=0, sticky="w")
        ttk.Label(
            left_info,
            textvariable=self._group_summary_var,
            style="Panel.Secondary.TLabel",
            font=font_tuple("body_bold"),
        ).pack(side="top", anchor="w")
        ttk.Label(
            left_info,
            textvariable=self._group_reason_var,
            style="Panel.Muted.TLabel",
            font=font_tuple("caption"),
        ).pack(side="top", anchor="w", pady=(_GAP_XS, 0))

        # Right: keep · reclaim · rule pills
        right_info = ttk.Frame(band, style="Panel.TFrame")
        right_info.grid(row=0, column=1, sticky="e", padx=(_GAP_LG, 0))
        ttk.Label(
            right_info,
            textvariable=self._group_keep_var,
            style="Panel.TLabel",
            font=font_tuple("caption"),
        ).pack(side="top", anchor="e")
        ttk.Label(
            right_info,
            textvariable=self._group_reclaim_var,
            style="Panel.Success.TLabel",
            font=font_tuple("caption"),
        ).pack(side="top", anchor="e", pady=(_GAP_XS, 0))
        ttk.Label(
            right_info,
            textvariable=self._group_rule_var,
            style="Panel.Accent.TLabel",
            font=font_tuple("caption"),
        ).pack(side="top", anchor="e", pady=(_GAP_XS, 0))

        # Workspace stack (Table / Gallery / Compare)
        self._workspace = ReviewWorkspaceStack(
            body,
            on_keep=self._on_set_keep,
            on_clear_keep=self._on_clear_keep,
        )
        self._workspace.grid(row=2, column=0, sticky="nsew")

    def _build_smart_rules_rail(self, body: ttk.Frame):
        """Smart Rules section of the Right Rail (Blueprint 5.2)."""
        body.columnconfigure(0, weight=1)

        # Rule selector label + combo
        ttk.Label(
            body,
            text="Auto-Select Rule",
            style="Panel.Muted.TLabel",
            font=font_tuple("data_label"),
        ).grid(row=0, column=0, sticky="w", pady=(0, _GAP_XS))
        self._smart_rule_var   = tk.StringVar(value="newest")
        self._smart_rule_combo = ttk.Combobox(
            body,
            textvariable=self._smart_rule_var,
            state="readonly",
            values=["newest", "oldest", "largest", "smallest", "first"],
        )
        self._smart_rule_combo.grid(row=1, column=0, sticky="ew", pady=(0, _GAP_MD))

        # Help text
        ttk.Label(
            body,
            text=(
                "One protected file per duplicate group — others can be deleted. "
                "Manual picks in Table / Gallery / Compare override Smart Select."
            ),
            style="Panel.Muted.TLabel",
            font=font_tuple("caption"),
            wraplength=220,
        ).grid(row=2, column=0, sticky="w", pady=(0, _GAP_SM))

        # Action buttons — full-width stacked
        ttk.Button(
            body,
            text="Apply to Group",
            style="Accent.TButton",
            command=self._on_apply_smart_rule_intent,
        ).grid(row=3, column=0, sticky="ew", pady=(0, _GAP_XS))
        ttk.Button(
            body,
            text="Reset defaults",
            style="Ghost.TButton",
            command=self._on_clear_smart_rule_intent,
        ).grid(row=4, column=0, sticky="ew")

        # Active rule status — spaced below actions
        self._active_rule_var = tk.StringVar(value="Smart Rule: off")
        ttk.Label(
            body,
            textvariable=self._active_rule_var,
            style="Panel.Accent.TLabel",
            font=font_tuple("caption"),
        ).grid(row=5, column=0, sticky="w", pady=(_GAP_MD, 0))

    # ----------------------------------------------------------------
    # Public
    # ----------------------------------------------------------------
    def set_ui_mode(self, mode: str) -> None:
        """Simple mode hides Compare and blocks compare shortcuts."""
        self._ui_mode = mode if mode in ("simple", "advanced") else "simple"
        adv = self._ui_mode == "advanced"
        if self._compare_mode_rb is not None:
            if adv:
                self._compare_mode_rb.pack(side="left", padx=(_GAP_XS, _GAP_XS), ipady=_GAP_XS)
            else:
                self._compare_mode_rb.pack_forget()
        if not adv and (self._mode_var.get() or "") == "compare":
            self._mode_var.set("table")
            self._on_mode_change()

    def _run_if_compare_allowed(self, fn: Callable[[], None]) -> None:
        if self._ui_mode != "advanced" or not self.winfo_viewable():
            return
        fn()

    def load_result(self, result: ScanResult):
        self._current_result = result
        self.vm.load_result(result)
        if not result.duplicate_groups:
            self._state_hint.set("All clear. No duplicates found in this scan.")
            self._zero_panel.grid()
        else:
            self._state_hint.set("Review unresolved groups, preview impact, then execute safely.")
            self._zero_panel.grid_remove()
        if self._store:
            from ..state.store import ReviewSelectionState

            self._store.set_review_selection(
                ReviewSelectionState(
                    keep_selections=dict(self.vm.keep_selections),
                    selected_group_id=self.vm.selected_group_id,
                )
            )
        self._prov.update(
            session_id=getattr(
                self.vm.session,
                "session_id",
                result.scan_id if result else "",
            ),
            verification=getattr(self.vm.current_group, "verification_level", "full")
            if self.vm.groups
            else "full",
            groups=self.vm.total_groups,
            reclaimable_bytes=self.vm.reclaimable_bytes,
        )
        self._refresh_group_list()
        self._update_filter_chip_labels()
        self._push_deletion_plan_ui()

    def on_show(self):
        self.bind_all("<Control-Right>",   self._bind_key_next,      add="+")
        self.bind_all("<Control-Left>",    self._bind_key_prev,      add="+")
        self.bind_all("<Key-g>",           self._bind_mode_gallery,  add="+")
        self.bind_all("<Key-t>",           self._bind_mode_table,    add="+")
        self.bind_all("<Key-c>",           self._bind_mode_compare,  add="+")
        self.bind_all("<space>",           self._bind_quick_look,    add="+")
        self.bind_all("<Control-Return>",  self._bind_execute,       add="+")
        self.bind_all("<Key-k>",           self._bind_set_keep,      add="+")
        self.bind_all("<Key-K>",           self._bind_clear_keep,    add="+")
        self.bind_all("<Key-p>",           self._bind_preview,       add="+")
        self.bind_all("<Key-u>",           self._bind_undo_hint,     add="+")
        self.bind_all("<Key-a>",           self._bind_apply_smart,   add="+")
        self.bind_all("<Key-bracketleft>", self._bind_compare_prev,  add="+")
        self.bind_all("<Key-bracketright>",self._bind_compare_next,  add="+")
        self.bind_all("<Key-x>",           self._bind_quick_compare, add="+")
        self.bind_all("<Down>",            self._bind_key_down,      add="+")
        self.bind_all("<Up>",              self._bind_key_up,        add="+")
        self.bind_all("<Return>",          self._bind_key_return,    add="+")

    def on_hide(self):
        self.unbind_all("<Control-Right>")
        self.unbind_all("<Control-Left>")
        self.unbind_all("<Key-g>")
        self.unbind_all("<Key-t>")
        self.unbind_all("<Key-c>")
        self.unbind_all("<space>")
        self.unbind_all("<Control-Return>")
        self.unbind_all("<Key-k>")
        self.unbind_all("<Key-K>")
        self.unbind_all("<Key-p>")
        self.unbind_all("<Key-u>")
        self.unbind_all("<Key-a>")
        self.unbind_all("<Key-bracketleft>")
        self.unbind_all("<Key-bracketright>")
        self.unbind_all("<Key-x>")
        self.unbind_all("<Down>")
        self.unbind_all("<Up>")
        self.unbind_all("<Return>")

    # ----------------------------------------------------------------
    # Group navigator
    # ----------------------------------------------------------------
    def _resolve_duplicate_group_for_nav(self, group_id: str):
        if not self._current_result:
            return None
        return next(
            (g for g in self._current_result.duplicate_groups if g.group_id == group_id),
            None,
        )

    def _push_deletion_plan_ui(self) -> None:
        self._safety_panel.update_plan(
            del_count=self.vm.delete_count,
            keep_count=self.vm.keep_count,
            reclaim_bytes=self.vm.reclaimable_bytes,
            risk_flags=self.vm.risk_flags,
        )
        self._sync_workspace_delete_btn()

    def _sync_workspace_delete_btn(self) -> None:
        if not hasattr(self, "_workspace_delete_btn"):
            return
        dc = self.vm.delete_count
        try:
            rb = int(self.vm.reclaimable_bytes)
        except (TypeError, ValueError):
            rb = 0
        try:
            dc = int(dc)
        except (TypeError, ValueError):
            dc = 0
        if dc > 0:
            self._workspace_delete_btn.configure(
                state="normal",
                text=f"DELETE — remove {dc} duplicate file(s) ({fmt_bytes(rb)})",
            )
        else:
            self._workspace_delete_btn.configure(
                state="disabled",
                text="DELETE — select keep files to enable",
            )

    def _should_skip_keyboard_nav(self, event) -> bool:
        w = getattr(event, "widget", None)
        if w is None:
            return False
        if isinstance(w, (tk.Text, tk.Entry, tk.Listbox)):
            return True
        if isinstance(w, (ttk.Entry, ttk.Combobox)):
            return True
        return False

    def _refresh_group_list(self):
        from ..components.decision_state import get_group_decision_state

        groups  = self.vm.filtered_groups
        total   = len(groups)
        display = groups if total <= REVIEW_NAVIGATOR_MAX_ROWS else groups[:REVIEW_NAVIGATOR_MAX_ROWS]
        if total > REVIEW_NAVIGATOR_MAX_ROWS:
            self._group_count_var.set(
                f"Showing first {REVIEW_NAVIGATOR_MAX_ROWS} of {total} groups"
            )
        else:
            self._group_count_var.set(f"{total} group{'s' if total != 1 else ''}")
        self._group_nav.set_groups(
            display,
            self.vm.selected_group_id,
            lambda gid, risky: get_group_decision_state(gid, self.vm.keep_selections, risky),
        )
        self._update_filter_chip_labels()

    def _dispatch_group_select(self, group_id: str) -> None:
        self._on_group_select(group_id)

    def _select_group_in_navigator(self, group_id: str) -> None:
        self._group_nav.scroll_to_group_id(group_id)

    def _on_search(self, text: str):
        self.vm.filter_text = text
        self._refresh_group_list()

    def _on_state_filter_change(self, *_):
        # No longer needed (chips replaced dropdown) — kept for compatibility.
        pass

    def _set_state_filter(self, state_key: str) -> None:
        prev = self._active_chip_key
        self._active_chip_key = state_key
        # Update chip button styles
        for key, btn in self._chip_buttons.items():
            btn.configure(style="Accent.TButton" if key == state_key else "Ghost.TButton")
        self.vm.state_filter = state_key
        self._refresh_group_list()

    def _update_filter_chip_labels(self) -> None:
        counts = getattr(self.vm, "state_filter_counts", None) or {}
        for key, var in self._chip_vars.items():
            display = key.title() if key != "all" else "All"
            count   = counts.get(key)
            if count is not None:
                var.set(f"{display} ({count})")
            else:
                var.set(display)

    def _on_sort_change(self, *_):
        self.vm.sort_key = self._sort_var.get()
        self._refresh_group_list()

    def _on_mode_change(self) -> None:
        mode = self._mode_var.get()
        self._workspace.set_mode(mode)

    def _set_mode_shortcut(self, mode: str) -> None:
        if mode == "compare" and self._ui_mode != "advanced":
            return
        self._mode_var.set(mode)
        self._on_mode_change()

    def _on_group_select(self, group_id: str) -> None:
        self.vm.selected_group_id = group_id
        self._select_group_in_navigator(group_id)
        self._load_workspace(group_id)
        self._update_workspace_summary()
        if self._store:
            from ..state.store import ReviewSelectionState

            self._store.set_review_selection(
                ReviewSelectionState(
                    keep_selections=dict(self.vm.keep_selections),
                    selected_group_id=group_id,
                )
            )

    def _load_workspace(self, group_id: str) -> None:
        if not self._current_result:
            return
        group = next(
            (g for g in self._current_result.duplicate_groups if g.group_id == group_id),
            None,
        )
        if group is None:
            return
        keep_path = self.vm.keep_selections.get(group_id)
        self._workspace.load_group(group, keep_path=keep_path)

    def _on_set_keep(self, group_id: str, file_path: str) -> None:
        if self._review_controller:
            self._review_controller.handle_set_keep(group_id, file_path)
            return
        self.vm.keep_selections[group_id] = file_path
        self._update_workspace_summary()
        self._push_deletion_plan_ui()
        self._refresh_group_list()

    def _on_clear_keep(self) -> None:
        gid = self.vm.selected_group_id
        if not gid:
            return
        if self._review_controller:
            self._review_controller.handle_clear_keep(gid)
            return
        self.vm.keep_selections.pop(gid, None)
        self._update_workspace_summary()
        self._push_deletion_plan_ui()
        self._refresh_group_list()

    def _set_keep_selected(self) -> None:
        gid = self.vm.selected_group_id
        if gid:
            self._workspace.set_keep_selected(gid)

    def _quick_look(self) -> None:
        gid = self.vm.selected_group_id
        if gid:
            self._workspace.open_quick_look(gid)

    def _update_workspace_summary(self) -> None:
        group = self.vm.current_group
        if group is None:
            self._group_summary_var.set("No group selected")
            self._group_reason_var.set("Reason: —")
            self._group_keep_var.set("Keep: not selected")
            self._group_reclaim_var.set("Reclaimable: —")
            self._group_rule_var.set("Rule: off")
            return
        gid       = group.group_id
        keep_path = self.vm.keep_selections.get(gid)
        name      = Path(keep_path).name if keep_path else "not selected"
        reclaim   = fmt_bytes(sum(f.size for f in group.files[1:]) if group.files else 0)
        self._group_summary_var.set(f"Group {gid[:8]}…  ·  {len(group.files)} files")
        self._group_reason_var.set(f"Reason: {getattr(group, 'reason', '—')}")
        self._group_keep_var.set(f"Keep: {name}")
        self._group_reclaim_var.set(f"Reclaimable: {reclaim}")
        rule = self._smart_rule_var.get() if hasattr(self, "_smart_rule_var") else "off"
        self._group_rule_var.set(f"Rule: {rule}")

    def _on_key_next_group(self) -> None:
        self.vm.select_next_group()
        gid = self.vm.selected_group_id
        if gid:
            self._dispatch_group_select(gid)

    def _on_key_prev_group(self) -> None:
        self.vm.select_prev_group()
        gid = self.vm.selected_group_id
        if gid:
            self._dispatch_group_select(gid)

    def _on_key_arrow_down(self, event) -> None:
        if self._should_skip_keyboard_nav(event):
            return
        self._on_key_next_group()

    def _on_key_arrow_up(self, event) -> None:
        if self._should_skip_keyboard_nav(event):
            return
        self._on_key_prev_group()

    def _on_key_activate_group(self, event) -> None:
        if self._should_skip_keyboard_nav(event):
            return
        gid = self.vm.selected_group_id
        if gid:
            self._load_workspace(gid)

    # ----------------------------------------------------------------
    # Smart Rules
    # ----------------------------------------------------------------
    def _on_apply_smart_rule_intent(self) -> None:
        rule = self._smart_rule_var.get()
        if self._review_controller:
            self._review_controller.handle_apply_smart_rule(rule)
            return
        if not self._current_result:
            return
        from ..utils.review_keep import apply_smart_rule

        keep_map: dict = {}
        for g in self._current_result.duplicate_groups:
            k = apply_smart_rule(g, rule)
            if k:
                keep_map[g.group_id] = k.path
        self.vm.keep_selections = keep_map
        self._refresh_group_list()
        gid = self.vm.selected_group_id
        if gid:
            self._load_workspace(gid)
        self._push_deletion_plan_ui()
        self._active_rule_var.set(f"Smart Rule: {rule} (active)")

    def _on_clear_smart_rule_intent(self) -> None:
        if self._review_controller:
            self._review_controller.handle_clear_all_keeps()
        else:
            from ..utils.review_keep import default_keep_map_from_result

            self.vm.keep_selections = (
                default_keep_map_from_result(self._current_result)
                if self._current_result
                else {}
            )
            self._refresh_group_list()
            gid = self.vm.selected_group_id
            if gid:
                self._load_workspace(gid)
            self._push_deletion_plan_ui()
        self._active_rule_var.set("Smart Rule: off")

    # ----------------------------------------------------------------
    # Store sync helpers (unchanged logic)
    # ----------------------------------------------------------------
    def _sync_review_from_store_and_refresh(self) -> None:
        if self._store and self._current_result:
            from ..state.selectors import review_selection

            sel = review_selection(self._store.state)
            if sel:
                self.vm.keep_selections  = dict(sel.keep_selections or {})
                self.vm.selected_group_id = sel.selected_group_id or ""
        self._refresh_group_list()
        gid = self.vm.selected_group_id
        if gid:
            self._load_workspace(gid)
        self._update_workspace_summary()
        self._push_deletion_plan_ui()

    def _on_preview_intent(self) -> None:
        if self._review_controller:
            self._review_controller.handle_preview_deletion()
            return
        self._on_dry_run()

    def _on_execute_intent(self) -> None:
        if self._review_controller:
            self._review_controller.handle_execute_deletion()
            return
        self._on_execute()

    def _on_undo_hint(self) -> None:
        messagebox.showinfo(
            "Undo",
            "Files are moved to Trash, not permanently deleted.\n"
            "Open your system Trash to restore them.",
        )

    # ----------------------------------------------------------------
    # Deletion helpers (logic unchanged)
    # ----------------------------------------------------------------
    def _create_plan(self) -> Optional[DeletionPlan]:
        if not self._current_result or not self.coordinator:
            return None
        return self.coordinator.create_deletion_plan(
            self._current_result,
            keep_strategy="first",
            group_keep_paths=self.vm.keep_selections or None,
        )

    def _on_dry_run(self):
        if self._review_controller:
            self._review_controller.handle_preview_deletion()
            return
        plan = self._create_plan()
        if not plan or not plan.groups:
            self._safety_panel.set_dry_run_result("No files selected.")
            return
        try:
            from ...engine.deletion import preview_deletion

            prev = preview_deletion(plan)
            self._safety_panel.set_dry_run_result(
                f"Preview Effects: {prev['total_files']} files → {prev['human_readable_size']}"
            )
        except Exception as e:
            self._safety_panel.set_dry_run_result(f"Error: {e}")

    # ----------------------------------------------------------------
    # Confirmation dialog
    # ----------------------------------------------------------------
    def _show_delete_confirmation(self, plan: DeletionPlan, prev: dict) -> str:
        """
        Confirmation dialog.
        Structure:
          - Spacious header (title + sub-line)
          - Two-column summary table
          - Horizontal divider
          - Footer bar: Cancel | Preview Effects → DELETE
        """
        result = {"choice": "cancel"}
        root   = self.winfo_toplevel()
        dlg    = tk.Toplevel(root)
        dlg.title("Confirm Deletion")
        dlg.transient(root)
        dlg.grab_set()
        dlg.resizable(False, False)

        outer = ttk.Frame(dlg, padding=(_GAP_LG, _GAP_LG, _GAP_LG, 0))
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(1, weight=1)

        # Dialog title
        ttk.Label(
            outer,
            text="⚠  Confirm Deletion",
            font=font_tuple("section_title"),
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, _GAP_XS))
        ttk.Label(
            outer,
            text="Review the summary below before proceeding. Files will be moved to Trash.",
            style="Muted.TLabel",
            font=font_tuple("body"),
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, _GAP_LG))

        # Summary rows — right-aligned key / left-aligned value
        total_files = prev.get("total_files", "?")
        human_size  = prev.get("human_readable_size", "?")
        rows = [
            ("Files to delete",    str(total_files)),
            ("Files kept",         str(self.vm.keep_count)),
            ("Duplicate groups",   str(len(plan.groups))),
            ("Reclaimable space",  str(human_size)),
            ("Delete mode",        "Trash"),
            ("Revalidation",       "ON"),
            ("Audit logging",      "ACTIVE"),
        ]
        for r_idx, (key, val) in enumerate(rows):
            base_row = r_idx + 2
            ttk.Label(
                outer,
                text=key,
                style="Muted.TLabel",
                font=font_tuple("body"),
                anchor="e",
                width=20,
            ).grid(row=base_row, column=0, sticky="e", padx=(0, _GAP_MD), pady=(_GAP_XS, 0))
            ttk.Label(
                outer,
                text=val,
                font=font_tuple("body_bold"),
                anchor="w",
            ).grid(row=base_row, column=1, sticky="w", pady=(_GAP_XS, 0))

        # Divider
        ttk.Separator(dlg, orient="horizontal").pack(fill="x", padx=_GAP_LG, pady=(_GAP_LG, 0))

        # Footer — Cancel / Preview  ←→  DELETE
        def _done(choice: str):
            result["choice"] = choice
            dlg.grab_release()
            dlg.destroy()

        footer = ttk.Frame(dlg, padding=(_GAP_LG, _GAP_SM, _GAP_LG, _GAP_MD))
        footer.pack(fill="x")
        ttk.Button(
            footer,
            text="Cancel",
            command=lambda: _done("cancel"),
        ).pack(side="left")
        ttk.Button(
            footer,
            text="Preview Effects",
            style="Ghost.TButton",
            command=lambda: _done("preview"),
        ).pack(side="left", padx=(_GAP_SM, 0))
        ttk.Button(
            footer,
            text="DELETE",
            style="Danger.TButton",
            command=lambda: _done("delete"),
        ).pack(side="right")

        dlg.wait_window(dlg)
        return result["choice"]

    # ----------------------------------------------------------------
    # Execute
    # ----------------------------------------------------------------
    def _on_execute(self):
        if self._review_controller:
            self._review_controller.handle_execute_deletion()
            return
        plan = self._create_plan()
        if not plan or not plan.groups:
            messagebox.showinfo("Delete", "No files selected for deletion.")
            return
        try:
            from ...engine.deletion import preview_deletion

            prev = preview_deletion(plan)
        except Exception:
            prev = {"total_files": "?", "human_readable_size": "?"}
        choice = self._show_delete_confirmation(plan, prev)
        if choice == "cancel":
            return
        if choice == "preview":
            self._on_dry_run()
            return
        self._safety_panel._delete_btn.configure(state="disabled", text="Executing…")
        if hasattr(self, "_workspace_delete_btn"):
            self._workspace_delete_btn.configure(state="disabled", text="Executing…")
        self.update()
        result = self.coordinator.execute_deletion(plan)
        self._safety_panel._delete_btn.configure(state="normal", text="DELETE")
        if hasattr(self, "_workspace_delete_btn"):
            self._sync_workspace_delete_btn()
        self._on_execute_done(result)
        if result.failed_files:
            messagebox.showwarning(
                "Deletion Complete",
                f"Deleted: {len(result.deleted_files)}\nFailed: {len(result.failed_files)}",
            )
        else:
            messagebox.showinfo(
                "Deletion Complete",
                f"Deleted {len(result.deleted_files)} files.",
            )

    def _on_execute_done(self, result: DeletionResult) -> None:
        self.on_delete_complete(result)
        if self._current_result:
            surviving = [
                g for g in self._current_result.duplicate_groups
                if g.group_id not in {grp.group_id for grp in result.deleted_groups or []}
            ]
            self._current_result.duplicate_groups = surviving
        self.vm.keep_selections = {}
        self._refresh_group_list()
        self._push_deletion_plan_ui()
        self._state_hint.set(
            f"Cleanup complete — {len(result.deleted_files)} file(s) moved to Trash."
        )