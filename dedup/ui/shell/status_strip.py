"""
StatusStrip — global bottom status strip.

Read-only telemetry (not menus): session, phase, engine, checkpoint, workers, warnings,
storage schema, and scan intent. In **Advanced** mode, clicking the strip opens **Diagnostics**
(one overflow affordance). Colors: green=healthy, amber=warning, red=failure.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable

from ..theme.design_system import SPACING, font_tuple
from ..theme.theme_manager import get_theme_manager
from ..utils.icons import IC


class StatusStrip(tk.Frame):
    """Bottom status strip — always visible."""

    HEIGHT = 28

    def __init__(self, parent, **kwargs):
        super().__init__(parent, height=self.HEIGHT, **kwargs)
        self.pack_propagate(False)
        self._tm = get_theme_manager()
        self._full_session_id = ""
        self._last_engine_health = "Healthy"
        self._last_warnings = 0
        self._ui_mode = "simple"
        self._strip_click_handler: Callable[[tk.Event | None], None] | None = None
        self._click_bind_targets: list[tk.Misc] = []
        self._session_tip: tk.Toplevel | None = None
        self._build()
        self._tm.subscribe(self._apply_colors)
        self._apply_colors(self._tm.tokens)

    def _build(self) -> None:
        self._sep = tk.Frame(self, height=3)
        self._sep.pack(fill="x")

        row = tk.Frame(self)
        row.pack(fill="both", expand=True, padx=SPACING["md"])
        self._row = row

        def _cell_pair(icon: str, var: tk.StringVar) -> tuple[tk.Frame, tk.Label]:
            cell = tk.Frame(row)
            tk.Label(cell, text=icon, font=font_tuple("strip")).pack(side="left", padx=(0, SPACING["xs"]))
            lbl = tk.Label(cell, textvariable=var, font=font_tuple("strip"))
            lbl.pack(side="left")
            return cell, lbl

        self._session_var = tk.StringVar(value="Session: —")
        self._phase_var = tk.StringVar(value="Phase: Idle")
        self._engine_var = tk.StringVar(value="Engine: Healthy")
        self._ckpt_var = tk.StringVar(value="Checkpoint: —")
        self._workers_var = tk.StringVar(value="Workers: 0")
        self._warnings_var = tk.StringVar(value="Warnings: 0")
        self._storage_var = tk.StringVar(value="")
        self._intent_var = tk.StringVar(value="Intent: idle")

        self._cells: dict[str, tk.Frame] = {}
        self._labels: dict[str, tk.Label] = {}
        specs = [
            ("session", IC.CHECKPOINT, self._session_var),
            ("phase", IC.RUNNING, self._phase_var),
            ("engine", IC.SHIELD, self._engine_var),
            ("ckpt", IC.CHECKPOINT, self._ckpt_var),
            ("workers", IC.WORKERS, self._workers_var),
            ("warnings", IC.WARN, self._warnings_var),
            ("storage", IC.SCHEMA, self._storage_var),
            ("intent", IC.INFO, self._intent_var),
        ]
        for key, icon, var in specs:
            cell, lbl = _cell_pair(icon, var)
            self._cells[key] = cell
            self._labels[key] = lbl

        t0 = self._tm.tokens
        self._sep_g1 = tk.Frame(row, width=1, bg=t0["border_soft"])
        self._sep_g2 = tk.Frame(row, width=1, bg=t0["border_soft"])

        pad = (0, SPACING["lg"])
        self._cells["session"].pack(side="left", padx=pad)
        self._cells["phase"].pack(side="left", padx=pad)
        self._cells["engine"].pack(side="left", padx=pad)
        self._sep_g1.pack(side="left", fill="y", pady=4, padx=SPACING["sm"])
        self._cells["ckpt"].pack(side="left", padx=pad)
        self._cells["workers"].pack(side="left", padx=pad)
        self._cells["warnings"].pack(side="left", padx=pad)
        self._sep_g2.pack(side="left", fill="y", pady=4, padx=SPACING["sm"])
        self._cells["storage"].pack(side="left", padx=pad)
        self._cells["intent"].pack(side="left", padx=pad)

        self._right_spacer = tk.Frame(row)
        self._right_spacer.pack(side="left", fill="x", expand=True)

        self._refresh_click_targets()
        self._bind_strip_click()
        self._bind_session_tooltip()

    def set_ui_mode(self, mode: str) -> None:
        """Hide storage + intent in Simple mode; show full strip in Advanced."""
        self._ui_mode = mode
        simple = mode != "advanced"
        if simple:
            self._sep_g2.pack_forget()
            self._cells["storage"].pack_forget()
            self._cells["intent"].pack_forget()
        else:
            if self._cells["storage"].winfo_manager() != "pack":
                # Pack before the right spacer so order is: … warnings | sep2 | storage | intent | spacer
                self._cells["intent"].pack(side="left", padx=(0, SPACING["lg"]), before=self._right_spacer)
                self._cells["storage"].pack(side="left", padx=(0, SPACING["lg"]), before=self._cells["intent"])
                self._sep_g2.pack(
                    side="left",
                    fill="y",
                    pady=4,
                    padx=SPACING["sm"],
                    before=self._cells["storage"],
                )
        self._refresh_click_targets()
        self._bind_strip_click()
        self._sync_strip_cursor()

    def set_strip_click_handler(self, handler: Callable[[tk.Event | None], None] | None) -> None:
        """Advanced: optional click handler (e.g. navigate to Diagnostics)."""
        self._strip_click_handler = handler
        self._sync_strip_cursor()

    def _sync_strip_cursor(self) -> None:
        cur = "hand2" if self._ui_mode == "advanced" and self._strip_click_handler is not None else "arrow"
        for w in self._click_bind_targets:
            try:
                w.configure(cursor=cur)
            except tk.TclError:
                pass

    def _refresh_click_targets(self) -> None:
        self._click_bind_targets = [
            self,
            self._sep,
            self._row,
            self._sep_g1,
            self._sep_g2,
            self._right_spacer,
        ]
        for _k, cell in self._cells.items():
            if not cell.winfo_ismapped():
                continue
            self._click_bind_targets.append(cell)
            for ch in cell.winfo_children():
                self._click_bind_targets.append(ch)

    def _bind_strip_click(self) -> None:
        def _go(e: tk.Event) -> None:
            self._on_strip_click(e)

        for w in self._click_bind_targets:
            w.bind("<Button-1>", _go)

    def _on_strip_click(self, event: tk.Event) -> None:
        if self._ui_mode != "advanced" or self._strip_click_handler is None:
            return
        self._strip_click_handler(event)

    def _bind_session_tooltip(self) -> None:
        def _hide(_e: tk.Event | None = None) -> None:
            if self._session_tip is not None and self._session_tip.winfo_exists():
                self._session_tip.destroy()
            self._session_tip = None

        def _show(e: tk.Event) -> None:
            _hide()
            full = self._full_session_id or ""
            text = f"Session: {full}" if full else "No active session"
            t = self._tm.tokens
            top = tk.Toplevel(self)
            top.wm_overrideredirect(True)
            top.wm_geometry(f"+{e.x_root + 12}+{e.y_root + 12}")
            tk.Label(
                top,
                text=text,
                justify="left",
                bg=t["bg_canvas"],
                fg=t["text_primary"],
                padx=SPACING["sm"],
                pady=SPACING["xs"],
                font=font_tuple("caption"),
            ).pack()
            self._session_tip = top

        cell = self._cells["session"]
        for w in (cell, *cell.winfo_children()):
            w.bind("<Enter>", _show)
            w.bind("<Leave>", lambda _e: _hide())

    def update_session(
        self,
        session_id: str,
        phase: str,
        engine_health: str = "Healthy",
        checkpoint_ts: str = "—",
        workers: int = 0,
        warnings: int = 0,
        storage_mode: str = "",
    ) -> None:
        self._full_session_id = session_id or ""
        self._last_engine_health = engine_health
        self._last_warnings = warnings
        t = self._tm.tokens
        short = (session_id[:10] + "…") if len(session_id) > 10 else (session_id or "—")
        self._session_var.set(f"Session: {short}")
        self._phase_var.set(f"Phase: {phase or 'Idle'}")
        self._engine_var.set(f"Engine: {engine_health}")
        self._ckpt_var.set(f"Ckpt: {checkpoint_ts}")
        self._workers_var.set(f"Workers: {workers}")
        self._warnings_var.set(f"Warnings: {warnings}")
        self._storage_var.set(storage_mode)

        eng_fg = (
            t["success"]
            if engine_health == "Healthy"
            else (t["warning"] if engine_health == "Warning" else t["danger"])
        )
        self._labels["engine"].configure(foreground=eng_fg)

        warn_fg = t["warning"] if warnings > 0 else t["text_muted"]
        self._labels["warnings"].configure(foreground=warn_fg)

        self._labels["phase"].configure(foreground=t["text_primary"])

    def subscribe_to_hub(self, hub) -> None:
        """
        Subscribe to ProjectionHub session projections.
        Drives the status strip from the canonical SessionProjection.
        """

        def _on_session(proj) -> None:
            import time as _t

            ts = _t.strftime("%H:%M:%S")
            self.update_session(
                session_id=proj.session_id,
                phase=proj.current_phase,
                engine_health=proj.engine_health,
                checkpoint_ts=ts if proj.is_active else "—",
                workers=0,
                warnings=proj.warnings_count,
                storage_mode=f"schema v{proj.schema_version}" if proj.schema_version else "",
            )

        hub.subscribe("session", _on_session)

    def subscribe_to_store(self, store) -> None:
        """
        Subscribe to UIStateStore to show scan intent lifecycle.
        Safe if store or store.scan.last_intent is absent/None — shows "Intent: idle".
        """

        def _on_state(state) -> None:
            scan = getattr(state, "scan", None)
            if scan is None:
                self._intent_var.set("Intent: idle")
                return
            last = getattr(scan, "last_intent", None)
            if last is None:
                self._intent_var.set("Intent: idle")
                return
            status = getattr(last, "status", None) or "idle"
            self._intent_var.set(f"Intent: {status}")

        self._unsub_store = store.subscribe(_on_state, fire_immediately=True)

    def _apply_role_colors(self, t: dict) -> None:
        self._labels["phase"].configure(foreground=t["text_primary"])
        eng = self._last_engine_health
        eng_fg = t["success"] if eng == "Healthy" else (t["warning"] if eng == "Warning" else t["danger"])
        self._labels["engine"].configure(foreground=eng_fg)
        warn_fg = t["warning"] if self._last_warnings > 0 else t["text_muted"]
        self._labels["warnings"].configure(foreground=warn_fg)

    def _apply_colors(self, t: dict) -> None:
        bg = t["bg_sidebar"]
        fg = t["text_muted"]
        self.configure(background=bg)
        self._sep.configure(background=t["border_soft"])
        self._row.configure(background=bg)
        self._sep_g1.configure(background=t["border_soft"])
        self._sep_g2.configure(background=t["border_soft"])
        self._right_spacer.configure(background=bg)
        for cell in self._cells.values():
            cell.configure(background=bg)
            for child in cell.winfo_children():
                child.configure(background=bg, foreground=fg)
        self._apply_role_colors(t)
