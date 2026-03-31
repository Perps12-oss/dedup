"""Shared theme utilities for CTK pages."""

from __future__ import annotations


def apply_label_colors(widget, tokens: dict) -> None:
    """Recursively update all CTkLabel text colors in widget tree with live tokens."""
    txt_primary = str(tokens.get("text_primary", "#F1F5F9"))
    txt_secondary = str(tokens.get("text_secondary", "#94A3B8"))
    txt_muted = str(tokens.get("text_muted", "#6B7280"))
    acc = str(tokens.get("accent_primary", "#3B8ED0"))

    try:
        for child in widget.winfo_children():
            if child.__class__.__name__ == "CTkLabel":
                try:
                    current_color = child.cget("text_color")
                    if current_color and isinstance(current_color, tuple) and len(current_color) == 2:
                        child.configure(text_color=(txt_primary, "#0A0E14"))
                    elif "accent" in str(current_color).lower():
                        child.configure(text_color=acc)
                    elif "muted" in str(current_color).lower():
                        child.configure(text_color=txt_muted)
                    elif "secondary" in str(current_color).lower():
                        child.configure(text_color=txt_secondary)
                    elif current_color:
                        child.configure(text_color=txt_primary)
                except Exception:
                    pass
            elif child.__class__.__name__ in ("CTkFrame", "CTkScrollableFrame"):
                apply_label_colors(child, tokens)
    except Exception:
        pass
