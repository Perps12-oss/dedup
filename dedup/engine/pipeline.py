"""
DEDUP Scan Pipeline - Orchestrates the complete duplicate detection workflow.

Pipeline phases:
1. Discovery - Find all files in specified directories
2. Size Grouping - Group by size (eliminates unique sizes)
3. Partial Hashing - Hash first N bytes (fast elimination)
4. Full Hashing - Confirm duplicates with complete hash
5. Result Assembly - Build duplicate groups

All phases support cancellation and progress reporting.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Protocol

from ..infrastructure.resume_support import PHASE_ORDER
from .benchmark_metrics import ScanBenchmarkReport, format_operator_summary
from .deletion import DeletionEngine
from .discovery import DiscoveryOptions, FileDiscovery
from .discovery_compat import (
    build_discovery_merge_report,
    discovery_config_hash,
    find_compatible_prior_session,
    root_fingerprint,
)
from .grouping import (
    FullHashReducer,
    GroupingEngine,
    PartialHashReducer,
    SizeReducer,
)
from .hashing import HashEngine
from .models import (
    CheckpointInfo,
    DeletionPlan,
    DeletionPolicy,
    DeletionResult,
    DuplicateGroup,
    FileMetadata,
    PhaseStatus,
    ScanConfig,
    ScanPhase,
    ScanProgress,
    ScanResult,
)
from .resume import ResumeResolver

_log = logging.getLogger(__name__)


@dataclass
class PhaseChunkResult:
    """Result metadata for a single phase execution step."""

    completed_units: int = 0
    total_units: Optional[int] = None
    next_cursor: Optional[str] = None
    events: List[Dict[str, Any]] = field(default_factory=list)
    artifacts_written: List[str] = field(default_factory=list)
    is_complete: bool = True
    payload: Any = None


@dataclass
class PhaseSummary:
    """Small phase completion summary."""

    phase_name: ScanPhase
    completed_units: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


class PhaseRunner(Protocol):
    """Protocol for persistence-aware pipeline phases."""

    phase_name: ScanPhase

    def can_resume(self, pipeline: "ScanPipeline", checkpoint: Optional[CheckpointInfo]) -> bool: ...
    def run_chunk(
        self,
        pipeline: "ScanPipeline",
        checkpoint: Optional[CheckpointInfo],
        progress_cb: Optional[Callable[[ScanProgress], None]] = None,
    ) -> PhaseChunkResult: ...
    def finalize(self, pipeline: "ScanPipeline", result: PhaseChunkResult) -> PhaseSummary: ...


@dataclass
class DiscoveryPhaseRunner:
    """Discovery phase with optional durable inventory shadow writes."""

    phase_name: ScanPhase = ScanPhase.DISCOVERY

    def can_resume(self, pipeline: "ScanPipeline", checkpoint: Optional[CheckpointInfo]) -> bool:
        return checkpoint is not None and checkpoint.status == PhaseStatus.COMPLETED

    def run_chunk(
        self,
        pipeline: "ScanPipeline",
        checkpoint: Optional[CheckpointInfo],
        progress_cb: Optional[Callable[[ScanProgress], None]] = None,
    ) -> PhaseChunkResult:
        files = pipeline._discover_files(progress_cb)
        return PhaseChunkResult(
            completed_units=len(files),
            total_units=len(files),
            artifacts_written=["inventory_files"] if pipeline.persistence else [],
            payload=files,
        )

    def finalize(self, pipeline: "ScanPipeline", result: PhaseChunkResult) -> PhaseSummary:
        metadata = {"bytes_found": pipeline._bytes_found}
        if pipeline._incremental_prior_report:
            metadata["incremental_prior_report"] = pipeline._incremental_prior_report
        if pipeline._incremental_merge_report:
            metadata["incremental_merge_report"] = pipeline._incremental_merge_report
        return PhaseSummary(
            phase_name=self.phase_name,
            completed_units=result.completed_units,
            metadata=metadata,
        )


PHASE_VERSION = "v1"


@dataclass
class SizeReductionPhaseRunner:
    """Size grouping: read inventory, write size_candidates."""

    phase_name: ScanPhase = ScanPhase.SIZE_REDUCTION

    def can_resume(self, pipeline: "ScanPipeline", checkpoint: Optional[CheckpointInfo]) -> bool:
        return checkpoint is not None and checkpoint.status == PhaseStatus.COMPLETED and checkpoint.is_finalized

    def run_chunk(
        self,
        pipeline: "ScanPipeline",
        checkpoint: Optional[CheckpointInfo],
        progress_cb: Optional[Callable[[ScanProgress], None]] = None,
    ) -> PhaseChunkResult:
        if progress_cb:
            progress_cb(
                pipeline._create_progress(
                    phase="grouping",
                    phase_description="Grouping by size...",
                    files_found=pipeline._files_found,
                )
            )
        size_groups = SizeReducer(progress_cb=pipeline.grouping.progress_cb).reduce(
            pipeline._discovered_files, pipeline.scan_id, pipeline.persistence
        )
        total_candidates = sum(len(g) for g in size_groups.values())
        return PhaseChunkResult(
            completed_units=total_candidates,
            total_units=total_candidates,
            artifacts_written=["size_candidates"] if pipeline.persistence else [],
            payload=size_groups,
        )

    def finalize(self, pipeline: "ScanPipeline", result: PhaseChunkResult) -> PhaseSummary:
        return PhaseSummary(phase_name=self.phase_name, completed_units=result.completed_units)


@dataclass
class PartialHashPhaseRunner:
    """Partial hash: read size_candidates, write partial_hashes and partial_candidates."""

    phase_name: ScanPhase = ScanPhase.PARTIAL_HASH

    def can_resume(self, pipeline: "ScanPipeline", checkpoint: Optional[CheckpointInfo]) -> bool:
        return checkpoint is not None and checkpoint.status == PhaseStatus.COMPLETED and checkpoint.is_finalized

    def run_chunk(
        self,
        pipeline: "ScanPipeline",
        checkpoint: Optional[CheckpointInfo],
        progress_cb: Optional[Callable[[ScanProgress], None]] = None,
    ) -> PhaseChunkResult:
        if progress_cb:
            progress_cb(
                pipeline._create_progress(
                    phase="hashing_partial",
                    phase_description="Computing partial hashes...",
                )
            )
        size_groups = pipeline._size_groups or {}
        partial_hash_groups = PartialHashReducer(
            hash_engine=pipeline.hash_engine,
            progress_cb=pipeline.grouping.progress_cb,
        ).reduce(size_groups, pipeline.scan_id, pipeline.persistence)
        total = sum(len(g) for g in partial_hash_groups.values())
        return PhaseChunkResult(
            completed_units=total,
            total_units=total,
            artifacts_written=["partial_hashes", "partial_candidates"] if pipeline.persistence else [],
            payload=partial_hash_groups,
        )

    def finalize(self, pipeline: "ScanPipeline", result: PhaseChunkResult) -> PhaseSummary:
        return PhaseSummary(phase_name=self.phase_name, completed_units=result.completed_units)


@dataclass
class FullHashPhaseRunner:
    """Full hash: read partial_candidates, write full_hashes and duplicate_groups."""

    phase_name: ScanPhase = ScanPhase.FULL_HASH

    def can_resume(self, pipeline: "ScanPipeline", checkpoint: Optional[CheckpointInfo]) -> bool:
        return checkpoint is not None and checkpoint.status == PhaseStatus.COMPLETED and checkpoint.is_finalized

    def run_chunk(
        self,
        pipeline: "ScanPipeline",
        checkpoint: Optional[CheckpointInfo],
        progress_cb: Optional[Callable[[ScanProgress], None]] = None,
    ) -> PhaseChunkResult:
        if progress_cb:
            progress_cb(
                pipeline._create_progress(
                    phase="hashing_full",
                    phase_description="Computing full hashes...",
                )
            )
        partial_hash_groups = pipeline._partial_hash_groups or {}
        duplicate_groups = FullHashReducer(
            hash_engine=pipeline.hash_engine,
            progress_cb=pipeline.grouping.progress_cb,
        ).reduce(partial_hash_groups, pipeline.scan_id, pipeline.persistence)
        return PhaseChunkResult(
            completed_units=len(duplicate_groups),
            total_units=len(duplicate_groups),
            artifacts_written=["full_hashes", "duplicate_groups", "duplicate_group_members"]
            if pipeline.persistence
            else [],
            payload=duplicate_groups,
        )

    def finalize(self, pipeline: "ScanPipeline", result: PhaseChunkResult) -> PhaseSummary:
        return PhaseSummary(phase_name=self.phase_name, completed_units=result.completed_units)


@dataclass
class ResultAssemblyPhaseRunner:
    """Assemble final duplicate groups from DB or from previous phase payload."""

    phase_name: ScanPhase = ScanPhase.RESULT_ASSEMBLY

    def can_resume(self, pipeline: "ScanPipeline", checkpoint: Optional[CheckpointInfo]) -> bool:
        return checkpoint is not None and checkpoint.status == PhaseStatus.COMPLETED and checkpoint.is_finalized

    def run_chunk(
        self,
        pipeline: "ScanPipeline",
        checkpoint: Optional[CheckpointInfo],
        progress_cb: Optional[Callable[[ScanProgress], None]] = None,
    ) -> PhaseChunkResult:
        duplicate_groups = pipeline._duplicate_groups or []
        return PhaseChunkResult(
            completed_units=len(duplicate_groups),
            total_units=len(duplicate_groups),
            payload=duplicate_groups,
        )

    def finalize(self, pipeline: "ScanPipeline", result: PhaseChunkResult) -> PhaseSummary:
        return PhaseSummary(phase_name=self.phase_name, completed_units=result.completed_units)


@dataclass
class ScanPipeline:
    """
    Main scan pipeline that orchestrates duplicate detection.

    Usage:
        config = ScanConfig(roots=[Path("/data")])
        pipeline = ScanPipeline(config)

        def on_progress(progress: ScanProgress):
            print(f"{progress.phase}: {progress.files_found} files")

        result = pipeline.run(progress_cb=on_progress)
    """

    config: ScanConfig
    scan_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    hash_cache_getter: Optional[Callable[[str], Optional[Dict[str, Any]]]] = None
    hash_cache_setter: Optional[Callable[[FileMetadata], bool]] = None
    persistence: Optional[Any] = None

    # Components
    discovery: FileDiscovery = field(init=False)
    hash_engine: HashEngine = field(init=False)
    grouping: GroupingEngine = field(init=False)

    # State
    _cancelled: bool = field(default=False, repr=False)
    _start_time: float = field(default=0, repr=False)
    _files_found: int = field(default=0, repr=False)
    _bytes_found: int = field(default=0, repr=False)
    _errors: List[str] = field(default_factory=list, repr=False)
    _discovered_files: List[FileMetadata] = field(default_factory=list, repr=False)
    _size_groups: Optional[Dict[int, List[FileMetadata]]] = field(default=None, repr=False)
    _partial_hash_groups: Optional[Dict[str, List[FileMetadata]]] = field(default=None, repr=False)
    _duplicate_groups: List[DuplicateGroup] = field(default_factory=list, repr=False)
    _incremental_prior_session_id: Optional[str] = field(default=None, repr=False)
    _incremental_prior_report: Optional[Dict[str, Any]] = field(default=None, repr=False)
    _incremental_merge_report: Optional[Dict[str, Any]] = field(default=None, repr=False)
    _current_dir_mtimes: Dict[str, int] = field(default_factory=dict, repr=False)
    _prior_dir_mtimes: Optional[Dict[str, int]] = field(default=None, repr=False)
    _benchmark: Optional[ScanBenchmarkReport] = field(default=None, repr=False)
    _phase_clock_phase: str = field(default="", repr=False)
    _phase_clock_started_at: float = field(default=0.0, repr=False)
    _phase_clock_last_updated_at: float = field(default=0.0, repr=False)
    phase_runners: List[PhaseRunner] = field(default_factory=list, init=False, repr=False)

    def __post_init__(self):
        # Initialize components
        self._sync_discovery_engine()
        self.hash_engine = HashEngine.from_config(self.config)
        self.hash_engine.cache_getter = self.hash_cache_getter
        self.hash_engine.cache_setter = self.hash_cache_setter
        self.grouping = GroupingEngine(
            hash_engine=self.hash_engine,
            progress_cb=None,
        )
        self.phase_runners = [
            DiscoveryPhaseRunner(),
            SizeReductionPhaseRunner(),
            PartialHashPhaseRunner(),
            FullHashPhaseRunner(),
            ResultAssemblyPhaseRunner(),
        ]

    def cancel(self):
        """Request cancellation of the scan."""
        self._cancelled = True
        self.discovery.cancel()

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled

    def _elapsed(self) -> float:
        """Get elapsed time in seconds."""
        return time.time() - self._start_time

    def _create_progress(self, **kwargs) -> ScanProgress:
        """Create a progress snapshot with common fields."""
        now = time.time()
        phase_name = str(kwargs.get("phase") or "")
        if phase_name:
            if phase_name != self._phase_clock_phase:
                self._phase_clock_phase = phase_name
                is_terminal = phase_name in ("complete", "cancelled", "error")
                if not is_terminal:
                    self._phase_clock_started_at = now
            self._phase_clock_last_updated_at = now

        phase_completed_units = int(kwargs.pop("phase_completed_units", kwargs.get("files_found", 0)) or 0)
        raw_phase_total = kwargs.pop("phase_total_units", kwargs.get("files_total"))
        phase_total_units = int(raw_phase_total) if raw_phase_total is not None else None
        is_terminal = phase_name in ("complete", "cancelled", "error")
        if is_terminal and self._phase_clock_started_at > 0:
            phase_elapsed_s = max(0.0, self._phase_clock_last_updated_at - self._phase_clock_started_at)
        elif phase_name and self._phase_clock_started_at > 0:
            phase_elapsed_s = max(0.0, now - self._phase_clock_started_at)
        else:
            phase_elapsed_s = 0.0

        ds = self.discovery.get_stats() if hasattr(self, "discovery") else {}
        dirs_scanned = int(ds.get("dirs_scanned", 0))
        dirs_reused = int(ds.get("dirs_reused", 0))
        dirs_skipped = int(ds.get("dirs_skipped_via_manifest", 0))

        return ScanProgress(
            scan_id=self.scan_id,
            elapsed_seconds=self._elapsed(),
            phase_elapsed_s=phase_elapsed_s,
            phase_started_at=self._phase_clock_started_at or None,
            phase_last_updated_at=self._phase_clock_last_updated_at or now,
            phase_total_units=phase_total_units,
            phase_completed_units=phase_completed_units,
            dirs_scanned=dirs_scanned,
            dirs_reused=dirs_reused,
            dirs_skipped_via_manifest=dirs_skipped,
            timestamp=now,
            **kwargs,
        )

    def _config_hash(self) -> str:
        payload = json.dumps(self.config.to_dict(), sort_keys=True).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def _discovery_config_hash(self) -> str:
        return discovery_config_hash(self.config)

    def _init_benchmark(self) -> None:
        self._benchmark = ScanBenchmarkReport(scan_id=self.scan_id)
        self.hash_engine.reset_metrics()

    def _set_phase_metrics(
        self,
        phase_name: ScanPhase,
        *,
        elapsed_ms: int,
        completed_units: int,
        artifacts_written: List[str],
        reused: bool,
    ) -> None:
        if not self._benchmark:
            return
        self._benchmark.phase_metrics[phase_name.value] = {
            "elapsed_ms": elapsed_ms,
            "completed_units": completed_units,
            "artifacts_produced": list(artifacts_written),
            "reused": reused,
        }

    def _sync_discovery_engine(self) -> None:
        discovery_options = DiscoveryOptions.from_config(self.config)
        prior_dir_mtimes = self._prior_dir_mtimes if self.config.incremental_discovery else None
        prior_session_id = self._incremental_prior_session_id if self.config.incremental_discovery else None
        get_prior_files = None
        if self.persistence and prior_session_id and prior_dir_mtimes is not None:

            def get_prior_files(dir_path):
                return self.persistence.inventory_repo.iter_under_directory(
                    prior_session_id,
                    dir_path,
                )

        self.discovery = FileDiscovery(
            discovery_options,
            prior_session_id=prior_session_id,
            prior_dir_mtimes=prior_dir_mtimes,
            get_prior_files_under_dir=get_prior_files,
            dir_mtimes_sink=self._current_dir_mtimes,
        )

    def _prepare_incremental_discovery(self, is_new_scan: bool) -> None:
        self._incremental_prior_session_id = None
        self._incremental_prior_report = None
        self._incremental_merge_report = None
        self._prior_dir_mtimes = None
        self._current_dir_mtimes = {}

        if not self.persistence or not is_new_scan or not self.config.incremental_discovery:
            if self._benchmark:
                self._benchmark.discovery_reuse_mode = "none"
                self._benchmark.prior_session_found = False
                self._benchmark.prior_session_compatible = False
                self._benchmark.prior_session_rejected_reason = "none"
            self._sync_discovery_engine()
            return

        prior_session_id, report = find_compatible_prior_session(
            self.persistence,
            self.config,
            exclude_session_id=self.scan_id,
        )
        self._incremental_prior_session_id = prior_session_id
        self._incremental_prior_report = report.to_dict()
        if self._benchmark:
            self._benchmark.prior_session_found = bool(report.candidate_session_id)
            self._benchmark.prior_session_compatible = bool(prior_session_id)
            self._benchmark.prior_session_rejected_reason = report.reason
            self._benchmark.discovery_reuse_mode = "merge" if prior_session_id else "none"
        if prior_session_id:
            try:
                self._prior_dir_mtimes = self.persistence.discovery_dir_repo.get_dir_mtimes(prior_session_id)
                if self._benchmark and self._prior_dir_mtimes:
                    self._benchmark.discovery_reuse_mode = "subtree_skip"
            except Exception:
                self._prior_dir_mtimes = None
        self._sync_discovery_engine()

    def _persist_directory_manifest(self) -> None:
        if not self.persistence or not self._current_dir_mtimes:
            return
        self.persistence.discovery_dir_repo.insert_batch(
            self.scan_id,
            list(self._current_dir_mtimes.items()),
        )

    def _initialize_durable_session(self, only_if_missing: bool = False) -> None:
        if not self.persistence:
            return
        if only_if_missing and self.persistence.session_repo.get(self.scan_id) is not None:
            return
        self.persistence.shadow_write_session(
            session_id=self.scan_id,
            config_json=json.dumps(self.config.to_dict()),
            config_hash=self._config_hash(),
            root_fingerprint=root_fingerprint(self.config),
            discovery_config_hash=self._discovery_config_hash(),
            status="running",
            current_phase=ScanPhase.DISCOVERY.value,
        )

    def _update_phase_checkpoint(
        self,
        phase_name: ScanPhase,
        completed_units: int,
        total_units: Optional[int],
        status: PhaseStatus,
        metadata_json: Optional[Dict[str, Any]] = None,
        is_finalized: bool = False,
    ) -> None:
        if not self.persistence:
            return
        meta = dict(metadata_json or {})
        if is_finalized:
            meta.update(self._finalized_checkpoint_metadata())
        self.persistence.shadow_write_checkpoint(
            session_id=self.scan_id,
            phase_name=phase_name,
            completed_units=completed_units,
            total_units=total_units,
            status=status,
            metadata_json=meta,
        )
        if self._benchmark:
            self._benchmark.checkpoint_writes += 1
        self.persistence.shadow_update_session(
            session_id=self.scan_id,
            status="running" if status != PhaseStatus.FAILED else "failed",
            current_phase=phase_name.value,
            failure_reason=(metadata_json or {}).get("error"),
        )

    def _finalized_checkpoint_metadata(self) -> Dict[str, Any]:
        """Compatibility metadata for authoritative resume."""
        schema_version = getattr(self.persistence, "schema_version", 4)
        if callable(schema_version):
            schema_version = schema_version()
        return {
            "schema_version": schema_version,
            "phase_version": PHASE_VERSION,
            "config_hash": self._config_hash(),
            "is_finalized": True,
            "resume_policy": "safe",
        }

    def _load_phase_output_from_db(self, phase: ScanPhase) -> None:
        """Load this phase's output into pipeline state from durable artifacts."""
        if not self.persistence:
            return
        if phase == ScanPhase.DISCOVERY:
            self._discovered_files = list(self.persistence.inventory_repo.iter_by_session(self.scan_id))
            self._files_found = len(self._discovered_files)
            self._bytes_found = sum(f.size for f in self._discovered_files)

    def _load_all_durable_state_before(self, first_runnable: ScanPhase) -> None:
        """Load pipeline state for all phases before first_runnable from DB."""
        if not self.persistence:
            return
        order_idx = {p: i for i, p in enumerate(PHASE_ORDER)}
        first_idx = order_idx.get(first_runnable, 0)
        if first_idx <= 0:
            return
        self._load_phase_output_from_db(ScanPhase.DISCOVERY)
        if first_idx <= 1:
            return
        inv = self.persistence.inventory_repo
        size_repo = self.persistence.size_candidate_repo
        size_groups = size_repo.iter_groups(self.scan_id)
        self._size_groups = {
            size: inv.load_metadata_for_file_ids(self.scan_id, ids) for size, ids in size_groups.items()
        }
        if first_idx <= 2:
            return
        partial_repo = self.persistence.partial_candidate_repo
        partial_groups = partial_repo.iter_groups(self.scan_id)
        self._partial_hash_groups = {
            ph: inv.load_metadata_for_file_ids(self.scan_id, ids) for ph, ids in partial_groups.items()
        }
        if first_idx <= 3:
            return
        self._duplicate_groups = self.persistence.duplicate_group_repo.load_groups(self.scan_id, inv)

    def run(
        self,
        progress_cb: Optional[Callable[[ScanProgress], None]] = None,
        event_bus: Optional[Any] = None,
    ) -> ScanResult:
        """
        Run the complete scan pipeline.

        Args:
            progress_cb: Called with progress updates

        Returns:
            ScanResult containing all duplicate groups
        """
        self._start_time = time.time()
        self.grouping.progress_cb = progress_cb
        self._init_benchmark()
        self._init_benchmark()

        first_runnable_phase = ScanPhase.DISCOVERY
        session_exists = False
        if self.persistence:
            session_exists = self.persistence.session_repo.get(self.scan_id) is not None
            resolver = ResumeResolver(self.persistence)
            decision = resolver.resolve(self.scan_id, self.config, is_new_scan=not session_exists)
            first_runnable_phase = decision.first_runnable_phase
            if event_bus is not None:
                try:
                    from ..orchestration.events import ScanEvent, ScanEventType

                    event_bus.publish(
                        ScanEvent(
                            ScanEventType.RESUME_REQUESTED,
                            self.scan_id,
                            {"decision": decision.log_message()},
                        )
                    )
                    if decision.outcome.value == "safe_resume":
                        # Compute reused phases and time saved for Work Saved panel
                        reused_phases: List[str] = []
                        time_saved_s: float = 0.0
                        order_idx = {p: i for i, p in enumerate(PHASE_ORDER)}
                        first_idx = order_idx.get(first_runnable_phase, 0)
                        for phase in PHASE_ORDER:
                            if order_idx.get(phase, 0) >= first_idx:
                                break
                            cp = self.persistence.checkpoint_repo.get(self.scan_id, phase)
                            if cp and cp.status == PhaseStatus.COMPLETED and cp.is_finalized:
                                reused_phases.append(phase.value)
                                dur_ms = (cp.metadata_json or {}).get("duration_ms", 0)
                                time_saved_s += dur_ms / 1000.0
                        event_bus.publish(
                            ScanEvent(
                                ScanEventType.RESUME_VALIDATED,
                                self.scan_id,
                                {
                                    "reason": decision.reason,
                                    "first_phase": first_runnable_phase.value,
                                    "reused_phases": reused_phases,
                                    "time_saved_estimate": time_saved_s,
                                },
                            )
                        )
                    else:
                        event_bus.publish(
                            ScanEvent(
                                ScanEventType.RESUME_REJECTED,
                                self.scan_id,
                                {"reason": decision.reason, "outcome": decision.outcome.value},
                            )
                        )
                except Exception as e:
                    _log.warning("Failed to publish resume decision event: %s", e)
                    try:
                        from ..infrastructure.diagnostics import CATEGORY_CALLBACK, get_diagnostics_recorder

                        get_diagnostics_recorder().record(
                            CATEGORY_CALLBACK, "Resume decision event publish failed", str(e)
                        )
                    except Exception:
                        pass
            only_if_missing = decision.outcome.value in ("safe_resume", "rebuild_current_phase")
            if decision.outcome.value == "restart_required":
                self._prepare_incremental_discovery(is_new_scan=not session_exists)
                self._initialize_durable_session()
            else:
                self._prepare_incremental_discovery(is_new_scan=False)
                self._initialize_durable_session(only_if_missing=only_if_missing and session_exists)
            if decision.outcome.value == "safe_resume":
                self._load_all_durable_state_before(first_runnable_phase)
            if decision.outcome.value == "rebuild_current_phase":
                cp_repo = self.persistence.checkpoint_repo
                cp_repo.upsert(
                    CheckpointInfo(
                        session_id=self.scan_id,
                        phase_name=first_runnable_phase,
                        status=PhaseStatus.PENDING,
                        metadata_json={"is_finalized": False},
                    )
                )
        else:
            self._prepare_incremental_discovery(is_new_scan=True)
            self._initialize_durable_session()

        result = ScanResult(
            scan_id=self.scan_id,
            config=self.config,
            started_at=datetime.now(),
        )
        duplicate_groups: List[DuplicateGroup] = []

        try:
            order_idx = {p: i for i, p in enumerate(PHASE_ORDER)}
            first_idx = order_idx.get(first_runnable_phase, 0)
            for runner in self.phase_runners:
                runner_idx = order_idx.get(runner.phase_name, -1)
                if runner_idx < first_idx:
                    continue

                checkpoint = None
                if self.persistence:
                    checkpoint = self.persistence.checkpoint_repo.get(self.scan_id, runner.phase_name)
                if checkpoint and runner.can_resume(self, checkpoint):
                    self._load_phase_output_from_db(runner.phase_name)
                    if runner.phase_name == ScanPhase.RESULT_ASSEMBLY and self._duplicate_groups:
                        duplicate_groups = self._duplicate_groups
                    self._set_phase_metrics(
                        runner.phase_name,
                        elapsed_ms=0,
                        completed_units=checkpoint.completed_units if checkpoint else 0,
                        artifacts_written=[],
                        reused=True,
                    )
                    continue

                if event_bus is not None and self.persistence:
                    try:
                        from ..orchestration.events import ScanEvent, ScanEventType

                        event_bus.publish(
                            ScanEvent(
                                ScanEventType.PHASE_REBUILD_STARTED,
                                self.scan_id,
                                {"phase": runner.phase_name.value},
                            )
                        )
                    except Exception as e:
                        _log.warning("Failed to publish phase rebuild event: %s", e)
                        try:
                            from ..infrastructure.diagnostics import CATEGORY_CALLBACK, get_diagnostics_recorder

                            get_diagnostics_recorder().record(
                                CATEGORY_CALLBACK, "Phase rebuild event publish failed", str(e)
                            )
                        except Exception:
                            pass

                phase_status = PhaseStatus.RUNNING
                self._update_phase_checkpoint(runner.phase_name, 0, None, phase_status)
                phase_start = time.time()
                phase_result = runner.run_chunk(self, checkpoint, progress_cb)
                summary = runner.finalize(self, phase_result)
                duration_ms = int((time.time() - phase_start) * 1000)
                self._set_phase_metrics(
                    runner.phase_name,
                    elapsed_ms=duration_ms,
                    completed_units=phase_result.completed_units,
                    artifacts_written=phase_result.artifacts_written,
                    reused=False,
                )
                meta = dict(summary.metadata)
                meta["duration_ms"] = duration_ms
                self._update_phase_checkpoint(
                    runner.phase_name,
                    phase_result.completed_units,
                    phase_result.total_units,
                    PhaseStatus.COMPLETED,
                    metadata_json=meta,
                    is_finalized=True,
                )

                if runner.phase_name == ScanPhase.DISCOVERY:
                    self._discovered_files = phase_result.payload or []
                    if not self._discovered_files and self.config.roots:
                        result.errors.append(
                            "No files were found. Check that the folder path is correct, "
                            "readable, and contains files (check filters: min size, extensions)."
                        )
                elif runner.phase_name == ScanPhase.SIZE_REDUCTION:
                    self._size_groups = phase_result.payload or {}
                elif runner.phase_name == ScanPhase.PARTIAL_HASH:
                    self._partial_hash_groups = phase_result.payload or {}
                elif runner.phase_name == ScanPhase.FULL_HASH:
                    self._duplicate_groups = phase_result.payload or []
                elif runner.phase_name == ScanPhase.RESULT_ASSEMBLY:
                    duplicate_groups = phase_result.payload or []

                if self._cancelled:
                    result.errors.append("Scan cancelled by user")
                    result.completed_at = datetime.now()
                    if self.persistence:
                        self.persistence.shadow_update_session(
                            session_id=self.scan_id,
                            status="cancelled",
                            current_phase=runner.phase_name.value,
                            completed=True,
                        )
                    return result

            # Build result
            result.files_scanned = self._files_found
            result.bytes_scanned = self._bytes_found
            result.duplicate_groups = duplicate_groups
            result.total_duplicates = sum(len(g.files) - 1 for g in duplicate_groups)
            result.total_reclaimable_bytes = sum(g.reclaimable_size for g in duplicate_groups)
            result.errors = self._errors
            result.incremental_discovery_report = self._incremental_merge_report or self._incremental_prior_report

            if self._cancelled:
                result.errors.append("Scan cancelled by user")

        except Exception as e:
            self._errors.append(str(e))
            result.errors = self._errors
            if self.persistence:
                self.persistence.shadow_update_session(
                    session_id=self.scan_id,
                    status="failed",
                    current_phase=ScanPhase.RESULT_ASSEMBLY.value,
                    failure_reason=str(e),
                    completed=True,
                )
            if progress_cb:
                progress_cb(
                    self._create_progress(
                        phase="error",
                        phase_description=f"Error: {str(e)}",
                        error_count=len(self._errors),
                        last_error=str(e),
                    )
                )

        finally:
            result.completed_at = datetime.now()
            if self._benchmark:
                hash_metrics = self.hash_engine.metrics_snapshot()
                self._benchmark.hash_cache_hits = hash_metrics.get("hash_cache_hits", 0)
                self._benchmark.hash_cache_misses = hash_metrics.get("hash_cache_misses", 0)
                self._benchmark.full_hash_computed = hash_metrics.get("full_hash_computed", 0)
                self._benchmark.partial_hash_computed = hash_metrics.get("partial_hash_computed", 0)
                self._benchmark.total_elapsed_ms = int(self._elapsed() * 1000)
                result.benchmark_report = self._benchmark.to_dict()
                _log.info("Benchmark summary: %s", format_operator_summary(result.benchmark_report))
            if self.persistence and not self._cancelled and not result.errors:
                self.persistence.shadow_update_session(
                    session_id=self.scan_id,
                    status="completed",
                    current_phase=ScanPhase.RESULT_ASSEMBLY.value,
                    metrics={
                        "files_scanned": result.files_scanned,
                        "duplicates_found": result.total_duplicates,
                        "reclaimable_bytes": result.total_reclaimable_bytes,
                        "incremental_discovery": result.incremental_discovery_report or {},
                        "benchmark": result.benchmark_report or {},
                    },
                    completed=True,
                )

            if progress_cb:
                progress_cb(
                    self._create_progress(
                        phase="complete" if not self._cancelled else "cancelled",
                        phase_description=f"Scan complete. Found {len(result.duplicate_groups)} duplicate groups.",
                        files_found=result.files_scanned,
                        groups_found=len(result.duplicate_groups),
                        duplicates_found=result.total_duplicates,
                    )
                )

        return result

    def _discover_files(self, progress_cb: Optional[Callable[[ScanProgress], None]] = None) -> List[FileMetadata]:
        """
        Discover all files.

        For 1M+ files, we collect into a list but could stream for even lower memory.
        Inventory writes use batch_size; checkpoints use checkpoint_every_files (decoupled).
        """
        discovery_start = time.time()
        files = []
        last_progress_time = 0
        progress_interval = self.config.progress_interval_ms / 1000
        checkpoint_every = getattr(self.config, "checkpoint_every_files", 5000)
        last_checkpoint_at = 0
        last_checkpoint_ts = time.monotonic()
        checkpoint_interval_s = 5.0

        batch: List[FileMetadata] = []
        for file in self.discovery.discover():
            if self._cancelled:
                break

            files.append(file)
            batch.append(file)
            self._files_found += 1
            self._bytes_found += file.size

            if self.persistence and len(batch) >= self.config.batch_size:
                try:
                    from ...infrastructure.profiler import measure

                    with measure("pipeline.inventory_write"):
                        self.persistence.shadow_write_inventory(self.scan_id, batch)
                except ImportError:
                    self.persistence.shadow_write_inventory(self.scan_id, batch)
                if self._benchmark:
                    self._benchmark.inventory_write_batches += 1
                    self._benchmark.inventory_rows_written += len(batch)
                batch = []

                # Checkpoint only when file threshold or time threshold crossed
                files_due = self._files_found - last_checkpoint_at >= checkpoint_every
                time_due = (time.monotonic() - last_checkpoint_ts) >= checkpoint_interval_s
                if files_due or time_due:
                    try:
                        from ...infrastructure.profiler import measure

                        with measure("pipeline.checkpoint_write"):
                            self._update_phase_checkpoint(
                                ScanPhase.DISCOVERY,
                                completed_units=self._files_found,
                                total_units=None,
                                status=PhaseStatus.RUNNING,
                                metadata_json={"bytes_found": self._bytes_found},
                            )
                    except ImportError:
                        self._update_phase_checkpoint(
                            ScanPhase.DISCOVERY,
                            completed_units=self._files_found,
                            total_units=None,
                            status=PhaseStatus.RUNNING,
                            metadata_json={"bytes_found": self._bytes_found},
                        )
                    last_checkpoint_at = self._files_found
                    last_checkpoint_ts = time.monotonic()

            # Throttle progress updates (pipeline → coordinator → hub; UI delivery further throttled
            # in `ProjectionHub.THROTTLE_MS` / `ProjectionHubStoreAdapter` — see `docs/TODO_POST_PHASE3.md`).
            current_time = time.time()
            if progress_cb and (current_time - last_progress_time) >= progress_interval:
                progress_cb(
                    self._create_progress(
                        phase="discovering",
                        phase_description=f"Discovering files: {self._files_found} found...",
                        files_found=self._files_found,
                        bytes_found=self._bytes_found,
                        current_file=file.path,
                    )
                )
                last_progress_time = current_time

        if self.persistence and batch:
            try:
                from ...infrastructure.profiler import measure

                with measure("pipeline.inventory_write"):
                    self.persistence.shadow_write_inventory(self.scan_id, batch)
            except ImportError:
                self.persistence.shadow_write_inventory(self.scan_id, batch)
            if self._benchmark:
                self._benchmark.inventory_write_batches += 1
                self._benchmark.inventory_rows_written += len(batch)
        if self.persistence:
            self._update_phase_checkpoint(
                ScanPhase.DISCOVERY,
                completed_units=self._files_found,
                total_units=self._files_found,
                status=PhaseStatus.RUNNING,
                metadata_json={"bytes_found": self._bytes_found},
            )
            self._persist_directory_manifest()

        if self.persistence and self._incremental_prior_session_id:
            prior_files = self.persistence.inventory_repo.iter_by_session(self._incremental_prior_session_id)
            self._incremental_merge_report = build_discovery_merge_report(
                files,
                prior_files,
                prior_session_id=self._incremental_prior_session_id,
            ).to_dict()

        if self._benchmark:
            stats = self.discovery.get_stats()
            self._benchmark.files_discovered_total = self._files_found
            self._benchmark.files_discovered_fresh = int(stats.get("files_discovered_fresh", 0))
            self._benchmark.files_reused_from_prior_inventory = int(stats.get("files_reused_from_prior_inventory", 0))
            self._benchmark.dirs_scanned = int(stats.get("dirs_scanned", 0))
            self._benchmark.dirs_reused = int(stats.get("dirs_reused", 0))
            self._benchmark.dirs_skipped_via_manifest = int(stats.get("dirs_skipped_via_manifest", 0))
            self._benchmark.stat_calls = int(stats.get("stat_calls", 0))
            self._benchmark.resolve_calls = int(stats.get("resolve_calls", 0))
            self._benchmark.discovery_elapsed_ms = int((time.time() - discovery_start) * 1000)
            if (
                self._benchmark.discovery_reuse_mode == "subtree_skip"
                and self._benchmark.dirs_skipped_via_manifest == 0
            ):
                self._benchmark.discovery_reuse_mode = "merge"
            if not self._incremental_prior_session_id:
                self._benchmark.discovery_reuse_mode = "none"

        try:
            from ...infrastructure.profiler import get_stats

            stats = get_stats()
            if stats:
                _log.info("Profiler stats: %s", stats)
        except ImportError:
            pass

        return files

    def create_deletion_plan(
        self, result: ScanResult, policy: DeletionPolicy = DeletionPolicy.TRASH, keep_strategy: str = "first"
    ) -> DeletionPlan:
        """
        Create a deletion plan from scan results.

        Args:
            result: The scan result
            policy: Deletion policy (trash or permanent)
            keep_strategy: Which file to keep (first, oldest, newest, largest, smallest)

        Returns:
            DeletionPlan
        """
        engine = DeletionEngine(persistence=self.persistence)
        return engine.create_plan_from_groups(
            scan_id=result.scan_id,
            groups=result.duplicate_groups,
            policy=policy,
            keep_strategy=keep_strategy,
        )

    def execute_deletion(
        self, plan: DeletionPlan, dry_run: bool = False, progress_cb: Optional[Callable[[int, int, str], bool]] = None
    ) -> DeletionResult:
        """
        Execute a deletion plan.

        Args:
            plan: The deletion plan
            dry_run: If True, don't actually delete (preview mode)
            progress_cb: Progress callback(current, total, filename) -> bool (continue?)

        Returns:
            DeletionResult
        """
        engine = DeletionEngine(dry_run=dry_run, persistence=self.persistence)
        return engine.execute_plan(plan, progress_cb)


@dataclass
class ResumableScanPipeline(ScanPipeline):
    """
    Scan pipeline with persistence for resumability.

    Saves scan state to disk at checkpoints, allowing recovery
    from interruptions for very large scans.
    """

    checkpoint_interval: int = 10000  # Files between checkpoints
    checkpoint_dir: Optional[Path] = None

    def __post_init__(self):
        super().__post_init__()
        if self.checkpoint_dir:
            self.checkpoint_dir = Path(self.checkpoint_dir)
            self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    def _save_checkpoint(self, files: List[FileMetadata]):
        """Save current state to disk."""
        if not self.checkpoint_dir:
            return

        try:
            import json

            checkpoint_file = self.checkpoint_dir / f"{self.scan_id}_checkpoint.json"

            data = {
                "scan_id": self.scan_id,
                "config": self.config.to_dict(),
                "files": [f.to_dict() for f in files],
                "timestamp": time.time(),
            }

            with open(checkpoint_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except (OSError, IOError, TypeError, ValueError) as e:
            _log.warning("Checkpoint write failed (scan continues): %s", e)
            try:
                from ..infrastructure.diagnostics import CATEGORY_CHECKPOINT, get_diagnostics_recorder

                get_diagnostics_recorder().record(
                    CATEGORY_CHECKPOINT,
                    "Checkpoint write failed",
                    str(e),
                )
            except Exception:
                pass

    def _load_checkpoint(self) -> Optional[List[FileMetadata]]:
        """Load state from disk if available."""
        if not self.checkpoint_dir:
            return None

        try:
            import json

            checkpoint_file = self.checkpoint_dir / f"{self.scan_id}_checkpoint.json"

            if not checkpoint_file.exists():
                return None

            with open(checkpoint_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            return [FileMetadata.from_dict(f) for f in data.get("files", [])]
        except (OSError, IOError, json.JSONDecodeError, KeyError, TypeError) as e:
            _log.debug("Checkpoint load failed or invalid: %s", e)
            return None

    @staticmethod
    def load_checkpoint_config(checkpoint_dir: Path, scan_id: str) -> Optional[ScanConfig]:
        """Load ScanConfig from a checkpoint file (for resume). Returns None if missing or invalid."""
        try:
            import json

            path = Path(checkpoint_dir) / f"{scan_id}_checkpoint.json"
            if not path.exists():
                return None
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return ScanConfig.from_dict(data.get("config", {}))
        except (OSError, IOError, json.JSONDecodeError, KeyError, TypeError) as e:
            _log.debug("Checkpoint config load failed: %s", e)
            return None

    def _clear_checkpoint(self) -> None:
        """Remove checkpoint file after successful completion."""
        if not self.checkpoint_dir:
            return
        try:
            checkpoint_file = self.checkpoint_dir / f"{self.scan_id}_checkpoint.json"
            if checkpoint_file.exists():
                checkpoint_file.unlink()
        except OSError as e:
            _log.debug("Checkpoint cleanup unlink failed: %s", e)

    def run(
        self,
        progress_cb: Optional[Callable[[ScanProgress], None]] = None,
        event_bus: Optional[Any] = None,
    ) -> ScanResult:
        """
        Run the scan pipeline with checkpoint support.
        If a checkpoint exists for this scan_id, discovery is skipped and the
        cached file list is used. After discovery, state is saved so that
        cancel/interrupt can be resumed later.
        """
        self._start_time = time.time()
        self.grouping.progress_cb = progress_cb

        result = ScanResult(
            scan_id=self.scan_id,
            config=self.config,
            started_at=datetime.now(),
        )

        try:
            # Try resume from checkpoint
            discovered_files = self._load_checkpoint()
            if discovered_files:
                self._prepare_incremental_discovery(is_new_scan=False)
                if self._benchmark:
                    self._benchmark.files_discovered_total = len(discovered_files)
                if progress_cb:
                    progress_cb(
                        self._create_progress(
                            phase="resuming",
                            phase_description="Resuming from checkpoint...",
                            files_found=len(discovered_files),
                            bytes_found=sum(f.size for f in discovered_files),
                        )
                    )
                self._files_found = len(discovered_files)
                self._bytes_found = sum(f.size for f in discovered_files)
            else:
                self._prepare_incremental_discovery(is_new_scan=True)
                # Phase 1: Discovery
                if progress_cb:
                    progress_cb(
                        self._create_progress(
                            phase="discovering",
                            phase_description="Discovering files...",
                        )
                    )

                discovered_files = self._discover_files(progress_cb)
                if self.checkpoint_dir and discovered_files:
                    self._save_checkpoint(discovered_files)

            if self._cancelled:
                result.errors.append("Scan cancelled by user")
                result.completed_at = datetime.now()
                return result

            if not discovered_files and self.config.roots:
                result.errors.append(
                    "No files were found. Check that the folder path is correct, "
                    "readable, and contains files (check filters: min size, extensions)."
                )

            # Phase 2-4: Grouping and hashing
            if progress_cb:
                progress_cb(
                    self._create_progress(
                        phase="grouping",
                        phase_description="Finding duplicates...",
                        files_found=self._files_found,
                        bytes_found=self._bytes_found,
                    )
                )

            duplicate_groups = self.grouping.find_duplicates(
                iter(discovered_files), self.scan_id, cancel_check=lambda: self._cancelled
            )

            result.files_scanned = self._files_found
            result.bytes_scanned = self._bytes_found
            result.duplicate_groups = duplicate_groups
            result.total_duplicates = sum(len(g.files) - 1 for g in duplicate_groups)
            result.total_reclaimable_bytes = sum(g.reclaimable_size for g in duplicate_groups)
            result.errors = self._errors
            result.incremental_discovery_report = self._incremental_merge_report or self._incremental_prior_report

            if self._cancelled:
                result.errors.append("Scan cancelled by user")

        except Exception as e:
            self._errors.append(str(e))
            result.errors = self._errors
            if progress_cb:
                progress_cb(
                    self._create_progress(
                        phase="error",
                        phase_description=f"Error: {str(e)}",
                        error_count=len(self._errors),
                        last_error=str(e),
                    )
                )

        finally:
            result.completed_at = datetime.now()
            if self._benchmark:
                hash_metrics = self.hash_engine.metrics_snapshot()
                self._benchmark.hash_cache_hits = hash_metrics.get("hash_cache_hits", 0)
                self._benchmark.hash_cache_misses = hash_metrics.get("hash_cache_misses", 0)
                self._benchmark.full_hash_computed = hash_metrics.get("full_hash_computed", 0)
                self._benchmark.partial_hash_computed = hash_metrics.get("partial_hash_computed", 0)
                self._benchmark.total_elapsed_ms = int(self._elapsed() * 1000)
                result.benchmark_report = self._benchmark.to_dict()
            if not self._cancelled and result.errors == []:
                self._clear_checkpoint()
            if progress_cb:
                progress_cb(
                    self._create_progress(
                        phase="complete" if not self._cancelled else "cancelled",
                        phase_description=f"Scan complete. Found {len(result.duplicate_groups)} duplicate groups.",
                        files_found=result.files_scanned,
                        groups_found=len(result.duplicate_groups),
                        duplicates_found=result.total_duplicates,
                    )
                )

        return result


def quick_scan(
    path: Path | str, min_size: int = 1, progress_cb: Optional[Callable[[ScanProgress], None]] = None
) -> ScanResult:
    """
    Quick scan with default settings.

    Usage:
        result = quick_scan("/data", min_size=1024)
        print(f"Found {len(result.duplicate_groups)} duplicate groups")
    """
    config = ScanConfig(
        roots=[Path(path)],
        min_size_bytes=min_size,
    )

    pipeline = ScanPipeline(config)
    return pipeline.run(progress_cb)
