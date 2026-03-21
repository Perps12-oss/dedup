"""Cross-session incremental discovery helpers."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Optional

from ..infrastructure.resume_support import is_phase_complete
from .models import FileMetadata, ScanConfig, ScanPhase


def normalize_discovery_path(path: str) -> str:
    """Normalize persisted discovery paths for stable cross-session lookups."""
    return os.path.normcase(os.path.normpath(path))


def root_fingerprint(config: ScanConfig) -> str:
    roots = sorted(normalize_discovery_path(str(root)) for root in config.roots)
    return hashlib.sha256("|".join(roots).encode("utf-8")).hexdigest()


def discovery_config_payload(config: ScanConfig) -> Dict[str, object]:
    """Return the subset of config that affects discovery correctness."""
    allowed_extensions = None
    if config.allowed_extensions:
        allowed_extensions = sorted(str(ext).lower().lstrip(".") for ext in config.allowed_extensions)

    return {
        "roots": sorted(normalize_discovery_path(str(root)) for root in config.roots),
        "min_size_bytes": config.min_size_bytes,
        "max_size_bytes": config.max_size_bytes,
        "include_hidden": config.include_hidden,
        "follow_symlinks": config.follow_symlinks,
        "scan_subfolders": config.scan_subfolders,
        "allowed_extensions": allowed_extensions,
        "exclude_dirs": sorted(config.exclude_dirs),
        "resolve_paths": config.resolve_paths,
    }


def discovery_config_hash(config: ScanConfig) -> str:
    payload = json.dumps(discovery_config_payload(config), sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@dataclass(slots=True)
class PriorSessionCompatibilityReport:
    """Why a prior session was or was not eligible for incremental discovery."""

    prior_session_id: Optional[str] = None
    candidate_session_id: Optional[str] = None
    compatible: bool = False
    root_fingerprint_match: bool = False
    discovery_config_match: bool = False
    schema_match: bool = False
    discovery_phase_complete: bool = False
    reason: str = "no_prior_session"

    def to_dict(self) -> Dict[str, object]:
        return {
            "prior_session_id": self.prior_session_id,
            "candidate_session_id": self.candidate_session_id,
            "compatible": self.compatible,
            "root_fingerprint_match": self.root_fingerprint_match,
            "discovery_config_match": self.discovery_config_match,
            "schema_match": self.schema_match,
            "discovery_phase_complete": self.discovery_phase_complete,
            "reason": self.reason,
        }


@dataclass(slots=True)
class DiscoveryMergeReport:
    """Classification of current discovery output against a prior session."""

    prior_session_id: Optional[str]
    total_current: int
    unchanged: int = 0
    changed: int = 0
    new: int = 0
    deleted: int = 0
    unchanged_paths: list[str] = field(default_factory=list)
    changed_paths: list[str] = field(default_factory=list)
    new_paths: list[str] = field(default_factory=list)
    deleted_paths: list[str] = field(default_factory=list)

    @property
    def reused(self) -> int:
        return self.unchanged

    def to_dict(self) -> Dict[str, object]:
        return {
            "prior_session_id": self.prior_session_id,
            "total_current": self.total_current,
            "unchanged": self.unchanged,
            "changed": self.changed,
            "new": self.new,
            "deleted": self.deleted,
            "reused": self.reused,
        }


def find_compatible_prior_session(
    persistence: Any,
    config: ScanConfig,
    *,
    exclude_session_id: Optional[str] = None,
) -> tuple[Optional[str], PriorSessionCompatibilityReport]:
    """Find the most recent compatible prior discovery session for a new scan."""
    report = PriorSessionCompatibilityReport()
    if not persistence or not getattr(config, "incremental_discovery", True):
        report.reason = "incremental_discovery_disabled"
        return None, report

    root_fp = root_fingerprint(config)
    current_disc_hash = discovery_config_hash(config)
    schema_version = getattr(persistence, "schema_version", 0)
    if callable(schema_version):
        schema_version = schema_version()

    candidates = persistence.session_repo.list_by_root_fingerprint(root_fp)
    if not candidates:
        report.reason = "no_prior_session"
        return None, report

    for session in candidates:
        session_id = str(session.get("session_id") or "")
        if not session_id or session_id == exclude_session_id:
            continue

        report.candidate_session_id = session_id
        report.root_fingerprint_match = (session.get("root_fingerprint") or "") == root_fp
        if not report.root_fingerprint_match:
            report.reason = "root_fingerprint_mismatch"
            continue

        report.discovery_config_match = (session.get("discovery_config_hash") or "") == current_disc_hash
        if not report.discovery_config_match:
            report.reason = "discovery_config_hash_mismatch"
            continue

        checkpoint = persistence.checkpoint_repo.get(session_id, ScanPhase.DISCOVERY)
        report.discovery_phase_complete = bool(
            checkpoint and is_phase_complete(persistence.checkpoint_repo, session_id, ScanPhase.DISCOVERY)
        )
        if not report.discovery_phase_complete:
            report.reason = "discovery_phase_incomplete"
            continue

        report.schema_match = bool(
            checkpoint and checkpoint.schema_version is not None and checkpoint.schema_version == schema_version
        )
        if not report.schema_match:
            report.reason = "schema_version_mismatch"
            continue

        report.prior_session_id = session_id
        report.compatible = True
        report.reason = "compatible"
        return session_id, report

    return None, report


def build_discovery_merge_report(
    current_files: Iterable[FileMetadata],
    prior_files: Iterable[FileMetadata],
    *,
    prior_session_id: Optional[str],
) -> DiscoveryMergeReport:
    """Compare current discovery results against a prior session inventory."""
    current_list = list(current_files)
    prior_map = {normalize_discovery_path(meta.path): meta for meta in prior_files}
    current_paths: set[str] = set()
    report = DiscoveryMergeReport(prior_session_id=prior_session_id, total_current=len(current_list))

    for current in current_list:
        norm_path = normalize_discovery_path(current.path)
        current_paths.add(norm_path)
        prior = prior_map.get(norm_path)
        if prior is None:
            report.new += 1
            report.new_paths.append(current.path)
            continue
        if prior.size == current.size and prior.mtime_ns == current.mtime_ns:
            report.unchanged += 1
            report.unchanged_paths.append(current.path)
            continue
        report.changed += 1
        report.changed_paths.append(current.path)

    for norm_path, prior in prior_map.items():
        if norm_path not in current_paths:
            report.deleted += 1
            report.deleted_paths.append(prior.path)

    return report
