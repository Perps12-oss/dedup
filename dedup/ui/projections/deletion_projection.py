"""
DeletionReadinessProjection — explicit contract powering SafetyPanel and ReviewPage actions.

This projection is the single source of truth for:
  - deletion mode (trash vs permanent)
  - revalidation and audit state
  - selected counts and reclaimable space
  - risk flags
  - dry-run result
  - execution readiness

Consumers: SafetyPanel, ReviewPage actions, History audit summary.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class DeletionReadinessProjection:
    """Immutable snapshot of deletion plan readiness."""
    mode: str                           # "trash" | "permanent"
    pre_delete_revalidation_enabled: bool
    audit_logging_enabled: bool
    selected_delete_count: int
    selected_keep_count: int
    reclaimable_now: int                # bytes that would be freed right now
    risk_flags: int                     # count of risky selections
    dry_run_status: str                 # "" | "passed" | "failed" | "pending"
    dry_run_detail: str                 # human-readable dry-run summary
    execution_ready: bool               # True when plan is non-empty + no blocking risk

    @property
    def mode_label(self) -> str:
        return "Trash" if self.mode == "trash" else "Permanent Delete"

    @property
    def revalidation_label(self) -> str:
        return "ON" if self.pre_delete_revalidation_enabled else "OFF"

    @property
    def audit_label(self) -> str:
        return "ACTIVE" if self.audit_logging_enabled else "OFF"

    @property
    def risk_variant(self) -> str:
        if self.risk_flags == 0:
            return "positive"
        if self.risk_flags <= 2:
            return "warning"
        return "danger"


EMPTY_DELETION = DeletionReadinessProjection(
    mode="trash",
    pre_delete_revalidation_enabled=True,
    audit_logging_enabled=True,
    selected_delete_count=0,
    selected_keep_count=0,
    reclaimable_now=0,
    risk_flags=0,
    dry_run_status="",
    dry_run_detail="",
    execution_ready=False,
)


def build_deletion_from_plan(
    deletion_plan,
    mode: str = "trash",
    keep_selections: Optional[dict] = None,
) -> DeletionReadinessProjection:
    """
    Build from a DeletionPlan engine object + current user keep selections.
    """
    groups = getattr(deletion_plan, "groups", []) if deletion_plan else []
    del_count  = 0
    keep_count = 0
    reclaim    = 0
    risk       = 0

    for grp in groups:
        keep_path = (keep_selections or {}).get(
            getattr(grp, "group_id", ""), "")
        for tgt in getattr(grp, "targets", []):
            path = getattr(tgt, "path", "")
            if path == keep_path:
                keep_count += 1
            else:
                del_count += 1
                reclaim += getattr(tgt, "size", 0) or 0

    return DeletionReadinessProjection(
        mode=mode,
        pre_delete_revalidation_enabled=True,
        audit_logging_enabled=True,
        selected_delete_count=del_count,
        selected_keep_count=keep_count,
        reclaimable_now=reclaim,
        risk_flags=risk,
        dry_run_status="",
        dry_run_detail="",
        execution_ready=(del_count > 0),
    )


def build_deletion_from_review_vm(vm) -> DeletionReadinessProjection:
    """
    Build from a ReviewVM that already tracks keep selections.
    Uses vm.delete_count, keep_count, reclaimable_bytes.
    """
    return DeletionReadinessProjection(
        mode=getattr(vm, "deletion_mode", "trash"),
        pre_delete_revalidation_enabled=True,
        audit_logging_enabled=True,
        selected_delete_count=getattr(vm, "delete_count", 0),
        selected_keep_count=getattr(vm, "keep_count", 0),
        reclaimable_now=getattr(vm, "reclaimable_bytes", 0),
        risk_flags=getattr(vm, "risk_flags", 0),
        dry_run_status="",
        dry_run_detail="",
        execution_ready=(getattr(vm, "delete_count", 0) > 0),
    )


def with_dry_run_result(
    base: DeletionReadinessProjection,
    status: str,
    detail: str,
) -> DeletionReadinessProjection:
    """Return a new projection with dry-run result applied."""
    return DeletionReadinessProjection(
        mode=base.mode,
        pre_delete_revalidation_enabled=base.pre_delete_revalidation_enabled,
        audit_logging_enabled=base.audit_logging_enabled,
        selected_delete_count=base.selected_delete_count,
        selected_keep_count=base.selected_keep_count,
        reclaimable_now=base.reclaimable_now,
        risk_flags=base.risk_flags,
        dry_run_status=status,
        dry_run_detail=detail,
        execution_ready=base.execution_ready and status == "passed",
    )
