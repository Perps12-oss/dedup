"""
Shared state-surface components: loading, empty, degraded, warning, error.

Aligns with docs/LOADING_ERROR_STATES.md. Use store/controller state for copy where possible.
"""

from __future__ import annotations

from tkinter import ttk
from typing import Callable, Optional

from ..theme.design_system import SPACING, font_tuple
from ..utils.icons import IC
from .empty_state import EmptyState

# Variant styles for inline notice and banners
NOTICE_STYLE = {
    "info": "Panel.Accent.TLabel",
    "warning": "Panel.Warning.TLabel",
    "error": "Panel.Danger.TLabel",
}
NOTICE_ICON = {"info": IC.INFO, "warning": IC.WARN, "error": IC.ERROR}


class InlineNotice(ttk.Frame):
    """Short inline message (info / warning / error). Use in toolbars, ribbons, or above content."""

    def __init__(
        self,
        parent,
        message: str = "",
        variant: str = "info",
        action_label: str = "",
        on_action: Optional[Callable] = None,
        **kwargs,
    ):
        super().__init__(parent, **kwargs)
        self._style = NOTICE_STYLE.get(variant, NOTICE_STYLE["info"])
        self._icon = NOTICE_ICON.get(variant, IC.INFO)
        ttk.Label(self, text=self._icon, style=self._style, font=font_tuple("body")).pack(
            side="left", padx=(0, SPACING["sm"])
        )
        self._msg_lbl = ttk.Label(self, text=message, style=self._style, font=font_tuple("body"), wraplength=400)
        self._msg_lbl.pack(side="left", fill="x", expand=True)
        if action_label and on_action:
            ttk.Button(self, text=action_label, style="Ghost.TButton", command=on_action).pack(
                side="left", padx=(SPACING["md"], 0)
            )

    def set_message(self, message: str) -> None:
        self._msg_lbl.configure(text=message)

    def hide(self):
        self.grid_remove()

    def show(self):
        self.grid()


def EmptyStateCard(
    parent,
    heading: str = "Nothing here yet",
    message: str = "",
    action_label: str = "",
    on_action: Optional[Callable] = None,
    icon: str = "○",
    **kwargs,
) -> EmptyState:
    """Standard empty-state card (icon + heading + message + optional CTA). Returns EmptyState."""
    return EmptyState(
        parent,
        icon=icon,
        heading=heading,
        message=message,
        action_label=action_label or "",
        on_action=on_action,
        **kwargs,
    )


class DegradedBanner(ttk.Frame):
    """Full-width banner for degraded mode (e.g. compatibility degraded). Non-blocking."""

    def __init__(self, parent, message: str = "", on_dismiss: Optional[Callable] = None, **kwargs):
        super().__init__(parent, style="Panel.TFrame", padding=(SPACING["md"], SPACING["sm"]), **kwargs)
        self.columnconfigure(1, weight=1)
        ttk.Label(self, text=IC.WARN, style="Panel.Warning.TLabel", font=font_tuple("body")).grid(
            row=0, column=0, padx=(0, SPACING["sm"]), sticky="w"
        )
        self._msg_lbl = ttk.Label(
            self, text=message, style="Panel.Warning.TLabel", font=font_tuple("body"), wraplength=500
        )
        self._msg_lbl.grid(row=0, column=1, sticky="w")
        if on_dismiss:
            ttk.Button(self, text="Dismiss", style="Ghost.TButton", command=on_dismiss).grid(
                row=0, column=2, padx=(SPACING["md"], 0)
            )

    def set_message(self, message: str) -> None:
        self._msg_lbl.configure(text=message)

    def hide(self):
        self.grid_remove()

    def show(self):
        self.grid()


class ErrorPanel(ttk.Frame):
    """Panel for hard errors: message + optional retry. Use for scan error, load error."""

    def __init__(
        self, parent, message: str = "", retry_label: str = "Retry", on_retry: Optional[Callable] = None, **kwargs
    ):
        super().__init__(parent, **kwargs)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        inner = ttk.Frame(self)
        inner.grid(row=0, column=0)
        ttk.Label(inner, text=IC.ERROR, style="Panel.Danger.TLabel", font=font_tuple("empty_icon")).pack(
            pady=(0, SPACING["md"])
        )
        ttk.Label(inner, text="Error", style="Panel.Danger.TLabel", font=font_tuple("section_title")).pack()
        self._msg_lbl = ttk.Label(
            inner,
            text=message,
            style="Panel.Secondary.TLabel",
            font=font_tuple("body"),
            wraplength=320,
            justify="center",
        )
        self._msg_lbl.pack(pady=(SPACING["sm"], SPACING["lg"]))
        if retry_label and on_retry:
            ttk.Button(inner, text=retry_label, style="Primary.TButton", command=on_retry).pack()

    def set_message(self, message: str) -> None:
        self._msg_lbl.configure(text=message)

    def hide(self):
        self.grid_remove()

    def show(self):
        self.grid()
