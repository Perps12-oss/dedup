"""
CompatibilityProjection — per-phase resume compatibility state.

Crucial for ScanPage status ribbon, History detail, and Diagnostics compatibility tab.
These must not be inferred by the UI — they come directly from ResumeDecision.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional

from .phase_projection import PHASE_ORDER


@dataclass(frozen=True)
class PhaseCompatibilityProjection:
    """Per-phase compatibility slot."""
    phase_name: str
    schema_match: bool
    config_hash_match: bool
    phase_version_match: bool
    artifact_integrity_ok: bool
    finalization_ok: bool
    resume_action: str          # safe_resume | rebuild_phase | restart_required | unknown

    @property
    def all_ok(self) -> bool:
        return (self.schema_match and self.config_hash_match
                and self.phase_version_match and self.artifact_integrity_ok
                and self.finalization_ok)

    @property
    def ribbon_variant(self) -> str:
        return {
            "safe_resume":      "safe_resume",
            "rebuild_phase":    "rebuild_phase",
            "restart_required": "restart_required",
        }.get(self.resume_action, "idle")


@dataclass(frozen=True)
class CompatibilityProjection:
    """
    Full-session compatibility snapshot.
    Contains one PhaseCompatibilityProjection per pipeline phase.
    """
    phases: Tuple[PhaseCompatibilityProjection, ...]
    overall_resume_outcome: str   # safe_resume | rebuild_current_phase | restart_required | unknown
    overall_resume_reason: str
    session_compatible: bool

    @property
    def ribbon_variant(self) -> str:
        if self.overall_resume_outcome == "safe_resume":
            return "safe_resume"
        if self.overall_resume_outcome in ("rebuild_current_phase", "rebuild_phase"):
            return "rebuild_phase"
        if self.overall_resume_outcome == "restart_required":
            return "restart_required"
        return "idle"

    def phase(self, name: str) -> Optional[PhaseCompatibilityProjection]:
        for p in self.phases:
            if p.phase_name == name:
                return p
        return None


def _unknown_phase_compat(phase_name: str) -> PhaseCompatibilityProjection:
    return PhaseCompatibilityProjection(
        phase_name=phase_name,
        schema_match=False,
        config_hash_match=False,
        phase_version_match=False,
        artifact_integrity_ok=False,
        finalization_ok=False,
        resume_action="unknown",
    )


EMPTY_COMPAT = CompatibilityProjection(
    phases=tuple(_unknown_phase_compat(p) for p in PHASE_ORDER),
    overall_resume_outcome="unknown",
    overall_resume_reason="",
    session_compatible=False,
)


def build_compat_from_resume_decision(decision) -> CompatibilityProjection:
    """
    Build from a ResumeDecision engine object.
    `decision` is `dedup.engine.models.ResumeDecision`.
    """
    phase_compats = []
    reports = getattr(decision, "compatibility_reports", []) or []
    report_map: Dict[str, object] = {}
    for r in reports:
        pname = getattr(r.phase, "value", str(r.phase))
        report_map[pname] = r

    for pname in PHASE_ORDER:
        r = report_map.get(pname)
        if r is None:
            phase_compats.append(_unknown_phase_compat(pname))
            continue
        compatible = getattr(r, "compatible", False)
        reasons = getattr(r, "reasons", [])
        schema_ok   = not any("schema" in x.lower()  for x in reasons)
        config_ok   = not any("config" in x.lower()  for x in reasons)
        pver_ok     = not any("version" in x.lower() for x in reasons)
        artifact_ok = not any("artifact" in x.lower() or "incomplete" in x.lower() for x in reasons)
        final_ok    = not any("finali" in x.lower()  for x in reasons)
        action = "safe_resume" if compatible else "rebuild_phase"
        phase_compats.append(PhaseCompatibilityProjection(
            phase_name=pname,
            schema_match=schema_ok,
            config_hash_match=config_ok,
            phase_version_match=pver_ok,
            artifact_integrity_ok=artifact_ok,
            finalization_ok=final_ok,
            resume_action=action,
        ))

    outcome_val = getattr(decision.outcome, "value", str(decision.outcome))
    return CompatibilityProjection(
        phases=tuple(phase_compats),
        overall_resume_outcome=outcome_val,
        overall_resume_reason=getattr(decision, "reason", ""),
        session_compatible=(outcome_val == "safe_resume"),
    )


def build_compat_from_event_payload(payload: dict) -> CompatibilityProjection:
    """Build from a raw RESUME_VALIDATED / RESUME_REJECTED event payload dict."""
    outcome  = payload.get("outcome", "unknown")
    reason   = payload.get("reason", "")
    reports  = payload.get("compatibility_reports", [])

    phase_compats = []
    report_map = {r.get("phase", ""): r for r in reports}

    for pname in PHASE_ORDER:
        r = report_map.get(pname, {})
        compatible = r.get("compatible", True)
        reasons    = r.get("reasons", [])
        schema_ok  = not any("schema" in x.lower()  for x in reasons)
        config_ok  = not any("config" in x.lower()  for x in reasons)
        pver_ok    = not any("version" in x.lower() for x in reasons)
        art_ok     = not any("artifact" in x.lower() for x in reasons)
        final_ok   = not any("finali" in x.lower()  for x in reasons)
        action     = "safe_resume" if compatible else "rebuild_phase"
        if outcome == "restart_required":
            action = "restart_required"
        phase_compats.append(PhaseCompatibilityProjection(
            phase_name=pname,
            schema_match=schema_ok,
            config_hash_match=config_ok,
            phase_version_match=pver_ok,
            artifact_integrity_ok=art_ok,
            finalization_ok=final_ok,
            resume_action=action,
        ))

    return CompatibilityProjection(
        phases=tuple(phase_compats),
        overall_resume_outcome=outcome,
        overall_resume_reason=reason,
        session_compatible=(outcome == "safe_resume"),
    )
