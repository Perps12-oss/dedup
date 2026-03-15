"""
ReviewVM — state for the Review page.

Owns:
  - Projection snapshots from the hub (groups, deletion readiness)
  - User interaction state (keep selections, current group, view mode)
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..projections.review_projection import ReviewGroupProjection
from ..projections.deletion_projection import (
    DeletionReadinessProjection, EMPTY_DELETION, build_deletion_from_review_vm,
)
from ..projections.session_projection import SessionProjection, EMPTY_SESSION


@dataclass
class ReviewVM:
    """
    View-model for the Review page.
    Groups come from build_review_groups_from_result() and are pushed in.
    keep_selections is owned by this VM (user choice, not engine truth).
    """
    # --- Projection snapshots ---
    session:    SessionProjection                = field(default_factory=lambda: EMPTY_SESSION)
    groups:     List[ReviewGroupProjection]      = field(default_factory=list)
    deletion:   DeletionReadinessProjection      = field(default_factory=lambda: EMPTY_DELETION)

    # --- User interaction state ---
    keep_selections:    Dict[str, str]  = field(default_factory=dict)  # group_id -> keep path
    current_group_idx:  int             = 0
    view_mode:          str             = "table"   # "table" | "gallery" | "compare"
    filter_text:        str             = ""
    show_reviewed:      bool            = True
    deletion_mode:      str             = "trash"   # "trash" | "permanent"

    # Counters computed lazily from groups + keep_selections
    @property
    def total_groups(self) -> int:
        return len(self.groups)

    @property
    def reclaimable_bytes(self) -> int:
        return sum(g.reclaimable_bytes for g in self.groups)

    @property
    def delete_count(self) -> int:
        """Files selected for deletion (all non-keepers in groups with a keep selection)."""
        total = 0
        for g in self.groups:
            if g.group_id in self.keep_selections:
                total += g.file_count - 1
        return total

    @property
    def keep_count(self) -> int:
        return len(self.keep_selections)

    @property
    def risk_flags(self) -> int:
        return sum(1 for g in self.groups if g.has_risk and g.group_id in self.keep_selections)

    @property
    def current_group(self) -> Optional[ReviewGroupProjection]:
        if 0 <= self.current_group_idx < len(self.groups):
            return self.groups[self.current_group_idx]
        return None

    @property
    def filtered_groups(self) -> List[ReviewGroupProjection]:
        if not self.filter_text:
            return self.groups
        q = self.filter_text.lower()
        return [g for g in self.groups if q in g.metadata_summary.lower()
                or q in g.group_id.lower()]

    def set_keep(self, group_id: str, path: str) -> None:
        self.keep_selections[group_id] = path
        self._refresh_deletion()

    def clear_keep(self, group_id: str) -> None:
        self.keep_selections.pop(group_id, None)
        self._refresh_deletion()

    def _refresh_deletion(self) -> None:
        self.deletion = build_deletion_from_review_vm(self)

    def load_result(self, result) -> None:
        """Replace groups from a new ScanResult and reset selections."""
        from ..projections.review_projection import build_review_groups_from_result
        self.groups          = build_review_groups_from_result(result)
        self.keep_selections = {}
        self.current_group_idx = 0
        self.deletion        = EMPTY_DELETION

    def review_completion_pct(self) -> float:
        if not self.groups:
            return 0.0
        reviewed = sum(1 for g in self.groups if g.group_id in self.keep_selections)
        return 100.0 * reviewed / len(self.groups)


# ---------------------------------------------------------------------------
# Backward-compatibility shim for modules that import GroupEntry from here.
# GroupEntry is now ReviewGroupProjection.
# ---------------------------------------------------------------------------
GroupEntry = ReviewGroupProjection
