"""
SessionProjection — canonical session snapshot consumed by all pages.

This is the single source of truth for session lifecycle state.
Every page that shows session identity, health, or resumability reads from here.

Consumers: store-fed pages (e.g. CTK Mission / Scan / History / Diagnostics) and any widget bound to ``UIStateStore.scan.session``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SessionProjection:
    """
    Immutable snapshot of the active (or most-recent) session state.
    Replaced atomically when any field changes — never mutated in place.
    """

    session_id: str
    status: str  # idle | pending | running | completed | cancelled | failed
    created_at: str
    updated_at: str
    current_phase: str  # discovery | size_reduction | partial_hash | full_hash | result_assembly | idle
    phase_status: str  # pending | running | completed | failed
    resume_policy: str  # safe | rebuild_phase | restart_required | none
    resume_reason: str  # human-readable reason string
    is_resumable: bool
    engine_health: str  # Healthy | Warning | Degraded
    warnings_count: int
    config_hash: str
    schema_version: int
    scan_root: str  # display-friendly root summary

    # Convenience properties
    @property
    def is_active(self) -> bool:
        return self.status == "running"

    @property
    def is_terminal(self) -> bool:
        return self.status in ("completed", "cancelled", "failed")

    @property
    def resume_outcome_label(self) -> str:
        labels = {
            "safe": "Safe Resume",
            "rebuild_phase": "Rebuild Phase",
            "restart_required": "Restart Required",
            "none": "",
        }
        return labels.get(self.resume_policy, self.resume_policy)

    @property
    def health_variant(self) -> str:
        """Maps engine_health to a StatusRibbon / MetricCard variant string."""
        return {
            "Healthy": "positive",
            "Warning": "warning",
            "Degraded": "danger",
        }.get(self.engine_health, "neutral")


# Sentinel used before any session starts.
EMPTY_SESSION = SessionProjection(
    session_id="",
    status="idle",
    created_at="",
    updated_at="",
    current_phase="",
    phase_status="",
    resume_policy="none",
    resume_reason="",
    is_resumable=False,
    engine_health="Healthy",
    warnings_count=0,
    config_hash="",
    schema_version=0,
    scan_root="",
)


def build_session_from_event(
    session_id: str,
    status: str,
    phase: str = "",
    phase_status: str = "",
    resume_policy: str = "none",
    resume_reason: str = "",
    engine_health: str = "Healthy",
    warnings_count: int = 0,
    config_hash: str = "",
    schema_version: int = 0,
    scan_root: str = "",
    created_at: str = "",
    updated_at: str = "",
) -> SessionProjection:
    """
    Build a SessionProjection from raw event/coordinator data.
    All optional fields have safe defaults so callers only supply what they know.
    """
    import time

    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    return SessionProjection(
        session_id=session_id,
        status=status,
        created_at=created_at or ts,
        updated_at=updated_at or ts,
        current_phase=phase,
        phase_status=phase_status,
        resume_policy=resume_policy,
        resume_reason=resume_reason,
        is_resumable=(status not in ("running", "idle")),
        engine_health=engine_health,
        warnings_count=warnings_count,
        config_hash=config_hash,
        schema_version=schema_version,
        scan_root=scan_root,
    )
