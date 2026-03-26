"""
Reusable UI building blocks.

Most modules here are **ttk-based** widgets kept for **unit tests** (e.g. ``review_workspace``,
``safety_panel``) and helpers used by ``ReviewVM`` / projections. The **CustomTkinter** shell
(``dedup.ui.ctk_app`` / ``ctk_pages``) does not import this package wholesale — import
submodules explicitly, e.g. ``from dedup.ui.components.toast_manager import ToastManager``.
"""
