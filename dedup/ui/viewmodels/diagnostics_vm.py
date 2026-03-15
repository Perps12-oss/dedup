"""
DiagnosticsVM — state for the Diagnostics page.

Owns:
  - CompatibilityProjection (from ProjectionHub, same truth model as Scan page)
  - PhaseProjection dict (same truth model)
  - Session summary fields
  - Active tab state
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..projections.session_projection import SessionProjection, EMPTY_SESSION
from ..projections.phase_projection import PhaseProjection, initial_phase_map
from ..projections.compatibility_projection import CompatibilityProjection, EMPTY_COMPAT


@dataclass
class ArtifactRow:
    table_name: str
    row_count: int
    status: str = "ok"   # ok | empty | missing


@dataclass
class EventRow:
    timestamp: str
    phase: str
    event_type: str
    detail: str
    severity: str = "info"   # info | warning | error


@dataclass
class IntegrityRow:
    check_name: str
    result: str    # ok | warning | error
    detail: str


@dataclass
class DiagnosticsVM:
    """
    View-model for the Diagnostics page.
    Reads from the same projection snapshots as ScanPage and HistoryPage.
    The diagnostics page is never a parallel universe.
    """
    # --- Projections (pushed from ProjectionHub, same as ScanPage) ---
    session:  SessionProjection          = field(default_factory=lambda: EMPTY_SESSION)
    phases:   Dict[str, PhaseProjection] = field(default_factory=initial_phase_map)
    compat:   CompatibilityProjection    = field(default_factory=lambda: EMPTY_COMPAT)

    # --- Events log (pushed from ProjectionHub "events_log" channel) ---
    events_log: List[str]                = field(default_factory=list)

    # --- On-demand artifact / integrity data (fetched from persistence) ---
    artifacts:  List[ArtifactRow]        = field(default_factory=list)
    integrity:  List[IntegrityRow]       = field(default_factory=list)

    # --- UI interaction state ---
    active_tab:  str = "phases"   # phases | artifacts | compatibility | events | integrity

    def refresh_artifacts(self, persistence) -> None:
        """
        Pull row counts from the persistence layer for the Artifacts tab.
        Called on demand when the user opens the Artifacts tab.
        """
        sid = self.session.session_id
        if not sid or not persistence:
            self.artifacts = []
            return

        tables = [
            "inventory_files",
            "size_candidates",
            "partial_hashes",
            "partial_candidates",
            "full_hashes",
            "duplicate_groups",
            "deletion_plans",
            "deletion_audit",
        ]
        rows: List[ArtifactRow] = []
        for tbl in tables:
            try:
                count = _safe_count(persistence, sid, tbl)
                rows.append(ArtifactRow(
                    table_name=tbl,
                    row_count=count,
                    status="ok" if count > 0 else "empty",
                ))
            except Exception:
                rows.append(ArtifactRow(table_name=tbl, row_count=0, status="missing"))
        self.artifacts = rows

    def refresh_integrity(self) -> None:
        """Build integrity rows from current phase + compat projections."""
        rows: List[IntegrityRow] = []
        for p in self.phases.values():
            if p.status in ("completed", "running", "rebuilt", "resumed"):
                rows.append(IntegrityRow(
                    check_name=f"{p.display_label} finalization",
                    result="ok" if p.finalized else "warning",
                    detail="Finalized" if p.finalized else "Not yet finalized",
                ))
                rows.append(IntegrityRow(
                    check_name=f"{p.display_label} integrity",
                    result="ok" if p.integrity_ok else "error",
                    detail=p.failure_reason if not p.integrity_ok else "✓",
                ))
        # Compat checks
        for pc in self.compat.phases:
            rows.append(IntegrityRow(
                check_name=f"{pc.phase_name} schema",
                result="ok" if pc.schema_match else "warning",
                detail="Match" if pc.schema_match else "Mismatch",
            ))
        self.integrity = rows

    @property
    def phase_rows(self):
        """Ordered list of PhaseProjection for the Phases tab."""
        from ..projections.phase_projection import PHASE_ORDER
        return [self.phases.get(p) for p in PHASE_ORDER if p in self.phases]

    @property
    def compat_rows(self):
        """List of PhaseCompatibilityProjection for the Compatibility tab."""
        return list(self.compat.phases) if self.compat else []


def _safe_count(persistence, session_id: str, table: str) -> int:
    """Best-effort row count from persistence. Returns 0 on any error."""
    conn = getattr(persistence, "_conn", None) or getattr(persistence, "conn", None)
    if conn is None:
        db = getattr(persistence, "_db", None) or getattr(persistence, "db", None)
        if db:
            conn = db
    if conn is None:
        return 0
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT COUNT(*) FROM {table} WHERE session_id = ?", (session_id,))
        row = cur.fetchone()
        return row[0] if row else 0
    except Exception:
        return 0
