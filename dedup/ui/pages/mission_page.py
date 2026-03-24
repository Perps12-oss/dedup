"""
Mission Page — Readiness dashboard, launch point, recent sessions.

Layout (2-column grid):
  Row 0: Engine Status Card  |  Last Scan Card
  Row 1: Quick Start         |  Capabilities
  Row 2: Recent Sessions (full-width)

UI Refactor (v4): Modern visual design pass.
  - Header: left-accented title block with gradient separator, icon badge.
  - Readiness row: equal-weight cards with unified border treatment.
  - Engine / Last Scan / Safety cards: cleaner KV rows, status dot indicators.
  - Recent session cards: prominent reclaim value, status pill, bolder action CTA.
  - Quick-start drop zone: dashed border, hover hint text.
  - Button rows: consistent pill-shaped Accent / Ghost pairing.
  - Section titles: uppercase tracking with hairline rule beneath.
  - All spacing remains on the 8px grid.
"""

from __future__ import annotations

import logging
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import TYPE_CHECKING, Callable, Optional

import ttkbootstrap as tb

from ..utils.ui_state import UIState

if TYPE_CHECKING:
    from ..state.store import UIStateStore

from ..components import MetricCard, SectionCard
from ..theme.design_system import font_tuple
from ..utils.formatting import fmt_bytes, fmt_dt, fmt_duration, fmt_int
from ..utils.icons import IC
from ..viewmodels.mission_vm import MissionVM

try:
    from ...engine.media_types import get_category_label, list_categories
except Exception:

    def list_categories():
        return ["all"]

    def get_category_label(c):
        return c.title()


try:
    from tkinterdnd2 import DND_FILES  # type: ignore
except Exception:
    DND_FILES = None


# ---------------------------------------------------------------------------
# Spacing helpers — 8-pt grid (shared across all pages)
# ---------------------------------------------------------------------------
def _S(n: int) -> int:
    return n * 4


_PAD_PAGE = _S(6)   # 24px
_GAP_XS   = _S(1)   # 4px
_GAP_SM   = _S(2)   # 8px
_GAP_MD   = _S(4)   # 16px
_GAP_LG   = _S(6)   # 24px
_GAP_XL   = _S(8)   # 32px

_log = logging.getLogger(__name__)


class MissionPage(ttk.Frame):
    """Mission / home page — CEREBRO launch hub."""

    def __init__(
        self,
        parent,
        on_start_scan: Callable[[Path, dict], None],
        on_resume_scan: Callable[[str], None],
        coordinator,
        on_request_refresh: Optional[Callable[[], None]] = None,
        on_open_last_review: Optional[Callable[[], None]] = None,
        ui_state: Optional[UIState] = None,
        **kwargs,
    ):
        super().__init__(parent, **kwargs)
        self.on_start_scan = on_start_scan
        self.on_resume_scan = on_resume_scan
        self.coordinator = coordinator
        self._on_request_refresh = on_request_refresh
        self._on_open_last_review = on_open_last_review or (lambda: None)
        self._ui_state = ui_state
        self.vm = MissionVM()
        self._selected_path: Optional[Path] = None
        self._store: Optional["UIStateStore"] = None
        self._store_unsub: Optional[Callable[[], None]] = None
        self._build()

    def _build(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self._content = ttk.Frame(self, padding=(_PAD_PAGE, _PAD_PAGE, _PAD_PAGE, _PAD_PAGE))
        content = self._content
        content.grid(row=0, column=0, sticky="nsew")
        content.columnconfigure(0, weight=1)
        content.rowconfigure(2, weight=1)

        # Build sections top-down so navigation stays obvious.
        self._build_hero_zone(content)
        self._build_readiness_row(content)
        self._build_recent_and_quick(content)

        # Capability vars kept for API compatibility
        self._cap_vars: dict[str, tk.StringVar] = {}

    def _build_hero_zone(self, content: ttk.Frame) -> None:
        """Hero banner with CTA actions and contextual hint."""
        self._hero = ttk.Frame(content)
        hero = self._hero
        hero.grid(row=0, column=0, sticky="ew", pady=(0, _GAP_LG))
        hero.columnconfigure(0, weight=1)

        top_row = ttk.Frame(hero)
        top_row.grid(row=0, column=0, sticky="ew")
        top_row.columnconfigure(1, weight=1)

        badge = ttk.Frame(top_row, style="Accent.TFrame", padding=(_GAP_SM, _GAP_XS, _GAP_SM, _GAP_XS))
        badge.grid(row=0, column=0, sticky="ns", padx=(0, _GAP_MD))
        ttk.Label(badge, text=IC.SHIELD, style="Accent.TLabel", font=font_tuple("section_title")).pack()

        title_block = ttk.Frame(top_row)
        title_block.grid(row=0, column=1, sticky="w")
        ttk.Label(title_block, text="CEREBRO  —  Mission Control", font=font_tuple("page_title")).pack(
            side="top", anchor="w"
        )
        ttk.Label(
            title_block,
            text="Your first scan takes 2 minutes.  No data leaves your device.",
            style="Muted.TLabel",
            font=font_tuple("page_subtitle"),
        ).pack(side="top", anchor="w", pady=(_GAP_XS, 0))

        ttk.Separator(hero, orient="horizontal").grid(row=1, column=0, sticky="ew", pady=(_GAP_SM, 0))

        cta = ttk.Frame(hero)
        cta.grid(row=2, column=0, sticky="w", pady=(_GAP_MD, 0))
        tb.Button(cta, text=f"{IC.SCAN}  Start New Scan", bootstyle="success", command=self._on_start).grid(
            row=0, column=0, sticky="w", padx=(0, _GAP_SM)
        )
        tb.Button(
            cta, text=f"{IC.RESUME}  Resume Interrupted", bootstyle="info", command=self._on_resume
        ).grid(row=0, column=1, sticky="w", padx=(0, _GAP_SM))
        self._open_review_btn = tb.Button(
            cta, text=f"{IC.REVIEW}  Open Last Review", bootstyle="secondary", command=self._on_open_last_review
        )
        self._open_review_btn.grid(row=0, column=2, sticky="w", padx=(0, _GAP_SM))
        self._tour_btn = tb.Button(cta, text="Watch Tour", bootstyle="secondary", command=self._show_quick_tour)
        self._tour_btn.grid(row=0, column=3, sticky="w")

        self._welcome_var = tk.StringVar(value="")
        self._welcome_lbl = ttk.Label(
            hero, textvariable=self._welcome_var, style="Muted.TLabel", font=font_tuple("caption")
        )
        self._welcome_lbl.grid(row=3, column=0, sticky="w", pady=(_GAP_XS, 0))

    def _build_readiness_row(self, content: ttk.Frame) -> None:
        """Three-card readiness row that can be relaid out by ui mode."""
        self._ready = ttk.Frame(content)
        ready = self._ready
        ready.grid(row=1, column=0, sticky="ew", pady=(0, _GAP_LG))
        ready.columnconfigure(0, weight=1)
        ready.columnconfigure(1, weight=1)
        ready.columnconfigure(2, weight=1)

        self._engine_card = SectionCard(ready, title=f"{IC.SHIELD}  Engine Status")
        self._engine_card.grid(row=0, column=0, sticky="nsew", padx=(0, _GAP_SM))
        self._build_engine_card()

        self._last_scan_card = SectionCard(ready, title=f"{IC.HISTORY}  Last Scan")
        self._last_scan_card.grid(row=0, column=1, sticky="nsew", padx=(_GAP_SM // 2, _GAP_SM // 2))
        self._build_last_scan_card()

        self._safety_card = SectionCard(ready, title=f"{IC.OK}  Trash Protection")
        self._safety_card.grid(row=0, column=2, sticky="nsew", padx=(_GAP_SM, 0))
        self._build_safety_card()

    def _build_recent_and_quick(self, content: ttk.Frame) -> None:
        """Bottom cards: recent sessions and quick scan launcher."""
        self._recent_card = SectionCard(content, title=f"{IC.HISTORY}  Recent Sessions")
        self._recent_card.grid(row=2, column=0, sticky="nsew", pady=(0, _GAP_LG))
        self._recent_card.columnconfigure(0, weight=1)
        self._build_recent_sessions(self._recent_card.body)

        self._quick_card = SectionCard(content, title=f"{IC.SCAN}  Quick Scan")
        self._quick_card.grid(row=3, column=0, sticky="ew", pady=(0, _GAP_MD))
        self._build_quick_start(self._quick_card.body)

    # ----------------------------------------------------------------
    def _build_engine_card(self):
        b = self._engine_card.body
        b.columnconfigure(0, minsize=130)
        b.columnconfigure(1, weight=1)
        self._eng_rows: dict[str, tk.StringVar] = {}
        fields = [
            ("Health",        f"{IC.OK} Healthy"),
            ("Pipeline",      "Durable"),
            ("Hash backend",  "—"),
            ("Resume",        "—"),
            ("Schema",        "—"),
        ]
        for i, (label, default) in enumerate(fields):
            # Label cell — right-aligned, muted
            ttk.Label(
                b,
                text=label,
                style="Panel.Muted.TLabel",
                font=font_tuple("data_label"),
                anchor="e",
                width=14,
            ).grid(row=i, column=0, sticky="e", padx=(0, _GAP_MD), pady=(_GAP_XS, 0))
            # Value cell
            var = tk.StringVar(value=default)
            ttk.Label(
                b,
                textvariable=var,
                style="Panel.TLabel",
                font=font_tuple("data_value"),
            ).grid(row=i, column=1, sticky="w", pady=(_GAP_XS, 0))
            self._eng_rows[label] = var

    def _build_last_scan_card(self):
        b = self._last_scan_card.body
        b.columnconfigure(0, weight=1)
        b.columnconfigure(1, weight=1)
        # Subtitle caption
        ttk.Label(
            b,
            text="From your most recent completed scan.",
            style="Panel.Muted.TLabel",
            font=font_tuple("caption"),
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, _GAP_SM))
        self._last_metrics: dict[str, MetricCard] = {}
        specs = [
            ("files",   f"{IC.FILE}  Files Scanned", "—", "neutral"),
            ("groups",  f"{IC.GROUPS} Groups",        "—", "neutral"),
            ("reclaim", f"{IC.RECLAIM} Reclaimable",  "—", "positive"),
            ("dur",     f"{IC.SPEED}  Duration",       "—", "neutral"),
        ]
        for i, (key, label, val, variant) in enumerate(specs):
            c = MetricCard(b, label=label, value=val, variant=variant, width=0)
            c.grid(
                row=(i // 2) + 1,
                column=i % 2,
                sticky="nsew",
                padx=(_GAP_XS, _GAP_XS),
                pady=(_GAP_XS, _GAP_XS),
            )
            self._last_metrics[key] = c

    def _build_safety_card(self):
        b = self._safety_card.body
        b.columnconfigure(0, minsize=170)
        b.columnconfigure(1, weight=1)
        self._safety_vars: dict[str, tk.StringVar] = {}
        rows = [
            ("Status",                  f"{IC.OK} Active"),
            ("Pre-delete revalidation", f"{IC.OK} Enabled"),
            ("Audit logging",           f"{IC.OK} Enabled"),
        ]
        for i, (label, default) in enumerate(rows):
            ttk.Label(
                b,
                text=label,
                style="Panel.Muted.TLabel",
                font=font_tuple("data_label"),
                anchor="e",
            ).grid(row=i, column=0, sticky="e", padx=(0, _GAP_MD), pady=(_GAP_XS, 0))
            var = tk.StringVar(value=default)
            ttk.Label(
                b,
                textvariable=var,
                style="Panel.Success.TLabel",
                font=font_tuple("data_value"),
            ).grid(row=i, column=1, sticky="w", pady=(_GAP_XS, 0))
            self._safety_vars[label] = var

    def _build_quick_start(self, body: ttk.Frame):
        body.columnconfigure(0, weight=1)

        # Caption
        ttk.Label(
            body,
            text="Quick shortcuts — or browse to any folder.",
            style="Panel.Muted.TLabel",
            font=font_tuple("caption"),
        ).grid(row=0, column=0, sticky="w", pady=(0, _GAP_SM))

        # Shortcut buttons row — Documents / Pictures / Downloads
        shortcut = ttk.Frame(body, style="Panel.TFrame")
        shortcut.grid(row=1, column=0, sticky="ew", pady=(0, _GAP_MD))
        for idx, (label, candidate) in enumerate(
            [
                ("Documents", Path.home() / "Documents"),
                ("Pictures",  Path.home() / "Pictures"),
                ("Downloads", Path.home() / "Downloads"),
            ]
        ):
            tb.Button(
                shortcut,
                text=label,
                bootstyle="secondary",
                command=lambda p=candidate: self._set_path(str(p)),
            ).grid(row=0, column=idx, sticky="w", padx=(0, _GAP_SM))

        # Drop zone — dashed groove, taller target
        dz = ttk.Label(
            body,
            text=f"  {IC.FOLDER}   Drop folder here  ·  or click to browse  ",
            relief="groove",
            anchor="center",
            cursor="hand2",
            padding=(_GAP_LG, _GAP_MD),
            font=font_tuple("body"),
        )
        dz.grid(row=2, column=0, sticky="ew", pady=(0, _GAP_SM))
        dz.bind("<Button-1>", lambda e: self._on_browse())
        self._drop_label = dz
        self._enable_drag_drop(dz)

        # Path entry + Browse button
        pf = ttk.Frame(body, style="Panel.TFrame")
        pf.grid(row=3, column=0, sticky="ew", pady=(0, _GAP_SM))
        pf.columnconfigure(0, weight=1)
        self._path_var = tk.StringVar()
        ttk.Entry(
            pf,
            textvariable=self._path_var,
        ).grid(row=0, column=0, sticky="ew", padx=(0, _GAP_SM), ipady=_GAP_XS)
        tb.Button(
            pf,
            text="Browse…",
            bootstyle="secondary",
            command=self._on_browse,
        ).grid(row=0, column=1)

        # Hidden option vars (advanced surface; not shown on Mission)
        self._recurse_var  = tk.BooleanVar(value=True)
        self._hidden_var   = tk.BooleanVar(value=False)
        self._min_size_var = tk.IntVar(value=1024)
        cats = list_categories()
        self._media_var  = tk.StringVar(value=get_category_label(cats[0]))
        self._media_map  = {get_category_label(c): c for c in cats}

        # Recent folders strip
        self._recent_frame = ttk.Frame(body, style="Panel.TFrame")
        self._recent_frame.grid(row=4, column=0, sticky="ew", pady=(0, _GAP_SM))

        # Action buttons — full-width equal pair
        btn_f = ttk.Frame(body, style="Panel.TFrame")
        btn_f.grid(row=5, column=0, sticky="ew")
        btn_f.columnconfigure(0, weight=1)
        btn_f.columnconfigure(1, weight=1)
        tb.Button(
            btn_f,
            text=f"{IC.SCAN}  Start Scan",
            bootstyle="primary",
            command=self._on_start,
        ).grid(row=0, column=0, sticky="ew", padx=(0, _GAP_SM), ipady=_GAP_SM)
        self._resume_btn = tb.Button(
            btn_f,
            text=f"{IC.RESUME}  Resume",
            bootstyle="secondary",
            command=self._on_resume,
            state="disabled",
        )
        self._resume_btn.grid(row=0, column=1, sticky="ew", ipady=_GAP_SM)

    def _build_capabilities(self, body: ttk.Frame):
        self._cap_vars: dict[str, tk.StringVar] = {}
        caps = [
            ("xxhash",      "xxhash64 backend"),
            ("blake3",      "blake3 backend"),
            ("pillow",      "Thumbnail preview"),
            ("send2trash",  "Trash protection"),
            ("durable",     "Durable pipeline"),
            ("revalidation","Pre-delete revalidation"),
            ("audit",       "Audit logging"),
        ]
        for i, (key, label) in enumerate(caps):
            row_f = ttk.Frame(body, style="Panel.TFrame")
            row_f.grid(row=i, column=0, sticky="ew", pady=(_GAP_XS, 0))
            var = tk.StringVar(value="—")
            ttk.Label(
                row_f,
                textvariable=var,
                style="Panel.Success.TLabel",
                font=font_tuple("data_value"),
                width=3,
            ).pack(side="left")
            ttk.Label(
                row_f,
                text=label,
                style="Panel.TLabel",
                font=font_tuple("data_label"),
            ).pack(side="left", padx=(_GAP_SM, 0))
            self._cap_vars[key] = var

    def _build_recent_sessions(self, body: ttk.Frame):
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        self._recent_cards = ttk.Frame(body, style="Panel.TFrame")
        self._recent_cards.grid(row=0, column=0, sticky="nsew")
        self._empty_recent = ttk.Label(
            body,
            text="No recent sessions yet. Start a scan to populate the dashboard.",
            style="Panel.Muted.TLabel",
            font=font_tuple("body"),
        )
        self._empty_recent.grid(row=1, column=0, sticky="w", pady=(_GAP_SM, 0))

    # ----------------------------------------------------------------
    # Store subscription
    # ----------------------------------------------------------------
    def attach_store(self, store: "UIStateStore") -> None:
        if self._store_unsub:
            self._store_unsub()
        self._store = store

        def on_state(state):
            self._sync_mission_layout()
            mission = getattr(state, "mission", None)
            if mission is not None:
                self.vm.refresh_from_mission_state(state)
                self._update_engine_card()
                self._update_last_scan()
                self._update_capabilities()
                self._update_recent_sessions()
                self._update_recent_folders()
                has_resumable = bool(self.vm.resumable_scan_ids)
                self._resume_btn.configure(state="normal" if has_resumable else "disabled")

        self._store_unsub = store.subscribe(on_state, fire_immediately=True)

    def detach_store(self) -> None:
        if self._store_unsub:
            self._store_unsub()
            self._store_unsub = None
        self._store = None

    def _sync_mission_layout(self) -> None:
        """Simple ui_mode: last-scan only + no recent sessions / tour. Advanced: honor mission_show_*."""
        mode = "simple"
        if self._store is not None:
            mode = getattr(self._store.state, "ui_mode", "simple")
        s = self._ui_state.settings if self._ui_state else None
        simple = mode != "advanced"
        if simple:
            show_engine = show_safety = False
            show_recent = False
            show_tour   = False
        else:
            show_engine = s.mission_show_capabilities if s else True
            show_safety = s.mission_show_warnings    if s else True
            show_recent = True
            show_tour   = True

        self._layout_mission_readiness_row(show_engine, show_safety)
        if show_recent:
            self._recent_card.grid()
        else:
            self._recent_card.grid_remove()
        if show_tour:
            self._tour_btn.grid(row=0, column=3, sticky="w")
        else:
            self._tour_btn.grid_remove()

        if show_recent:
            self._content.rowconfigure(2, weight=1)
        else:
            self._content.rowconfigure(2, weight=0)

        self._apply_mission_density(simple)

    def _apply_mission_density(self, simple: bool) -> None:
        """Sprint 1 (P0): tighter padding in Simple mode; defaults for Advanced."""
        if simple:
            pad        = _S(5)    # 20px
            hero_tail  = _GAP_MD
            ready_tail = _GAP_MD
            recent_tail = _GAP_MD
            quick_tail = _GAP_SM
        else:
            pad        = _PAD_PAGE
            hero_tail  = _GAP_LG
            ready_tail = _GAP_LG
            recent_tail = _GAP_LG
            quick_tail = _GAP_MD
        self._content.configure(padding=(pad, pad, pad, pad))
        self._hero.grid_configure(pady=(0, hero_tail))
        self._ready.grid_configure(pady=(0, ready_tail))
        self._recent_card.grid_configure(pady=(0, recent_tail))
        self._quick_card.grid_configure(pady=(0, quick_tail))

    def _layout_mission_readiness_row(self, show_engine: bool, show_safety: bool) -> None:
        ec, lc, sc = self._engine_card, self._last_scan_card, self._safety_card
        if show_engine and show_safety:
            ec.grid(row=0, column=0, sticky="nsew", padx=(0, _GAP_SM))
            lc.grid(row=0, column=1, sticky="nsew", padx=(_GAP_SM // 2, _GAP_SM // 2))
            sc.grid(row=0, column=2, sticky="nsew", padx=(_GAP_SM, 0))
            return
        if show_engine and not show_safety:
            ec.grid(row=0, column=0, sticky="nsew", padx=(0, _GAP_SM))
            lc.grid(row=0, column=1, columnspan=2, sticky="nsew", padx=(_GAP_SM // 2, 0))
            sc.grid_remove()
            return
        if not show_engine and show_safety:
            ec.grid_remove()
            lc.grid(row=0, column=0, columnspan=2, sticky="nsew", padx=(0, _GAP_SM))
            sc.grid(row=0, column=2, sticky="nsew", padx=(_GAP_SM, 0))
            return
        ec.grid_remove()
        sc.grid_remove()
        lc.grid(row=0, column=0, columnspan=3, sticky="nsew")

    # ----------------------------------------------------------------
    # Logic
    # ----------------------------------------------------------------
    def on_show(self):
        if self._on_request_refresh:
            self._on_request_refresh()
        else:
            self._refresh()
        self._sync_mission_layout()

    def sync_chrome(self) -> None:
        """Re-apply Mission layout from `ui_mode` + `AppSettings`."""
        self._sync_mission_layout()

    def _refresh(self):
        self.vm.refresh_from_coordinator(self.coordinator)
        self._update_engine_card()
        self._update_last_scan()
        self._update_capabilities()
        self._update_recent_sessions()
        self._update_recent_folders()
        has_resumable = bool(
            self.vm.recent_sessions
            and any(
                s.get("scan_id") in set(self.coordinator.get_resumable_scan_ids() or [])
                for s in self.vm.recent_sessions
            )
        )
        self._resume_btn.configure(state="normal" if has_resumable else "disabled")
        self._sync_mission_layout()

    def _update_engine_card(self):
        e    = self.vm.engine_status
        caps = self.vm.capabilities_by_name()
        self._eng_rows["Hash backend"].set(e.hash_backend)
        self._eng_rows["Resume"].set(f"{IC.OK} Yes" if e.resume_available else f"{IC.ERROR} No")
        self._eng_rows["Schema"].set(str(e.schema_version))
        self._eng_rows["Health"].set(f"{IC.OK} Healthy")
        self._eng_rows["Pipeline"].set("Durable")
        if hasattr(self, "_safety_vars"):
            trash_ok       = caps.get("send2trash", False)
            revalidate_ok  = True
            audit_ok       = True
            self._safety_vars["Status"].set(f"{IC.OK} Active"   if trash_ok else f"{IC.WARN} Limited")
            self._safety_vars["Pre-delete revalidation"].set(
                f"{IC.OK} Enabled" if revalidate_ok else f"{IC.WARN} Limited"
            )
            self._safety_vars["Audit logging"].set(f"{IC.OK} Enabled" if audit_ok else f"{IC.WARN} Limited")

    def _update_last_scan(self):
        ls = self.vm.last_scan
        if ls:
            self._last_metrics["files"].update(fmt_int(ls.files_scanned))
            self._last_metrics["groups"].update(fmt_int(ls.duplicate_groups))
            self._last_metrics["reclaim"].update(fmt_bytes(ls.reclaimable_bytes))
            self._last_metrics["dur"].update(fmt_duration(ls.duration_s))

    def _update_capabilities(self):
        caps = self.vm.capabilities_by_name()
        for key, var in self._cap_vars.items():
            if key in ("durable", "revalidation", "audit"):
                var.set(IC.OK)
            elif key in caps:
                var.set(IC.OK if caps[key] else IC.WARN)
            else:
                var.set("—")

    def _update_recent_sessions(self):
        """Repaint recent session cards from the latest VM snapshot."""
        for w in self._recent_cards.winfo_children():
            w.destroy()
        resumable = set(
            getattr(self.vm, "resumable_scan_ids", None)
            or self.coordinator.get_resumable_scan_ids()
            or []
        )
        if not self.vm.recent_sessions:
            self._welcome_var.set("")
            self._empty_recent.grid()
            return
        self._empty_recent.grid_remove()
        self._welcome_var.set("")
        max_cards = 3
        cols      = 3
        for i, item in enumerate(self.vm.recent_sessions[:max_cards]):
            scan_id = item.get("scan_id", "")
            status  = item.get("status", "—")
            if scan_id in resumable:
                status = "resumable"
            row = i // cols
            col = i % cols
            self._recent_cards.columnconfigure(col, weight=1)
            self._build_recent_session_card(item=item, status=status, row=row, col=col)

    def _build_recent_session_card(self, *, item: dict, status: str, row: int, col: int) -> None:
        """Render one recent-session card; extracted to keep list renderer compact."""
        scan_id = item.get("scan_id", "")
        started = fmt_dt(item.get("started_at", ""))
        roots_str = self._recent_roots_label(item.get("roots") or [])
        files = fmt_int(item.get("files_scanned", 0))
        groups = fmt_int(item.get("duplicates_found", 0))
        reclaim = fmt_bytes(item.get("reclaimable_bytes", 0))

        card = ttk.Frame(self._recent_cards, style="Panel.TFrame", padding=(_GAP_MD, _GAP_MD))
        card.grid(row=row, column=col, sticky="nsew", padx=_GAP_SM, pady=_GAP_SM)
        card.columnconfigure(0, weight=1)

        ttk.Label(
            card, text=roots_str or "Recent scan", style="Panel.Secondary.TLabel", font=font_tuple("body_bold")
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(card, text=started, style="Panel.Muted.TLabel", font=font_tuple("caption")).grid(
            row=1, column=0, sticky="w", pady=(_GAP_XS, _GAP_XS)
        )
        ttk.Label(card, text=f"{files} files  ·  {groups} groups", style="Panel.TLabel", font=font_tuple("body")).grid(
            row=2, column=0, sticky="w"
        )
        ttk.Label(
            card,
            text=f"{IC.RECLAIM}  Reclaimable: {reclaim}",
            style="Panel.Success.TLabel",
            font=font_tuple("body_bold"),
        ).grid(row=3, column=0, sticky="w", pady=(_GAP_XS, _GAP_MD))

        action_row = ttk.Frame(card, style="Panel.TFrame")
        action_row.grid(row=4, column=0, sticky="ew")
        action_row.columnconfigure(1, weight=1)
        pill_text = "Resumable" if status == "resumable" else status.title()
        ttk.Label(
            action_row,
            text=pill_text,
            style="Panel.Accent.TLabel" if status == "resumable" else "Panel.Muted.TLabel",
            font=font_tuple("caption"),
        ).grid(row=0, column=0, sticky="w")
        action_text = "Resume" if status == "resumable" else "Review"
        action_cmd = (
            (lambda sid=scan_id: self.on_resume_scan(sid)) if status == "resumable" else self._on_open_last_review
        )
        tb.Button(
            action_row,
            text=action_text,
            bootstyle="success" if status == "resumable" else "secondary",
            command=action_cmd,
        ).grid(row=0, column=2, sticky="e")

    def _recent_roots_label(self, roots: list[str]) -> str:
        """Compact root labels for cards; cap to two entries."""
        roots_str = ", ".join(Path(r).name for r in roots[:2])
        if len(roots) > 2:
            roots_str += "…"
        return roots_str

    def _show_quick_tour(self) -> None:
        messagebox.showinfo(
            "CEREBRO Quick Tour",
            "Scan → Review → Cleanup\n\n"
            "1) Start Scan to discover duplicates.\n"
            "2) Use Decision Studio to choose keep/delete safely.\n"
            "3) Execute cleanup with preview and audit protections.",
        )

    def _update_recent_folders(self):
        for w in self._recent_frame.winfo_children():
            w.destroy()
        if self.vm.recent_folders:
            ttk.Label(
                self._recent_frame,
                text="Recent:",
                style="Panel.Muted.TLabel",
                font=font_tuple("data_label"),
            ).pack(side="left")
            for folder in self.vm.recent_folders[:4]:
                name = Path(folder).name or folder
                btn  = tb.Button(
                    self._recent_frame,
                    text=name,
                    bootstyle="secondary",
                    command=lambda f=folder: self._set_path(f),
                )
                btn.pack(side="left", padx=(_GAP_XS, 0))

    def _on_session_select(self, iid: str):
        pass

    def _on_session_double_click(self, iid: str):
        self.on_resume_scan(iid)

    def _on_browse(self):
        path = filedialog.askdirectory(title="Select Folder to Scan")
        if path:
            self._set_path(path)

    def _set_path(self, path: str):
        resolved = str(Path(path).resolve())
        self._path_var.set(resolved)
        self._selected_path = Path(resolved)

    def _enable_drag_drop(self, widget):
        if DND_FILES is None:
            return
        try:
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", self._on_drop)
            widget.configure(text=f"  {IC.FOLDER}   Drop folder here  ·  or click to browse  ")
        except Exception as e:
            _log.debug("Drag-and-drop unavailable: %s", e)

    def _on_drop(self, event):
        data = (event.data or "").strip()
        if not data:
            return
        try:
            paths = self.tk.splitlist(data)
        except Exception as e:
            _log.debug("Drop parsing failed, using raw payload: %s", e)
            paths = [data]
        for p in paths:
            candidate = p.strip("{}").strip()
            if candidate:
                path_obj = Path(candidate)
                if path_obj.exists() and path_obj.is_dir():
                    self._set_path(str(path_obj))
                    break

    def _on_start(self):
        path_str = self._path_var.get().strip()
        if not path_str:
            messagebox.showerror("Error", "Please select a folder to scan.")
            return
        path = Path(path_str).resolve()
        if not path.exists() or not path.is_dir():
            messagebox.showerror("Error", f"Invalid path: {path}")
            return
        label    = self._media_var.get()
        media_key = self._media_map.get(label, "all")
        options  = {
            "min_size":        self._min_size_var.get(),
            "include_hidden":  self._hidden_var.get(),
            "scan_subfolders": self._recurse_var.get(),
            "media_category":  media_key,
        }
        try:
            self.coordinator.add_recent_folder(path)
        except Exception as e:
            _log.warning("Failed to add recent folder '%s': %s", path, e)
        self.on_start_scan(path, options)

    def _on_resume(self):
        try:
            resumable = self.coordinator.get_resumable_scan_ids() or []
        except Exception:
            resumable = []
        if not resumable:
            messagebox.showinfo("Resume", "No resumable scan found.")
            return
        self.on_resume_scan(resumable[0])
