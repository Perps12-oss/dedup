"""
Authoritative durable resume: ResumeResolver produces a single ResumeDecision.

Before any scan run we inspect session, checkpoints, and artifact completeness;
we then choose exactly one of: safe_resume, rebuild_current_phase, restart_required.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Optional

from .models import (
    PhaseCompatibilityReport,
    ResumeDecision,
    ResumeOutcome,
    ResumeReason,
    ScanConfig,
    ScanPhase,
)
from .discovery_compat import root_fingerprint
from ..infrastructure.resume_support import (
    PHASE_ORDER,
    get_phase_artifact_stats,
    is_phase_complete,
    validate_artifact_integrity,
)


# Phase implementation version; bump when phase semantics change.
PHASE_VERSION = "v1"


def _config_hash(config: ScanConfig) -> str:
    payload = json.dumps(config.to_dict(), sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _root_fingerprint(config: ScanConfig) -> str:
    return root_fingerprint(config)


def _hash_strategy_fingerprint(config: ScanConfig) -> str:
    return hashlib.sha256(
        f"{config.hash_algorithm}:{config.partial_hash_bytes}".encode("utf-8")
    ).hexdigest()


class ResumeResolver:
    """
    Central decision point: inspect session + checkpoints + repositories,
    choose resume outcome and first runnable phase.
    """

    def __init__(self, persistence: Any):
        self.persistence = persistence

    def resolve(
        self,
        session_id: str,
        config: ScanConfig,
        is_new_scan: bool = False,
    ) -> ResumeDecision:
        """
        Produce the single authoritative resume decision.
        """
        if is_new_scan or not self.persistence:
            return ResumeDecision(
                outcome=ResumeOutcome.RESTART_REQUIRED,
                first_runnable_phase=ScanPhase.DISCOVERY,
                reason=ResumeReason.NEW_SCAN.value,
                compatibility_reports=[],
            )

        session = self.persistence.session_repo.get(session_id)
        if not session:
            return ResumeDecision(
                outcome=ResumeOutcome.RESTART_REQUIRED,
                first_runnable_phase=ScanPhase.DISCOVERY,
                reason=ResumeReason.NO_SESSION.value,
                compatibility_reports=[],
            )

        current_config_hash = _config_hash(config)
        current_root = _root_fingerprint(config)
        current_hash_strategy = _hash_strategy_fingerprint(config)
        session_config_hash = session.get("config_hash") or ""
        session_root = session.get("root_fingerprint") or ""

        if session.get("status") not in ("pending", "running", "cancelled", "failed", "completed"):
            return ResumeDecision(
                outcome=ResumeOutcome.RESTART_REQUIRED,
                first_runnable_phase=ScanPhase.DISCOVERY,
                reason=ResumeReason.SESSION_NOT_RESUMABLE.value,
                compatibility_reports=[],
            )

        if session_config_hash != current_config_hash:
            return ResumeDecision(
                outcome=ResumeOutcome.RESTART_REQUIRED,
                first_runnable_phase=ScanPhase.DISCOVERY,
                reason=ResumeReason.CONFIG_HASH_MISMATCH.value,
                compatibility_reports=[],
                cursor_or_context={"session_config_hash": session_config_hash, "current_config_hash": current_config_hash},
            )

        if session_root != current_root:
            return ResumeDecision(
                outcome=ResumeOutcome.RESTART_REQUIRED,
                first_runnable_phase=ScanPhase.DISCOVERY,
                reason=ResumeReason.ROOT_SET_CHANGED.value,
                compatibility_reports=[],
            )

        schema_version = getattr(self.persistence, "schema_version", 4)
        if callable(schema_version):
            schema_version = schema_version()
        reports: list[PhaseCompatibilityReport] = []
        first_runnable: Optional[ScanPhase] = None
        outcome = ResumeOutcome.SAFE_RESUME
        reason = ResumeReason.COMPATIBLE.value

        for phase in PHASE_ORDER:
            cp = self.persistence.checkpoint_repo.get(session_id, phase)
            stats = get_phase_artifact_stats(
                session_id,
                phase,
                self.persistence.inventory_repo,
                self.persistence.size_candidate_repo,
                self.persistence.partial_hash_repo,
                self.persistence.partial_candidate_repo,
                self.persistence.full_hash_repo,
                self.persistence.duplicate_group_repo,
            )
            report = PhaseCompatibilityReport(phase=phase, compatible=True, reasons=[], artifact_stats=stats)
            reasons: list[str] = []

            if cp is None:
                if first_runnable is None:
                    first_runnable = phase
                reports.append(report)
                continue

            if cp.schema_version is not None and cp.schema_version != schema_version:
                report.compatible = False
                reasons.append(ResumeReason.SCHEMA_VERSION_MISMATCH.value)
                if first_runnable is None:
                    first_runnable = phase
                    outcome = ResumeOutcome.REBUILD_CURRENT_PHASE
                    reason = ResumeReason.SCHEMA_VERSION_MISMATCH.value
            if cp.config_hash and cp.config_hash != current_config_hash:
                report.compatible = False
                reasons.append(ResumeReason.CONFIG_HASH_MISMATCH.value)
                if first_runnable is None:
                    first_runnable = phase
                    outcome = ResumeOutcome.REBUILD_CURRENT_PHASE
                    reason = ResumeReason.CONFIG_HASH_MISMATCH.value
            if cp.status.value != "completed" or not cp.is_finalized:
                if cp.status.value == "running":
                    valid, msg = validate_artifact_integrity(
                        session_id,
                        phase,
                        self.persistence.checkpoint_repo,
                        self.persistence.inventory_repo,
                        self.persistence.size_candidate_repo,
                        self.persistence.partial_candidate_repo,
                        self.persistence.duplicate_group_repo,
                    )
                    if not valid:
                        report.compatible = False
                        reasons.append(msg)
                        if first_runnable is None:
                            first_runnable = phase
                            outcome = ResumeOutcome.REBUILD_CURRENT_PHASE
                            reason = msg
                else:
                    report.compatible = False
                    reasons.append(ResumeReason.PHASE_NOT_FINALIZED.value)
                    if first_runnable is None:
                        first_runnable = phase
            report.reasons = reasons
            reports.append(report)

            if report.compatible and cp.status.value == "completed" and cp.is_finalized:
                continue
            if first_runnable is None:
                first_runnable = phase

        if first_runnable is None:
            first_runnable = ScanPhase.RESULT_ASSEMBLY

        return ResumeDecision(
            outcome=outcome,
            first_runnable_phase=first_runnable,
            reason=reason,
            compatibility_reports=reports,
        )
