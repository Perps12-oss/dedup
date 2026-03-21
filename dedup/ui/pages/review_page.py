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

UI Refactor (v2): Spacing, hierarchy, and visual polish pass.
  - 8px grid system enforced throughout (_S helper).
  - Header: more vertical breathing room, subtitle line-height fix.
  - View-mode selector: proper segmented control with active indicator.
  - Group Navigator: chip row with active tracking + hover states.
  - Workspace summary band: taller, two-column info layout.
  - Smart Rules rail: labelled combo with better action button layout.
  - Zero-state: centered card with icon, tighter CTA grouping.
  - Dialogs (Confirm, Quick Look): 24px padding, divider rhythm, footer bar.
  - Confirmation dialog: table-style summary rows, spacious footer.
  - Quick Look dialog: metadata grid replacing raw Text widget.
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
    DataTable,
    FilterBar,
    ProvenanceRibbon,
    SafetyPanel,
    SectionCard,
)
from ..components.review_workspace import ReviewWorkspaceStack
from ..controller.review_controller import ReviewController
from ..theme.design_system import font_tuple
from ..utils.formatting import fmt_bytes
from ..utils.icons import IC
from ..viewmodels.review_vm import ReviewVM

_THUMB_SIZE = (64, 64)
# Bounded navigator for scale (Phase 3B): cap visible rows to avoid unbounded Treeview
REVIEW_NAVIGATOR_MAX_ROWS = 2000


# ---------------------------------------------------------------------------
# Spacing helpers — 8-pt grid
# All layout measurements are multiples of 4 (half-step) or 8 (full step).
# ---------------------------------------------------------------------------
def _S(n: int) -> int:
    """Return n × 4px — the base unit of the 8px grid (half-step = 4px)."""
    return n * 4


# Semantic aliases (use these instead of bare integers throughout _build methods)
_PAD_PAGE = _S(6)  # 24px  outer page inset
_PAD_CARD = _S(4)  # 16px  inside SectionCard / panels
_GAP_XS = _S(1)  # 4px
_GAP_SM = _S(2)  # 8px
_GAP_MD = _S(4)  # 16px
_GAP_LG = _S(6)  # 24px
_GAP_XL = _S(8)  # 32px
_BTN_PAD_X = _S(4)  # 16px horizontal button padding
_ROW_H = _S(9)  # 36px  standard interactive row / button height


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
        self.coordinator = coordinator  # Optional: only for fallback when no controller
        self.on_delete_complete = on_delete_complete
        self._review_controller = review_controller
        self._store = store
        self._on_new_scan = on_new_scan or (lambda: None)
        self._on_view_history = on_view_history or (lambda: None)
        self.vm = ReviewVM()
        self._current_result: Optional[ScanResult] = None
        self._thumbnail_refs: list = []
        # Track which state-filter chip is active so we can style it
        self._active_chip_key: str = "all"
        self._ui_mode: str = "simple"
        self._nav_top = 0
        self._nav_slot_group_ids: list[str] = []
        self._nav_scroll_virtual: bool | None = None
        self._nav_wheel_bound = False
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
        # Increased vertical padding: top _GAP_LG, bottom _GAP_MD.
        # Title + subtitle stacked with _GAP_XS between them.
        # State hint sits below with _GAP_SM separation.
        hdr = ttk.Frame(self, padding=(_PAD_PAGE, _GAP_LG, _PAD_PAGE, _GAP_MD))
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.columnconfigure(1, weight=1)

        # Title block (col 0–1)
        title_block = ttk.Frame(hdr)
        title_block.grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(
            title_block,
            text=f"{IC.REVIEW}  Decision Studio",
            font=font_tuple("page_title"),
        ).pack(side="top", anchor="w")
        ttk.Label(
            title_block,
            text="Groups · Workspace · Decision & Safety",
            style="Muted.TLabel",
            font=font_tuple("page_subtitle"),
        ).pack(side="top", anchor="w", pady=(_GAP_XS, 0))

        self._state_hint = tk.StringVar(value="No review data yet. Run a scan, then return here to make decisions.")
        ttk.Label(
            hdr,
            textvariable=self._state_hint,
            style="Muted.TLabel",
            font=font_tuple("caption"),
        ).grid(row=1, column=0, sticky="w", pady=(_GAP_SM, 0))

        # View-mode segmented control (right side, vertically centred in header)
        # Rendered as a framed group of radiobuttons with consistent width.
        self._mode_var = tk.StringVar(value="table")
        mode_frame = ttk.Frame(hdr, style="Card.TFrame", padding=(_GAP_XS, _GAP_XS, _GAP_XS, _GAP_XS))
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

        # ── Provenance ribbon ─────────────────────────────────────────
        # Added top gap to lift it off the header.
        self._prov = ProvenanceRibbon(self)
        self._prov.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=_PAD_PAGE,
            pady=(_GAP_XS, _GAP_MD),
        )

        # ── 3-pane body ───────────────────────────────────────────────
        body = ttk.Frame(self)
        body.grid(row=2, column=0, sticky="nsew", padx=_PAD_PAGE, pady=(0, _PAD_PAGE))
        body.rowconfigure(0, weight=1)
        # 25% / 50% / 25% column split (mins fit MIN_WIDTH 540 + 56px nav + page padding)
        body.columnconfigure(0, weight=1, minsize=110)
        body.columnconfigure(1, weight=2, minsize=220)
        body.columnconfigure(2, weight=1, minsize=110)

        # Left: Group Navigator
        left = SectionCard(body, title=f"{IC.GROUPS}  Group Navigator")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, _GAP_MD))
        self._build_group_navigator(left.body)

        # Center: Workspace (Gallery / Table / Compare)
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

        # ── Zero-state panel ──────────────────────────────────────────
        # Centred card with generous padding and a prominent icon line.
        self._zero_panel = ttk.Frame(
            self,
            style="Panel.TFrame",
            padding=(_PAD_PAGE, _GAP_LG, _PAD_PAGE, _GAP_LG),
        )
        self._zero_panel.grid(row=3, column=0, sticky="ew", padx=_PAD_PAGE, pady=(0, _PAD_PAGE))
        self._zero_panel.columnconfigure(0, weight=1)

        # Icon line
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

        # CTA buttons grouped tightly
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

        # Keyboard shortcuts (bindings stored for on_show / on_hide)
        self._bind_key_next = lambda e: self._on_key_next_group()
        self._bind_key_prev = lambda e: self._on_key_prev_group()
        self._bind_mode_gallery = lambda e: self._set_mode_shortcut("gallery")
        self._bind_mode_table = lambda e: self._set_mode_shortcut("table")
        self._bind_mode_compare = lambda e: self._set_mode_shortcut("compare")
        self._bind_quick_look = lambda e: self._quick_look()
        self._bind_execute = lambda e: self._on_execute_intent()
        self._bind_set_keep = lambda e: self._set_keep_selected()
        self._bind_clear_keep = lambda e: self._on_clear_keep()
        self._bind_preview = lambda e: self._on_preview_intent()
        self._bind_undo_hint = lambda e: self._on_undo_hint()
        self._bind_apply_smart = lambda e: self._on_apply_smart_rule_intent()
        self._bind_compare_prev = lambda e: self._run_if_compare_allowed(self._workspace.compare_prev)
        self._bind_compare_next = lambda e: self._run_if_compare_allowed(self._workspace.compare_next)
        self._bind_quick_compare = lambda e: self._run_if_compare_allowed(
            self._workspace.open_quick_compare_overlay
        )

    # ----------------------------------------------------------------
    # Sub-builders
    # ----------------------------------------------------------------
    def _build_group_navigator(self, body: ttk.Frame):
        body.columnconfigure(0, weight=1)
        body.rowconfigure(4, weight=1)

        # Search bar — full width, padded bottom
        self._filter_bar = FilterBar(
            body,
            on_search=self._on_search,
            filters=[],
            style="Panel.TFrame",
        )
        self._filter_bar.grid(row=0, column=0, sticky="ew", pady=(0, _GAP_SM))

        # ── State-filter chips ────────────────────────────────────────
        # Each chip gets equal width; active chip uses "Accent.TButton".
        # Hover feedback is handled by the theme's active/hover states.
        chips = ttk.Frame(body, style="Panel.TFrame")
        chips.grid(row=1, column=0, sticky="ew", pady=(0, _GAP_MD))
        self._chip_vars: dict[str, tk.StringVar] = {}
        self._chip_buttons: dict[str, ttk.Button] = {}
        chip_specs = [
            ("unresolved", "Unresolved"),
            ("ready", "Ready"),
            ("warning", "Warning"),
            ("skipped", "Skipped"),
            ("all", "All"),
        ]
        for i, (state_key, label) in enumerate(chip_specs):
            chips.columnconfigure(i, weight=1)
            var = tk.StringVar(value=label)
            # Active chip starts on "all"
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
            self._chip_vars[state_key] = var
            self._chip_buttons[state_key] = btn

        # ── Sort row ──────────────────────────────────────────────────
        # Label and combobox on the same row with _GAP_SM gap.
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

        # ── Count label ───────────────────────────────────────────────
        # Sits directly above the table with minimal gap.
        self._group_count_var = tk.StringVar(value="0 groups")
        ttk.Label(
            body,
            textvariable=self._group_count_var,
            style="Panel.Muted.TLabel",
            font=font_tuple("caption"),
        ).grid(row=3, column=0, sticky="w", pady=(0, _GAP_XS))

        # ── Group table ───────────────────────────────────────────────
        # Row height set via `height` (number of visible rows).
        self._group_table = DataTable(
            body,
            columns=[
                ("idx", "#", 32, "center"),
                ("state", "State", 120, "w"),
                ("files", "Files", 40, "center"),
                ("size", "Size", 70, "e"),
                ("conf", "Conf", 40, "center"),
            ],
            height=8,
            sortable=False,
            on_select=self._dispatch_group_select,
        )
        self._group_table.grid(row=4, column=0, sticky="nsew")
        body.rowconfigure(4, weight=1)
        self._group_table.bind_height_to_parent(
            body,
            min_lines=5,
            max_lines=22,
            reserve_px=200,
            after_change=self._refresh_group_list,
        )

    def _build_workspace(self, body: ttk.Frame):
        body.columnconfigure(0, weight=1)
        body.rowconfigure(1, weight=1)

        # ── Summary band ──────────────────────────────────────────────
        # Increased padding for breathing room.
        # Two logical columns: left (group id + reason) | right (keep + reclaim + rule).
        band = ttk.Frame(
            body,
            style="Panel.TFrame",
            padding=(_GAP_MD, _GAP_SM, _GAP_MD, _GAP_SM),
        )
        band.grid(row=0, column=0, sticky="ew", pady=(0, _GAP_MD))
        band.columnconfigure(0, weight=1)
        band.columnconfigure(1, weight=0)  # right info block: natural width

        self._group_summary_var = tk.StringVar(value="No group selected")
        self._group_reason_var = tk.StringVar(value="Reason: —")
        self._group_keep_var = tk.StringVar(value="Keep: not selected")
        self._group_reclaim_var = tk.StringVar(value="Reclaimable: —")
        self._group_rule_var = tk.StringVar(value="Rule: off")

        # Left column
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

        # Right column — three stacked metadata pills
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

        self._workspace = ReviewWorkspaceStack(
            body,
            on_keep=self._on_set_keep,
            on_clear_keep=self._on_clear_keep,
        )
        self._workspace.grid(row=1, column=0, sticky="nsew")

    def _build_smart_rules_rail(self, body: ttk.Frame):
        """Construct the Smart Rules section of the Right Rail (Blueprint 5.2)."""
        body.columnconfigure(0, weight=1)

        # ── Rule selector ─────────────────────────────────────────────
        # Label above combo (not inline) for cleaner alignment.
        ttk.Label(
            body,
            text="Auto-Select Rule",
            style="Panel.Muted.TLabel",
            font=font_tuple("data_label"),
        ).grid(row=0, column=0, sticky="w", pady=(0, _GAP_XS))

        self._smart_rule_var = tk.StringVar(value="newest")
        self._smart_rule_combo = ttk.Combobox(
            body,
            textvariable=self._smart_rule_var,
            state="readonly",
            values=["newest", "oldest", "largest", "smallest", "first"],
        )
        self._smart_rule_combo.grid(row=1, column=0, sticky="ew", pady=(0, _GAP_MD))

        # ── Action buttons ────────────────────────────────────────────
        # Both full-width, stacked vertically — more readable than side-by-side
        # on a narrow rail.
        ttk.Button(
            body,
            text="Apply to Group",
            style="Accent.TButton",
            command=self._on_apply_smart_rule_intent,
        ).grid(row=2, column=0, sticky="ew", pady=(0, _GAP_XS))

        ttk.Button(
            body,
            text="Clear All",
            style="Ghost.TButton",
            command=self._on_clear_smart_rule_intent,
        ).grid(row=3, column=0, sticky="ew")

        # ── Active rule status ────────────────────────────────────────
        # Extra top gap separates status from actions.
        self._active_rule_var = tk.StringVar(value="Smart Rule: off")
        ttk.Label(
            body,
            textvariable=self._active_rule_var,
            style="Panel.Accent.TLabel",
            font=font_tuple("caption"),
        ).grid(row=4, column=0, sticky="w", pady=(_GAP_MD, 0))

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
                    keep_selections={},
                    selected_group_id=self.vm.selected_group_id,
                )
            )
        self._prov.update(
            session_id=getattr(self.vm.session, "session_id", result.scan_id if result else ""),
            verification=getattr(self.vm.current_group, "verification_level", "full") if self.vm.groups else "full",
            groups=self.vm.total_groups,
            reclaimable_bytes=self.vm.reclaimable_bytes,
        )
        self._refresh_group_list()
        self._update_filter_chip_labels()
        self._safety_panel.update_plan(
            del_count=self.vm.delete_count,
            keep_count=self.vm.keep_count,
            reclaim_bytes=self.vm.reclaimable_bytes,
            risk_flags=self.vm.risk_flags,
        )

    def on_show(self):
        self.bind_all("<Control-Right>", self._bind_key_next, add="+")
        self.bind_all("<Control-Left>", self._bind_key_prev, add="+")
        self.bind_all("<Key-g>", self._bind_mode_gallery, add="+")
        self.bind_all("<Key-t>", self._bind_mode_table, add="+")
        self.bind_all("<Key-c>", self._bind_mode_compare, add="+")
        self.bind_all("<space>", self._bind_quick_look, add="+")
        self.bind_all("<Control-Return>", self._bind_execute, add="+")
        self.bind_all("<Key-k>", self._bind_set_keep, add="+")
        self.bind_all("<Key-K>", self._bind_clear_keep, add="+")
        self.bind_all("<Key-p>", self._bind_preview, add="+")
        self.bind_all("<Key-u>", self._bind_undo_hint, add="+")
        self.bind_all("<Key-a>", self._bind_apply_smart, add="+")
        self.bind_all("<Key-bracketleft>", self._bind_compare_prev, add="+")
        self.bind_all("<Key-bracketright>", self._bind_compare_next, add="+")
        self.bind_all("<Key-x>", self._bind_quick_compare, add="+")

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

    # ----------------------------------------------------------------
    # Group list
    # ----------------------------------------------------------------
    def _refresh_group_list(self):
        from ..components.decision_state import get_group_decision_state
        from ..components.virtual_navigator import (
            clamp_top,
            scrollbar_fracs,
            virtual_navigator_enabled,
        )

        groups = self.vm.filtered_groups
        total = len(groups)
        tree = self._group_table.tree
        vis = max(1, int(tree.cget("height")))
        use_virtual = virtual_navigator_enabled() and total > vis

        self._bind_group_nav_scroll(use_virtual)

        if use_virtual:
            self._nav_top = clamp_top(self._nav_top, total, vis)
            self._fill_virtual_group_rows(groups, total, vis, get_group_decision_state)
            lo, hi = scrollbar_fracs(self._nav_top, total, vis)
            self._group_table.vsb.set(lo, hi)
        else:
            self._refresh_group_list_legacy(get_group_decision_state)

        self._update_filter_chip_labels()

    def _refresh_group_list_legacy(self, get_group_decision_state):
        self._group_table.clear()
        self._nav_slot_group_ids = []
        groups = self.vm.filtered_groups
        total = len(groups)
        display = groups if total <= REVIEW_NAVIGATOR_MAX_ROWS else groups[:REVIEW_NAVIGATOR_MAX_ROWS]
        if total > REVIEW_NAVIGATOR_MAX_ROWS:
            self._group_count_var.set(f"Showing first {REVIEW_NAVIGATOR_MAX_ROWS} of {total} groups")
        else:
            self._group_count_var.set(f"{total} group{'s' if total != 1 else ''}")
        for i, ge in enumerate(display):
            state = get_group_decision_state(ge.group_id, self.vm.keep_selections, ge.has_risk)
            state_label = self._decision_badge_text(state)
            tag = "warn" if ge.has_risk else ("danger" if state == "unresolved" else "safe" if state == "ready" else "")
            self._group_table.insert_row(
                ge.group_id,
                (str(i + 1), state_label, str(ge.file_count), fmt_bytes(ge.reclaimable_bytes), ge.confidence_label),
                tags=(tag,) if tag else (),
            )

    def _bind_group_nav_scroll(self, virtual: bool) -> None:
        cur = getattr(self, "_nav_scroll_virtual", None)
        if cur is not None and cur == virtual:
            return
        self._nav_scroll_virtual = virtual
        tree = self._group_table.tree
        vsb = self._group_table.vsb
        if virtual:
            tree.configure(yscrollcommand=lambda *_a: None)
            vsb.configure(command=self._on_nav_virtual_scrollbar_cmd)
            if not self._nav_wheel_bound:
                self._nav_wheel_bound = True
                tree.bind("<MouseWheel>", self._on_nav_virtual_wheel, add="+")
                tree.bind("<Button-4>", self._on_nav_virtual_wheel, add="+")
                tree.bind("<Button-5>", self._on_nav_virtual_wheel, add="+")
        else:
            tree.configure(yscrollcommand=vsb.set)
            vsb.configure(command=tree.yview)

    def _fill_virtual_group_rows(self, groups, total, vis, get_group_decision_state) -> None:
        from ..components.virtual_navigator import slot_iid

        self._group_table.clear()
        self._nav_slot_group_ids = []
        end = min(total, self._nav_top + vis)
        for slot, idx in enumerate(range(self._nav_top, end)):
            ge = groups[idx]
            state = get_group_decision_state(ge.group_id, self.vm.keep_selections, ge.has_risk)
            state_label = self._decision_badge_text(state)
            tag = "warn" if ge.has_risk else ("danger" if state == "unresolved" else "safe" if state == "ready" else "")
            self._nav_slot_group_ids.append(ge.group_id)
            self._group_table.insert_row(
                slot_iid(slot),
                (str(idx + 1), state_label, str(ge.file_count), fmt_bytes(ge.reclaimable_bytes), ge.confidence_label),
                tags=(tag,) if tag else (),
            )
        if total > vis:
            self._group_count_var.set(
                f"Rows {self._nav_top + 1}–{end} of {total} (virtual scroll — CEREBRO_VIRTUAL_NAV=1)"
            )
        else:
            self._group_count_var.set(f"{total} group{'s' if total != 1 else ''}")

    def _on_nav_virtual_scrollbar_cmd(self, *args) -> None:
        from ..components.decision_state import get_group_decision_state
        from ..components.virtual_navigator import clamp_top, scrollbar_fracs, slot_iid, virtual_navigator_enabled

        if not virtual_navigator_enabled():
            return
        groups = self.vm.filtered_groups
        total = len(groups)
        vis = max(1, int(self._group_table.tree.cget("height")))
        if total <= vis:
            return
        opcode = args[0]
        max_top = max(0, total - vis)
        if opcode == "moveto":
            pos = float(args[1])
            self._nav_top = int(round(pos * max_top)) if max_top else 0
        elif opcode == "scroll":
            n = int(float(args[1]))
            if args[2] == "units":
                self._nav_top = clamp_top(self._nav_top + n, total, vis)
            else:
                self._nav_top = clamp_top(self._nav_top + n * vis, total, vis)
        else:
            return
        self._fill_virtual_group_rows(groups, total, vis, get_group_decision_state)
        lo, hi = scrollbar_fracs(self._nav_top, total, vis)
        self._group_table.vsb.set(lo, hi)
        gid = self.vm.selected_group_id
        if gid and gid in self._nav_slot_group_ids:
            self._group_table.select(slot_iid(self._nav_slot_group_ids.index(gid)))

    def _on_nav_virtual_wheel(self, event) -> None:
        from ..components.decision_state import get_group_decision_state
        from ..components.virtual_navigator import clamp_top, scrollbar_fracs, slot_iid, virtual_navigator_enabled

        if not virtual_navigator_enabled() or not self._use_virtual_nav_for_current():
            return
        groups = self.vm.filtered_groups
        total = len(groups)
        vis = max(1, int(self._group_table.tree.cget("height")))
        if total <= vis:
            return
        if getattr(event, "delta", 0):
            n = -1 if event.delta > 0 else 1
        elif getattr(event, "num", 0) == 4:
            n = -1
        elif getattr(event, "num", 0) == 5:
            n = 1
        else:
            return
        self._nav_top = clamp_top(self._nav_top + n * 3, total, vis)
        self._fill_virtual_group_rows(groups, total, vis, get_group_decision_state)
        lo, hi = scrollbar_fracs(self._nav_top, total, vis)
        self._group_table.vsb.set(lo, hi)
        gid = self.vm.selected_group_id
        if gid and gid in self._nav_slot_group_ids:
            self._group_table.select(slot_iid(self._nav_slot_group_ids.index(gid)))

    def _use_virtual_nav_for_current(self) -> bool:
        from ..components.virtual_navigator import virtual_navigator_enabled

        if not virtual_navigator_enabled():
            return False
        tree = self._group_table.tree
        vis = max(1, int(tree.cget("height")))
        return len(self.vm.filtered_groups) > vis

    def _dispatch_group_select(self, iid: str) -> None:
        from ..components.virtual_navigator import NAV_SLOT_PREFIX, virtual_navigator_enabled

        if virtual_navigator_enabled() and self._use_virtual_nav_for_current() and iid.startswith(NAV_SLOT_PREFIX):
            rest = iid[len(NAV_SLOT_PREFIX) :]
            try:
                slot = int(rest)
            except ValueError:
                return
            if 0 <= slot < len(self._nav_slot_group_ids):
                self._on_group_select(self._nav_slot_group_ids[slot])
            return
        self._on_group_select(iid)

    def _select_group_in_table(self, group_id: str) -> None:
        from ..components.decision_state import get_group_decision_state
        from ..components.virtual_navigator import (
            clamp_top,
            scrollbar_fracs,
            slot_iid,
            virtual_navigator_enabled,
        )

        groups = self.vm.filtered_groups
        tree = self._group_table.tree
        vis = max(1, int(tree.cget("height")))
        total = len(groups)
        idx = next((i for i, g in enumerate(groups) if g.group_id == group_id), None)
        if idx is None:
            return
        if virtual_navigator_enabled() and total > vis:
            max_top = max(0, total - vis)
            if idx < self._nav_top:
                self._nav_top = idx
            elif idx >= self._nav_top + vis:
                self._nav_top = min(max_top, idx - vis + 1)
            self._nav_top = clamp_top(self._nav_top, total, vis)
            self._fill_virtual_group_rows(groups, total, vis, get_group_decision_state)
            lo, hi = scrollbar_fracs(self._nav_top, total, vis)
            self._group_table.vsb.set(lo, hi)
            self._group_table.select(slot_iid(idx - self._nav_top))
        else:
            self._group_table.select(group_id)

    def _on_search(self, text: str):
        self.vm.filter_text = text
        self._refresh_group_list()

    def _on_state_filter_change(self, *_):
        # No longer needed (chips replaced dropdown) — kept for compatibility.
        pass

    def _set_state_filter(self, state_key: str) -> None:
        # Update visual active state on chips
        self._active_chip_key = state_key
        for key, btn in self._chip_buttons.items():
            btn.configure(style="Accent.TButton" if key == state_key else "Ghost.TButton")
        self.vm.filter_state = state_key
        self._refresh_group_list()

    def _on_sort_change(self, *_):
        label = (self._sort_var.get() or "priority").strip().lower()
        mapping = {
            "priority": "priority",
            "reclaimable size": "reclaimable",
            "file count": "files",
            "confidence": "confidence",
        }
        self.vm.sort_by = mapping.get(label, "priority")
        self._refresh_group_list()

    def _decision_badge_text(self, state: str) -> str:
        icons = {
            "unresolved": "●",
            "ready": "✓",
            "warning": "⚠",
            "skipped": "—",
            "keep_selected": "◉",
        }
        from ..components.decision_state import get_decision_label

        return f"{icons.get(state, '•')} {get_decision_label(state)}"

    def _update_filter_chip_labels(self) -> None:
        from ..components.decision_state import get_group_decision_state

        counts = {"all": len(self.vm.groups), "unresolved": 0, "ready": 0, "warning": 0, "skipped": 0}
        for g in self.vm.groups:
            state = get_group_decision_state(g.group_id, self.vm.keep_selections, g.has_risk)
            counts[state] = counts.get(state, 0) + 1
        labels = {
            "unresolved": "Unresolved",
            "ready": "Ready",
            "warning": "Warning",
            "skipped": "Skipped",
            "all": "All",
        }
        for key, var in getattr(self, "_chip_vars", {}).items():
            var.set(f"{labels[key]} ({counts.get(key, 0)})")

    def _on_key_next_group(self):
        groups = self.vm.filtered_groups
        if not groups or not self.winfo_viewable():
            return
        idx = next((i for i, g in enumerate(groups) if g.group_id == self.vm.selected_group_id), 0)
        if idx + 1 < len(groups):
            gid = groups[idx + 1].group_id
            self._on_group_select(gid)
            self._select_group_in_table(gid)

    def _on_key_prev_group(self):
        groups = self.vm.filtered_groups
        if not groups or not self.winfo_viewable():
            return
        idx = next((i for i, g in enumerate(groups) if g.group_id == self.vm.selected_group_id), 0)
        if idx > 0:
            gid = groups[idx - 1].group_id
            self._on_group_select(gid)
            self._select_group_in_table(gid)

    def _on_group_select(self, group_id: str):
        self.vm.selected_group_id = group_id
        if self._store:
            from ..state.store import ReviewSelectionState

            self._store.set_review_selection(
                ReviewSelectionState(
                    keep_selections=dict(self.vm.keep_selections),
                    selected_group_id=group_id,
                )
            )
        self._load_workspace(group_id)

    def _load_workspace(self, group_id: str):
        if not self._current_result:
            return
        group = next((g for g in self._current_result.duplicate_groups if g.group_id == group_id), None)
        keep_path = self.vm.keep_selections.get(group_id, "")
        mode = self.vm.view_mode
        self._workspace.load_group(group, keep_path=keep_path, mode=mode)
        if group:
            file_count = len(getattr(group, "files", []) or [])
            self._group_summary_var.set(f"Group {group.group_id} · {file_count} files")
            self._group_reason_var.set("Reason: hash-based duplicate group")
            self._group_keep_var.set(f"Keep: {Path(keep_path).name if keep_path else 'not selected'}")
            reclaim = sum(getattr(f, "size", 0) for f in group.files) - (
                next((f.size for f in group.files if f.path == keep_path), 0) if keep_path else 0
            )
            self._group_reclaim_var.set(f"Reclaimable: {fmt_bytes(max(0, reclaim))}")
            self._group_rule_var.set(f"Rule: {self._smart_rule_var.get() if keep_path else 'off'}")

    # ----------------------------------------------------------------
    # Intent forwarding
    # ----------------------------------------------------------------
    def _on_preview_intent(self) -> None:
        if self._review_controller:
            self._review_controller.handle_preview_deletion()
        else:
            self._on_dry_run()

    def _on_execute_intent(self) -> None:
        if self._review_controller:
            self._review_controller.handle_execute_deletion()
        else:
            self._on_execute()

    def _sync_review_from_store_and_refresh(self) -> None:
        if not self._store:
            return
        from ..state.selectors import review_selection

        state = self._store.state
        sel = review_selection(state)
        if sel is None:
            return
        keep = getattr(sel, "keep_selections", None) or {}
        self.vm.keep_selections = dict(keep)
        sid = getattr(sel, "selected_group_id", None)
        if sid is not None:
            self.vm.selected_group_id = sid
        gid = self.vm.selected_group_id
        if gid:
            self._load_workspace(gid)
        self._safety_panel.update_plan(
            del_count=self.vm.delete_count,
            keep_count=self.vm.keep_count,
            reclaim_bytes=self.vm.reclaimable_bytes,
            risk_flags=self.vm.risk_flags,
        )
        if self.vm.keep_count > 0:
            self._active_rule_var.set(f"Smart Rule: {self._smart_rule_var.get()} (active)")
        else:
            self._active_rule_var.set("Smart Rule: off")

    def _on_execute_done(self, result: DeletionResult) -> None:
        self.on_delete_complete(result)
        self._record_action_history(result)
        if result.deleted_files and self._current_result:
            from ...engine.models import DuplicateGroup

            deleted_set = set(result.deleted_files)
            new_groups = []
            for g in self._current_result.duplicate_groups:
                remaining = [f for f in g.files if f.path not in deleted_set]
                if len(remaining) >= 2:
                    new_groups.append(DuplicateGroup(group_id=g.group_id, group_hash=g.group_hash, files=remaining))
            self._current_result.duplicate_groups = new_groups
            self.load_result(self._current_result)
        else:
            self._safety_panel.update_plan(
                del_count=self.vm.delete_count,
                keep_count=self.vm.keep_count,
                reclaim_bytes=self.vm.reclaimable_bytes,
                risk_flags=self.vm.risk_flags,
            )
        if self.vm.keep_count == 0:
            self._active_rule_var.set("Smart Rule: off")
        if self._store:
            from ..state.store import ReviewSelectionState

            self._store.set_review_selection(
                ReviewSelectionState(
                    keep_selections=dict(self.vm.keep_selections),
                    selected_group_id=self.vm.selected_group_id,
                )
            )

    def _record_action_history(self, result: DeletionResult) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        deleted = len(result.deleted_files)
        failed = len(result.failed_files)
        bytes_txt = fmt_bytes(getattr(result, "bytes_reclaimed", 0) or 0)
        entry = f"[{stamp}] execute -> deleted={deleted}, failed={failed}, reclaim={bytes_txt}"
        self._safety_panel.add_action_entry(entry)
        if deleted > 0:
            self._safety_panel.set_undo_message(
                "Undo available via your system Trash/Recycle Bin. Press U for guidance."
            )
        else:
            self._safety_panel.set_undo_message("")

    def _on_set_keep(self, path: str) -> None:
        gid = self.vm.selected_group_id
        if not gid or not path:
            return
        if self._review_controller:
            self._review_controller.handle_set_keep(gid, path)
        else:
            self.vm.set_keep(gid, path)
            self._load_workspace(gid)
            self._safety_panel.update_plan(
                del_count=self.vm.delete_count,
                keep_count=self.vm.keep_count,
                reclaim_bytes=self.vm.reclaimable_bytes,
                risk_flags=self.vm.risk_flags,
            )

    def _on_clear_keep(self) -> None:
        gid = self.vm.selected_group_id
        if not gid or gid not in self.vm.keep_selections:
            return
        if self._review_controller:
            self._review_controller.handle_clear_keep(gid)
        else:
            self.vm.clear_keep(gid)
            self._load_workspace(gid)
            self._safety_panel.update_plan(
                del_count=self.vm.delete_count,
                keep_count=self.vm.keep_count,
                reclaim_bytes=self.vm.reclaimable_bytes,
                risk_flags=self.vm.risk_flags,
            )

    def _on_mode_change(self) -> None:
        mode = self._mode_var.get()
        self.vm.view_mode = mode
        self._workspace.set_mode(mode)
        gid = self.vm.selected_group_id
        if gid:
            self._load_workspace(gid)

    def _set_mode_shortcut(self, mode: str) -> None:
        if not self.winfo_viewable():
            return
        if mode == "compare" and self._ui_mode != "advanced":
            return
        self._mode_var.set(mode)
        self._on_mode_change()

    # ----------------------------------------------------------------
    # Quick Look dialog
    # ----------------------------------------------------------------
    def _quick_look(self) -> None:
        if not self.winfo_viewable() or not self._current_result:
            return
        gid = self.vm.selected_group_id
        if not gid:
            return
        group = next((g for g in self._current_result.duplicate_groups if g.group_id == gid), None)
        if not group:
            return
        sel = self._workspace.table_view.selection()
        target = next((f for f in group.files if f.path == sel), None) if sel else None
        if target is None and group.files:
            target = group.files[0]
        if target is None:
            return

        dlg = tk.Toplevel(self)
        dlg.title("Quick Look")
        dlg.transient(self.winfo_toplevel())
        dlg.geometry("800x420")
        dlg.grab_set()

        # ── Outer wrapper ─────────────────────────────────────────────
        wrap = ttk.Frame(dlg, padding=(_GAP_LG, _GAP_LG, _GAP_LG, 0))
        wrap.pack(fill="both", expand=True)
        wrap.columnconfigure(0, weight=1)
        wrap.rowconfigure(1, weight=1)

        # Filename as section title
        ttk.Label(
            wrap,
            text=target.filename,
            style="Panel.Secondary.TLabel",
            font=font_tuple("section_title"),
        ).grid(row=0, column=0, sticky="w", pady=(0, _GAP_MD))

        # ── Metadata grid ─────────────────────────────────────────────
        # Label / value pairs laid out in a two-column grid.
        # Each key label is right-aligned; value is left-aligned in col 1.
        meta_frame = ttk.Frame(wrap)
        meta_frame.grid(row=1, column=0, sticky="nsew", pady=(0, _GAP_MD))
        meta_frame.columnconfigure(1, weight=1)

        def _meta_row(r: int, key: str, val: str) -> None:
            ttk.Label(
                meta_frame,
                text=key,
                style="Panel.Muted.TLabel",
                font=font_tuple("caption"),
                anchor="e",
                width=12,
            ).grid(row=r, column=0, sticky="e", padx=(0, _GAP_MD), pady=(_GAP_XS, 0))
            ttk.Label(
                meta_frame,
                text=val,
                font=font_tuple("body"),
                anchor="w",
            ).grid(row=r, column=1, sticky="w", pady=(_GAP_XS, 0))

        _meta_row(0, "Path", target.path)
        _meta_row(1, "Size", fmt_bytes(target.size))
        _meta_row(2, "Modified", str(getattr(target, "mtime_ns", 0)))
        _meta_row(3, "Hash", (target.file_hash or "—")[:32])

        # ── Divider ───────────────────────────────────────────────────
        ttk.Separator(dlg, orient="horizontal").pack(fill="x", padx=_GAP_LG, pady=(_GAP_MD, 0))

        # ── Footer action bar ─────────────────────────────────────────
        # Danger action (Mark Keep) on the right; neutral actions on left.
        footer = ttk.Frame(dlg, padding=(_GAP_LG, _GAP_SM, _GAP_LG, _GAP_MD))
        footer.pack(fill="x")
        ttk.Button(
            footer,
            text="Close",
            style="Ghost.TButton",
            command=dlg.destroy,
        ).pack(side="left")
        ttk.Button(
            footer,
            text="Mark Delete",
            style="Ghost.TButton",
            command=dlg.destroy,
        ).pack(side="left", padx=(_GAP_SM, 0))
        ttk.Button(
            footer,
            text="Mark Keep ✓",
            style="Accent.TButton",
            command=lambda p=target.path: [self._on_set_keep(p), dlg.destroy()],
        ).pack(side="right")

        dlg.wait_window(dlg)

    def _set_keep_selected(self) -> None:
        if not self.winfo_viewable():
            return
        sel = self._workspace.table_view.selection()
        if sel:
            self._on_set_keep(sel)

    def _on_undo_hint(self) -> None:
        if not self.winfo_viewable():
            return
        messagebox.showinfo(
            "Undo Guidance",
            "Deleted files are moved to Trash/Recycle Bin in safe mode.\n\n"
            "To restore:\n"
            "1) Open your system Trash/Recycle Bin\n"
            "2) Sort by most recent\n"
            "3) Restore the files from the last execute action\n\n"
            "Action history in the Safety Rail helps identify the latest batch.",
        )

    def _on_apply_smart_rule_intent(self) -> None:
        rule = self._smart_rule_var.get().strip().lower() or "newest"
        if self._review_controller:
            self._review_controller.handle_apply_smart_rule(rule)
        else:
            if not self._current_result:
                return
            keep_map: dict[str, str] = {}
            for g in self._current_result.duplicate_groups:
                files = list(g.files or [])
                if len(files) < 2:
                    continue
                if rule == "newest":
                    k = max(files, key=lambda f: getattr(f, "mtime_ns", 0))
                elif rule == "oldest":
                    k = min(files, key=lambda f: getattr(f, "mtime_ns", 0))
                elif rule == "largest":
                    k = max(files, key=lambda f: getattr(f, "size", 0))
                elif rule == "smallest":
                    k = min(files, key=lambda f: getattr(f, "size", 0))
                else:
                    k = files[0]
                keep_map[g.group_id] = k.path
            self.vm.keep_selections = keep_map
            self._refresh_group_list()
            gid = self.vm.selected_group_id
            if gid:
                self._load_workspace(gid)
            self._safety_panel.update_plan(
                del_count=self.vm.delete_count,
                keep_count=self.vm.keep_count,
                reclaim_bytes=self.vm.reclaimable_bytes,
                risk_flags=self.vm.risk_flags,
            )
        self._active_rule_var.set(f"Smart Rule: {rule} (active)")

    def _on_clear_smart_rule_intent(self) -> None:
        if self._review_controller:
            self._review_controller.handle_clear_all_keeps()
        else:
            self.vm.keep_selections = {}
            self._refresh_group_list()
            gid = self.vm.selected_group_id
            if gid:
                self._load_workspace(gid)
            self._safety_panel.update_plan(
                del_count=self.vm.delete_count,
                keep_count=self.vm.keep_count,
                reclaim_bytes=self.vm.reclaimable_bytes,
                risk_flags=self.vm.risk_flags,
            )
        self._active_rule_var.set("Smart Rule: off")

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
        Refactored confirmation dialog.
        Structure:
          - Spacious header (title + sub-line)
          - Two-column summary table (key / value)
          - Horizontal divider
          - Footer bar: Cancel | Preview Effects  →  DELETE
        """
        result = {"choice": "cancel"}
        root = self.winfo_toplevel()
        dlg = tk.Toplevel(root)
        dlg.title("Confirm Deletion")
        dlg.transient(root)
        dlg.grab_set()
        dlg.resizable(False, False)

        # Outer padding
        outer = ttk.Frame(dlg, padding=(_GAP_LG, _GAP_LG, _GAP_LG, 0))
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(1, weight=1)

        # ── Dialog title ──────────────────────────────────────────────
        ttk.Label(
            outer,
            text="⚠  Confirm Deletion",
            font=font_tuple("section_title"),
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, _GAP_XS))
        ttk.Label(
            outer,
            text="Review the summary below before proceeding. This action moves files to Trash.",
            style="Muted.TLabel",
            font=font_tuple("body"),
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, _GAP_LG))

        # ── Summary rows ──────────────────────────────────────────────
        total_files = prev.get("total_files", "?")
        human_size = prev.get("human_readable_size", "?")
        rows = [
            ("Files to delete", str(total_files)),
            ("Files kept", str(self.vm.keep_count)),
            ("Duplicate groups", str(len(plan.groups))),
            ("Reclaimable space", str(human_size)),
            ("Delete mode", "Trash"),
            ("Revalidation", "ON"),
            ("Audit logging", "ACTIVE"),
        ]
        for r_idx, (key, val) in enumerate(rows):
            base_row = r_idx + 2  # offset past title rows
            ttk.Label(
                outer,
                text=key,
                style="Muted.TLabel",
                font=font_tuple("body"),
                anchor="e",
                width=18,
            ).grid(row=base_row, column=0, sticky="e", padx=(0, _GAP_MD), pady=(_GAP_XS, 0))
            ttk.Label(
                outer,
                text=val,
                font=font_tuple("body_bold"),
                anchor="w",
            ).grid(row=base_row, column=1, sticky="w", pady=(_GAP_XS, 0))

        # ── Divider ───────────────────────────────────────────────────
        ttk.Separator(dlg, orient="horizontal").pack(fill="x", padx=_GAP_LG, pady=(_GAP_LG, 0))

        # ── Footer bar ────────────────────────────────────────────────
        # Cancel / Preview  ←→  DELETE
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
        self.update()
        result = self.coordinator.execute_deletion(plan)
        self._safety_panel._delete_btn.configure(state="normal", text="DELETE")
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
