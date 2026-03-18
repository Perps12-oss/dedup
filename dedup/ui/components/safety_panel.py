"""
SafetyPanel — persistent companion near destructive actions.
Shows deletion mode, revalidation status, audit status, risk summary.
"""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from typing import Optional, Callable

from ..utils.formatting import fmt_bytes, fmt_int
from ..utils.icons import IC
from ..theme.design_system import font_tuple, SPACING
from .decision_state import SAFETY_RAIL


class SafetyPanel(ttk.Frame):
    """Right-side deletion plan + safety summary panel."""

    def __init__(self, parent, on_dry_run: Optional[Callable] = None,
                 on_execute: Optional[Callable] = None, **kwargs):
        super().__init__(parent, style="Panel.TFrame", **kwargs)
        self._on_dry_run = on_dry_run
        self._on_execute = on_execute
        self._build()

    def _build(self):
        t = self
        t.columnconfigure(0, weight=1)
        row = 0

        # Title — Decision & Safety Rail
        ttk.Label(t, text=f"{IC.SHIELD}  Deletion Plan",
                  style="Panel.Secondary.TLabel",
                  font=font_tuple("card_title")).grid(
            row=row, column=0, sticky="w", padx=SPACING["lg"], pady=(SPACING["lg"], SPACING["sm"]))
        row += 1
        ttk.Separator(t, orient="horizontal").grid(row=row, column=0, sticky="ew", padx=SPACING["md"])
        row += 1

        body = ttk.Frame(t, style="Panel.TFrame", padding=(SPACING["lg"], SPACING["md"]))
        body.grid(row=row, column=0, sticky="ew")
        body.columnconfigure(1, weight=1)
        row += 1
        br = 0

        def _row(label, var_or_val, style="Panel.Secondary.TLabel"):
            ttk.Label(body, text=label + ":", style="Panel.Muted.TLabel",
                      font=font_tuple("data_label")).grid(row=br, column=0, sticky="w", pady=1)
            if isinstance(var_or_val, tk.Variable):
                ttk.Label(body, textvariable=var_or_val, style=style,
                          font=font_tuple("data_value")).grid(
                    row=br, column=1, sticky="w", padx=(SPACING["md"], 0))
            else:
                ttk.Label(body, text=var_or_val, style=style,
                          font=font_tuple("data_value")).grid(
                    row=br, column=1, sticky="w", padx=(SPACING["md"], 0))
            return br + 1

        self._mode_var     = tk.StringVar(value="Trash")
        self._revalid_var  = tk.StringVar(value="ON")
        self._audit_var    = tk.StringVar(value="ACTIVE")
        self._del_count    = tk.StringVar(value="0")
        self._keep_count   = tk.StringVar(value="0")
        self._reclaim_var  = tk.StringVar(value="—")
        self._risk_var     = tk.StringVar(value="None")

        br = _row("Delete mode",   self._mode_var)
        br = _row("Revalidation",  self._revalid_var, "Panel.Success.TLabel")
        br = _row(f"{IC.AUDIT} Audit",      self._audit_var,   "Panel.Success.TLabel")

        ttk.Separator(body, orient="horizontal").grid(
            row=br, column=0, columnspan=2, sticky="ew", pady=6)
        br += 1

        br = _row("Selected to delete", self._del_count)
        br = _row("Files kept",         self._keep_count)
        br = _row("Reclaimable",        self._reclaim_var, "Panel.Success.TLabel")

        ttk.Separator(body, orient="horizontal").grid(
            row=br, column=0, columnspan=2, sticky="ew", pady=6)
        br += 1

        br = _row(f"{IC.WARN} Risk flags", self._risk_var, "Panel.Warning.TLabel")

        # One-line readiness: "Ready to delete N files (size)" when plan has items
        self._readiness_var = tk.StringVar(value="")
        self._readiness_lbl = ttk.Label(t, textvariable=self._readiness_var,
                                        style="Panel.Secondary.TLabel",
                                        font=font_tuple("body"), wraplength=200)
        self._readiness_lbl.grid(row=row, column=0, sticky="w", padx=SPACING["lg"], pady=(0, SPACING["xs"]))
        row += 1

        # Preview result (safety rail: show outcome of Preview before Execute)
        self._dryrun_result = tk.StringVar(value="")
        self._dryrun_lbl = ttk.Label(t, textvariable=self._dryrun_result,
                                     style="Panel.Muted.TLabel",
                                     font=font_tuple("data_label"), wraplength=180)
        self._dryrun_lbl.grid(row=row, column=0, sticky="w", padx=SPACING["lg"])
        row += 1

        # Safety rail: Preview first (non-destructive), then Execute (destructive, only when ready)
        btn_frame = ttk.Frame(t, style="Panel.TFrame", padding=(SPACING["lg"], SPACING["sm"], SPACING["lg"], SPACING["lg"]))
        btn_frame.grid(row=row, column=0, sticky="ew")
        btn_frame.columnconfigure(0, weight=1)
        btn_frame.columnconfigure(1, weight=1)
        row += 1

        self._preview_btn = ttk.Button(btn_frame, text=SAFETY_RAIL["preview_effects"],
                                       style="Ghost.TButton",
                                       command=self._do_dry_run)
        self._preview_btn.grid(row=0, column=0, sticky="ew", padx=(0, SPACING["sm"]))

        self._delete_btn = ttk.Button(btn_frame, text=SAFETY_RAIL["execute_deletion"],
                                      style="Danger.TButton",
                                      command=self._do_execute,
                                      state="disabled")
        self._delete_btn.grid(row=0, column=1, sticky="ew", padx=(SPACING["sm"], 0))

    def update_plan(self, del_count: int, keep_count: int, reclaim_bytes: int,
                    risk_flags: int = 0, mode: str = "Trash"):
        self._mode_var.set(mode)
        self._del_count.set(fmt_int(del_count))
        self._keep_count.set(fmt_int(keep_count))
        self._reclaim_var.set(fmt_bytes(reclaim_bytes))
        self._risk_var.set(str(risk_flags) if risk_flags else "None")
        ready = del_count > 0
        self._delete_btn.configure(
            state="normal" if ready else "disabled",
            text=f"Delete {del_count} files" if ready else SAFETY_RAIL["execute_deletion"],
        )
        self._readiness_var.set(
            f"Ready to delete {del_count} files ({fmt_bytes(reclaim_bytes)})" if ready else ""
        )
        self._dryrun_result.set("")

    def set_dry_run_result(self, text: str):
        self._dryrun_result.set(text)

    def _do_dry_run(self):
        if self._on_dry_run:
            self._on_dry_run()

    def _do_execute(self):
        if self._on_execute:
            self._on_execute()
