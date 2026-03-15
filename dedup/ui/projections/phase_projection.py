"""
PhaseProjection — canonical phase state for PhaseTimeline, ScanPage, DiagnosticsPage.

One PhaseProjection per pipeline phase, assembled from CheckpointInfo + progress events.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# Canonical ordered phase sequence
PHASE_ORDER: Tuple[str, ...] = (
    "discovery",
    "size_reduction",
    "partial_hash",
    "full_hash",
    "result_assembly",
)

# Human display labels
PHASE_LABELS: Dict[str, str] = {
    "discovery":      "Discovery",
    "size_reduction": "Size",
    "partial_hash":   "Partial Hash",
    "full_hash":      "Full Hash",
    "result_assembly":"Results",
}

# Timeline key aliases — pipeline emits short names (including engine progress.phase)
PHASE_ALIASES: Dict[str, str] = {
    "scanning":          "discovery",
    "discovering":       "discovery",
    "grouping":          "size_reduction",
    "size":              "size_reduction",
    "size_reduction":    "size_reduction",
    "partial":           "partial_hash",
    "partial_hash":      "partial_hash",
    "hashing_partial":   "partial_hash",
    "full":              "full_hash",
    "full_hash":         "full_hash",
    "hashing_full":      "full_hash",
    "results":           "result_assembly",
    "result_assembly":   "result_assembly",
    "complete":          "result_assembly",
}


def canonical_phase(raw: str) -> str:
    """Normalise a raw phase string to a canonical PHASE_ORDER key."""
    key = raw.lower().replace(" ", "_").replace("-", "_")
    return PHASE_ALIASES.get(key, key)


@dataclass(frozen=True)
class PhaseProjection:
    """
    Immutable per-phase state snapshot.
    Replaced atomically when status changes.
    """
    phase_name: str          # canonical key from PHASE_ORDER
    display_label: str
    status: str              # pending | running | completed | failed | resumed | rebuilt | skipped
    finalized: bool
    integrity_ok: bool
    rows_written: int
    duration_ms: float
    checkpoint_cursor: str
    is_reused: bool          # True when this phase was loaded from durable state
    resume_outcome: str      # safe_resume | rebuild_phase | restart_required | unknown
    failure_reason: str

    # Timeline display state (maps to PhaseTimeline component states)
    @property
    def timeline_state(self) -> str:
        if self.status == "running":
            return "active"
        if self.status == "completed" and self.is_reused:
            return "resumed"
        if self.status == "completed":
            return "completed"
        if self.status == "failed":
            return "failed"
        if self.status == "rebuilt":
            return "rebuilt"
        if self.status == "skipped":
            return "skipped"
        return "pending"


def _empty_phase(phase_name: str) -> PhaseProjection:
    return PhaseProjection(
        phase_name=phase_name,
        display_label=PHASE_LABELS.get(phase_name, phase_name.replace("_", " ").title()),
        status="pending",
        finalized=False,
        integrity_ok=True,
        rows_written=0,
        duration_ms=0.0,
        checkpoint_cursor="",
        is_reused=False,
        resume_outcome="unknown",
        failure_reason="",
    )


def initial_phase_map() -> Dict[str, PhaseProjection]:
    """Return a fresh dict of all phases in pending state."""
    return {p: _empty_phase(p) for p in PHASE_ORDER}


def build_phase_from_checkpoint(
    phase_name: str,
    status: str,
    finalized: bool = False,
    rows_written: int = 0,
    duration_ms: float = 0.0,
    checkpoint_cursor: str = "",
    is_reused: bool = False,
    resume_outcome: str = "unknown",
    failure_reason: str = "",
) -> PhaseProjection:
    canon = canonical_phase(phase_name)
    return PhaseProjection(
        phase_name=canon,
        display_label=PHASE_LABELS.get(canon, canon.replace("_", " ").title()),
        status=status,
        finalized=finalized,
        integrity_ok=(failure_reason == ""),
        rows_written=rows_written,
        duration_ms=duration_ms,
        checkpoint_cursor=checkpoint_cursor,
        is_reused=is_reused,
        resume_outcome=resume_outcome,
        failure_reason=failure_reason,
    )
