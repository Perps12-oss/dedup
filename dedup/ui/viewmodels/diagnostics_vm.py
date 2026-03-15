"""
DiagnosticsVM — state for the Diagnostics page.

Owns:
  - CompatibilityProjection (from ProjectionHub, same truth model as Scan page)
  - PhaseProjection dict (same truth model)
  - Session summary fields (config_hash, schema_version, root_fingerprint from load())
  - Active tab state
"""
from __future__ import annotations
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

from ..projections.session_projection import SessionProjection, EMPTY_SESSION
from ..projections.phase_projection import PhaseProjection, initial_phase_map, PHASE_ORDER
from ..projections.compatibility_projection import (
    CompatibilityProjection, EMPTY_COMPAT,
    PhaseCompatibilityProjection,
)


@dataclass
class ArtifactRow:
    table_name: str
    row_count: int
    status: str = "ok"   # ok | empty | missing
    description: str = ""


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

    # --- Loaded session overview (from load(coordinator, session_id)) ---
    _loaded_session_id: Optional[str] = None
    _loaded_overview: Dict[str, Any] = field(default_factory=dict)

    def load(self, coordinator, session_id: str) -> None:
        """Load diagnostics for a session. Uses coordinator history + persistence."""
        self._loaded_session_id = session_id or ""
        self._loaded_overview = {}
        if session_id:
            try:
                history = coordinator.get_history(limit=200) or []
                for h in history:
                    if h.get("scan_id") == session_id:
                        self._loaded_overview = {
                            "config_hash": str(h.get("config_hash", "")),
                            "schema_version": h.get("schema_version"),
                            "root_fingerprint": str(h.get("root_fingerprint", "")),
                            "deletion_verification_summary": dict(h.get("deletion_verification_summary") or {}),
                            "benchmark_summary": dict(h.get("benchmark_summary") or {}),
                        }
                        break
            except Exception:
                pass
        # Use loaded session_id for artifact counts
        self.session = SessionProjection(
            session_id=session_id or "",
            status="",
            created_at="",
            updated_at="",
            current_phase="",
            phase_status="",
            resume_policy="",
            resume_reason="",
            is_resumable=False,
            engine_health="",
            warnings_count=0,
            config_hash=self._loaded_overview.get("config_hash", ""),
            schema_version=self._loaded_overview.get("schema_version") or 0,
            scan_root="",
        )
        persistence = getattr(coordinator, "persistence", None)
        self.refresh_artifacts(persistence)
        self.refresh_integrity()

    @property
    def config_hash(self) -> str:
        return self._loaded_overview.get("config_hash", "") or getattr(
            self.session, "config_hash", "")

    @property
    def schema_version(self) -> Any:
        return self._loaded_overview.get("schema_version") or getattr(
            self.session, "schema_version", None)

    @property
    def root_fingerprint(self) -> str:
        return self._loaded_overview.get("root_fingerprint", "") or getattr(
            self.session, "scan_root", "")

    @property
    def deletion_verification_summary(self) -> Dict[str, int]:
        return dict(self._loaded_overview.get("deletion_verification_summary") or {})

    @property
    def benchmark_summary(self) -> Dict[str, Any]:
        return dict(self._loaded_overview.get("benchmark_summary") or {})

    @property
    def phases_table(self) -> List[Any]:
        """Phase rows for the Phases tab: phase, integrity, finalized, rows, duration_s, checkpoint_ts, resume_action."""
        out = []
        for pname in PHASE_ORDER:
            p = self.phases.get(pname)
            if not p:
                continue
            out.append(SimpleNamespace(
                phase=pname,
                integrity="ok" if p.integrity_ok else "warn",
                finalized=p.finalized,
                rows=p.rows_written,
                duration_s=p.duration_ms / 1000.0,
                checkpoint_ts=p.checkpoint_cursor or "",
                resume_action=p.resume_outcome or "unknown",
            ))
        return out

    @property
    def compatibility(self) -> List[Any]:
        """Compat rows for the Compatibility tab: phase, schema_match, config_match, phase_version_match, artifact_complete, resume_action."""
        out = []
        for pc in self.compat.phases:
            out.append(SimpleNamespace(
                phase=pc.phase_name,
                schema_match=pc.schema_match,
                config_match=pc.config_hash_match,
                phase_version_match=pc.phase_version_match,
                artifact_complete=pc.artifact_integrity_ok,
                resume_action=pc.resume_action,
            ))
        return out

    @property
    def events(self) -> List[Any]:
        """Event rows for the Events tab: ts, event_type, phase, severity, detail."""
        out = []
        for line in (self.events_log or [])[:200]:
            out.append(SimpleNamespace(
                ts=line[:12] if len(line) > 12 else line,
                event_type="log",
                phase="",
                severity="info",
                detail=line[:80] if len(line) > 80 else line,
            ))
        return out

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
            "deletion_verifications",
        ]
        rows: List[ArtifactRow] = []
        for tbl in tables:
            try:
                count = _safe_count(persistence, sid, tbl)
                rows.append(ArtifactRow(
                    table_name=tbl,
                    row_count=count,
                    status="ok" if count > 0 else "empty",
                    description="ok" if count > 0 else "empty",
                ))
            except Exception:
                rows.append(ArtifactRow(table_name=tbl, row_count=0, status="missing", description="missing"))
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
