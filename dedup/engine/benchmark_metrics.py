"""Canonical scan benchmarking metrics and formatting utilities."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass(slots=True)
class ScanBenchmarkReport:
    """Canonical benchmark metrics for one scan execution."""

    scan_id: str
    discovery_reuse_mode: str = "none"  # none | merge | subtree_skip
    prior_session_found: bool = False
    prior_session_compatible: bool = False
    prior_session_rejected_reason: str = "none"

    files_discovered_total: int = 0
    files_discovered_fresh: int = 0
    files_reused_from_prior_inventory: int = 0
    dirs_scanned: int = 0
    dirs_reused: int = 0
    dirs_skipped_via_manifest: int = 0
    stat_calls: int = 0
    resolve_calls: int = 0
    inventory_rows_written: int = 0
    inventory_write_batches: int = 0
    checkpoint_writes: int = 0
    discovery_elapsed_ms: int = 0
    total_elapsed_ms: int = 0

    hash_cache_hits: int = 0
    hash_cache_misses: int = 0
    full_hash_computed: int = 0
    partial_hash_computed: int = 0

    delete_targets_planned: int = 0
    delete_targets_verified_deleted: int = 0
    delete_targets_still_present: int = 0
    delete_targets_changed_after_plan: int = 0
    delete_groups_resolved: int = 0
    delete_groups_partially_resolved: int = 0
    delete_groups_unresolved: int = 0

    phase_metrics: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scan_id": self.scan_id,
            "discovery_reuse_mode": self.discovery_reuse_mode,
            "prior_session_found": self.prior_session_found,
            "prior_session_compatible": self.prior_session_compatible,
            "prior_session_rejected_reason": self.prior_session_rejected_reason,
            "files_discovered_total": self.files_discovered_total,
            "files_discovered_fresh": self.files_discovered_fresh,
            "files_reused_from_prior_inventory": self.files_reused_from_prior_inventory,
            "dirs_scanned": self.dirs_scanned,
            "dirs_reused": self.dirs_reused,
            "dirs_skipped_via_manifest": self.dirs_skipped_via_manifest,
            "stat_calls": self.stat_calls,
            "resolve_calls": self.resolve_calls,
            "inventory_rows_written": self.inventory_rows_written,
            "inventory_write_batches": self.inventory_write_batches,
            "checkpoint_writes": self.checkpoint_writes,
            "discovery_elapsed_ms": self.discovery_elapsed_ms,
            "total_elapsed_ms": self.total_elapsed_ms,
            "hash_cache_hits": self.hash_cache_hits,
            "hash_cache_misses": self.hash_cache_misses,
            "full_hash_computed": self.full_hash_computed,
            "partial_hash_computed": self.partial_hash_computed,
            "delete_targets_planned": self.delete_targets_planned,
            "delete_targets_verified_deleted": self.delete_targets_verified_deleted,
            "delete_targets_still_present": self.delete_targets_still_present,
            "delete_targets_changed_after_plan": self.delete_targets_changed_after_plan,
            "delete_groups_resolved": self.delete_groups_resolved,
            "delete_groups_partially_resolved": self.delete_groups_partially_resolved,
            "delete_groups_unresolved": self.delete_groups_unresolved,
            "phase_metrics": dict(self.phase_metrics),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)


def format_operator_summary(report: Dict[str, Any] | ScanBenchmarkReport) -> str:
    """Human-readable one-block summary for logs and benchmark CLI output."""
    data = report.to_dict() if isinstance(report, ScanBenchmarkReport) else report
    return (
        "discovery mode: {mode}; prior session: found={found}, compatible={compatible}, reason={reason}; "
        "directories scanned={dirs_scanned}, reused={dirs_reused}, skipped={dirs_skipped}; "
        "files fresh={fresh}, reused={reused}, total={total}; "
        "inventory writes: batches={batches}, rows={rows}; checkpoints={checkpoints}; "
        "hash cache: hits={hits}, misses={misses}; "
        "discovery time={disc}ms; total scan time={total_ms}ms"
    ).format(
        mode=data.get("discovery_reuse_mode", "none"),
        found=data.get("prior_session_found", False),
        compatible=data.get("prior_session_compatible", False),
        reason=data.get("prior_session_rejected_reason", "none"),
        dirs_scanned=data.get("dirs_scanned", 0),
        dirs_reused=data.get("dirs_reused", 0),
        dirs_skipped=data.get("dirs_skipped_via_manifest", 0),
        fresh=data.get("files_discovered_fresh", 0),
        reused=data.get("files_reused_from_prior_inventory", 0),
        total=data.get("files_discovered_total", 0),
        batches=data.get("inventory_write_batches", 0),
        rows=data.get("inventory_rows_written", 0),
        checkpoints=data.get("checkpoint_writes", 0),
        hits=data.get("hash_cache_hits", 0),
        misses=data.get("hash_cache_misses", 0),
        disc=data.get("discovery_elapsed_ms", 0),
        total_ms=data.get("total_elapsed_ms", 0),
    )
