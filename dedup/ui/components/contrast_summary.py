"""WCAG contrast summary label driven by ContrastSummary model."""

from __future__ import annotations

from tkinter import ttk

from dedup.models.theme import ContrastSummary

class ContrastSummaryLabel(ttk.Label):
    """Updates text from a ContrastSummary dataclass."""

    def set_summary(self, summary: ContrastSummary) -> None:
        self.configure(text=summary.ratio_label)

    def clear(self) -> None:
        self.configure(text="")


def build_contrast_label(parent, **kwargs) -> ContrastSummaryLabel:
    return ContrastSummaryLabel(parent, style="Muted.TLabel", font=("Consolas", 10), justify="left", **kwargs)
