"""
CTk-styled tooltips. CustomTkinter does not ship CTkToolTip in all versions;
this provides the same API pattern (attach to any widget, show on hover).
"""

from __future__ import annotations

import tkinter as tk

import customtkinter as ctk


class CTkToolTip:
    """Show a themed tooltip window after a short delay when the pointer rests on ``widget``."""

    def __init__(
        self,
        widget: tk.Widget,
        message: str,
        *,
        delay_ms: int = 450,
        wraplength: int = 320,
    ) -> None:
        self._widget = widget
        self._message = message
        self._delay_ms = delay_ms
        self._wraplength = wraplength
        self._after_id: str | None = None
        self._tip: ctk.CTkToplevel | None = None
        widget.bind("<Enter>", self._on_enter, add=True)
        widget.bind("<Leave>", self._on_leave, add=True)
        widget.bind("<Button>", self._on_leave, add=True)

    def configure(self, message: str | None = None) -> None:
        if message is not None:
            self._message = message
        if self._tip is not None and self._tip.winfo_exists():
            for c in self._tip.winfo_children():
                if isinstance(c, ctk.CTkLabel):
                    c.configure(text=self._message)

    def _on_enter(self, _event: tk.Event | None = None) -> None:
        self._cancel_scheduled()
        try:
            self._after_id = self._widget.after(self._delay_ms, self._show)
        except (tk.TclError, RuntimeError):
            pass

    def _on_leave(self, _event: tk.Event | None = None) -> None:
        self._cancel_scheduled()
        self._destroy_tip()

    def _cancel_scheduled(self) -> None:
        if self._after_id is not None:
            try:
                self._widget.after_cancel(self._after_id)
            except (tk.TclError, RuntimeError, ValueError):
                pass
            self._after_id = None

    def _show(self) -> None:
        self._after_id = None
        if self._tip is not None:
            return
        try:
            top = self._widget.winfo_toplevel()
        except (tk.TclError, RuntimeError):
            return
        tip = ctk.CTkToplevel(top)
        tip.withdraw()
        tip.overrideredirect(True)
        try:
            tip.attributes("-topmost", True)
        except (tk.TclError, RuntimeError):
            pass
        tip.configure(fg_color=("#1e293b", "#0f172a"))
        lbl = ctk.CTkLabel(
            tip,
            text=self._message,
            text_color=("#e2e8f0", "#e2e8f0"),
            font=ctk.CTkFont(size=12),
            wraplength=self._wraplength,
            justify="left",
        )
        lbl.pack(padx=10, pady=8)
        tip.update_idletasks()
        try:
            x = int(self._widget.winfo_rootx() + self._widget.winfo_width() // 2)
            y = int(self._widget.winfo_rooty() + self._widget.winfo_height() + 6)
            tip.geometry(f"+{x}+{y}")
        except (tk.TclError, RuntimeError, ValueError):
            pass
        tip.deiconify()
        self._tip = tip

    def _destroy_tip(self) -> None:
        if self._tip is not None:
            try:
                self._tip.destroy()
            except (tk.TclError, RuntimeError):
                pass
            self._tip = None
