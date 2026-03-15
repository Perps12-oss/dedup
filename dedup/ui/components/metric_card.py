"""
MetricCard — reusable stat card for CEREBRO dashboard.
Variants: neutral, positive (success), warning, danger, accent.
"""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from typing import Optional


VARIANT_STYLES = {
    "neutral":  ("Panel.TFrame", "Panel.TLabel",         "Panel.Secondary.TLabel"),
    "positive": ("Panel.TFrame", "Panel.Success.TLabel", "Panel.Secondary.TLabel"),
    "warning":  ("Panel.TFrame", "Panel.Warning.TLabel", "Panel.Secondary.TLabel"),
    "danger":   ("Panel.TFrame", "Panel.Danger.TLabel",  "Panel.Secondary.TLabel"),
    "accent":   ("Panel.TFrame", "Panel.Accent.TLabel",  "Panel.Secondary.TLabel"),
}


class MetricCard(ttk.Frame):
    """
    Single metric card.

        ┌─────────────────────┐
        │  LABEL              │
        │  VALUE              │
        │  sub_label          │
        └─────────────────────┘
    """

    def __init__(
        self,
        parent,
        label: str,
        value: str = "—",
        sub_label: str = "",
        icon: str = "",
        variant: str = "neutral",
        width: int = 160,
        **kwargs,
    ):
        frame_style, val_style, sub_style = VARIANT_STYLES.get(variant, VARIANT_STYLES["neutral"])
        super().__init__(parent, style=frame_style, padding=(14, 10), **kwargs)
        self._val_style = val_style
        self._sub_style = sub_style

        if width:
            self.configure(width=width)

        # Label row
        label_text = f"{icon}  {label}" if icon else label
        self._label_var = tk.StringVar(value=label_text)
        ttk.Label(self, textvariable=self._label_var,
                  style=sub_style,
                  font=("Segoe UI", 8)).pack(anchor="w")

        # Value
        self._value_var = tk.StringVar(value=value)
        ttk.Label(self, textvariable=self._value_var,
                  style=val_style,
                  font=("Segoe UI", 18, "bold")).pack(anchor="w", pady=(2, 0))

        # Sub-label
        self._sub_var = tk.StringVar(value=sub_label)
        self._sub_lbl = ttk.Label(self, textvariable=self._sub_var,
                                  style=sub_style,
                                  font=("Segoe UI", 8))
        self._sub_lbl.pack(anchor="w")

    def update(self, value: str, sub_label: str = "", label: str = ""):
        if value is not None:
            self._value_var.set(value)
        if sub_label is not None:
            self._sub_var.set(sub_label)
        if label:
            current = self._label_var.get()
            # preserve icon prefix if any
            self._label_var.set(label)

    def set_variant(self, variant: str):
        _, val_style, sub_style = VARIANT_STYLES.get(variant, VARIANT_STYLES["neutral"])
        self._val_style = val_style
