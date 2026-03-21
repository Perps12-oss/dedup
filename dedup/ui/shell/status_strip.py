"""
StatusStrip — global bottom status strip.

Shows: Session | Phase | Engine Health | Checkpoint | Workers | Warnings | Intent
Intent reflects store.scan.last_intent (idle | accepted | failed | completed).
Color rules: green=safe, amber=warning, red=failure
"""

from __future__ import annotations

import tkinter as tk

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
        self._build()
        self._tm.subscribe(self._apply_colors)
        self._apply_colors(self._tm.tokens)

    def _build(self):
        # Top separator line
        self._sep = tk.Frame(self, height=1)
        self._sep.pack(fill="x")

        row = tk.Frame(self)
        row.pack(fill="both", expand=True, padx=SPACING["md"])
        self._row = row

        def _item(icon: str, var: tk.StringVar):
            cell = tk.Frame(row)
            cell.pack(side="left", padx=(0, SPACING["lg"]))
            tk.Label(cell, text=icon, font=font_tuple("strip")).pack(side="left", padx=(0, SPACING["xs"]))
            self._lbl = tk.Label(cell, textvariable=var, font=font_tuple("strip"))
            self._lbl.pack(side="left")
            return cell, self._lbl

        self._session_var = tk.StringVar(value="Session: —")
        self._phase_var = tk.StringVar(value="Phase: Idle")
        self._engine_var = tk.StringVar(value="Engine: Healthy")
        self._ckpt_var = tk.StringVar(value="Checkpoint: —")
        self._workers_var = tk.StringVar(value="Workers: 0")
        self._warnings_var = tk.StringVar(value="Warnings: 0")
        self._storage_var = tk.StringVar(value="")
        self._intent_var = tk.StringVar(value="Intent: idle")

        self._cells = {}
        self._labels = {}
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
            cell, lbl = _item(icon, var)
            self._cells[key] = cell
            self._labels[key] = lbl

        # Right spacer
        tk.Frame(row).pack(side="left", fill="x", expand=True)

    def update_session(
        self,
        session_id: str,
        phase: str,
        engine_health: str = "Healthy",
        checkpoint_ts: str = "—",
        workers: int = 0,
        warnings: int = 0,
        storage_mode: str = "",
    ):
        t = self._tm.tokens
        short = (session_id[:10] + "…") if len(session_id) > 10 else (session_id or "—")
        self._session_var.set(f"Session: {short}")
        self._phase_var.set(f"Phase: {phase or 'Idle'}")
        self._engine_var.set(f"Engine: {engine_health}")
        self._ckpt_var.set(f"Ckpt: {checkpoint_ts}")
        self._workers_var.set(f"Workers: {workers}")
        self._warnings_var.set(f"Warnings: {warnings}")
        self._storage_var.set(storage_mode)

        # Color the engine health label
        eng_fg = (
            t["success"]
            if engine_health == "Healthy"
            else (t["warning"] if engine_health == "Warning" else t["danger"])
        )
        self._labels["engine"].configure(foreground=eng_fg)

        # Color warnings
        warn_fg = t["warning"] if warnings > 0 else t["text_muted"]
        self._labels["warnings"].configure(foreground=warn_fg)

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

    def _apply_colors(self, t: dict):
        bg = t["bg_sidebar"]
        fg = t["text_muted"]
        self.configure(background=bg)
        self._sep.configure(background=t["border_soft"])
        self._row.configure(background=bg)
        for cell in self._cells.values():
            cell.configure(background=bg)
            for child in cell.winfo_children():
                child.configure(background=bg, foreground=fg)
