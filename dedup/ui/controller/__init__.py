"""
UI controller — handles intents and delegates to coordinator/services.

ReviewController: handles SetKeep, ClearKeep, PreviewDeletion, ExecuteDeletion.
"""

from .review_controller import ReviewController

__all__ = ["ReviewController"]
