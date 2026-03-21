"""
Optional CustomTkinter preview window (does not replace the main shell).

Install: pip install customtkinter  (extra: modern-ui)
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox


def open_ctk_preview(parent: tk.Misc | None) -> None:
    try:
        import customtkinter as ctk
    except ImportError:
        messagebox.showinfo(
            "Optional dependency",
            "Install CustomTkinter for this preview:\n  pip install customtkinter",
            parent=parent,
        )
        return

    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    w = ctk.CTkToplevel(parent)
    w.title("CustomTkinter — optional preview")
    w.geometry("420x280")
    w.transient(parent)
    ctk.CTkLabel(
        w,
        text="Standalone CTK preview (main CEREBRO shell stays ttk + Sun Valley).",
        wraplength=380,
    ).pack(pady=(24, 12), padx=16)
    ctk.CTkButton(w, text="Accent", height=36).pack(pady=8)
    ctk.CTkButton(w, text="Close", command=w.destroy, fg_color="gray40").pack(pady=16)
