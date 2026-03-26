"""
Facade for the draggable accent gradient editor (theme strip).

Delegates to `DraggableGradientEditor` in `dedup.ui.theme.gradient_editor_canvas`.
"""

from __future__ import annotations

from typing import Callable, List, Tuple

from ..theme.gradient_editor_canvas import DraggableGradientEditor

GradientEditor = DraggableGradientEditor

__all__ = ["DraggableGradientEditor", "GradientEditor"]
