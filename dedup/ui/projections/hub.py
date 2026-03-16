"""
ProjectionHub
=============
The single bottleneck between engine events and UI state.

Threading contract
------------------
- Engine publishes ScanEvent objects on background threads via EventBus.
- ProjectionHub._handle_event() is called on those background threads.
  It updates internal snapshots under a lock and marks projection types dirty.
- A Tk after() poll loop runs every POLL_MS on the main UI thread.
  On each tick it checks dirty flags and, respecting per-type throttle intervals,
  delivers the latest snapshot to subscribed UI callbacks.

Design rules
------------
1. UI callbacks are ALWAYS called on the Tk main thread (no thread-crossing).
2. Snapshots are replaced atomically (frozen dataclasses — no in-place mutation).
3. Throttle intervals ensure the UI is never flooded with updates.
4. Phase and session transitions are delivered immediately (throttle = 0 ms).
5. Metrics updates are coalesced at 300 ms intervals.
6. Event-log entries are batched at 750 ms.
7. No widget should listen to raw EventBus events directly.

UI event type labels (for subscription keys)
--------------------------------------------
  "session"       — SessionProjection delivered to SessionProjection subscribers
  "phase"         — Dict[phase_name, PhaseProjection]
  "metrics"       — MetricsProjection
  "compatibility" — CompatibilityProjection
  "deletion"      — DeletionReadinessProjection (not from engine; hub re-publishes on request)
  "events_log"    — List[str]  (structured event log entries)
  "terminal"      — SessionProjection  (scan finished / failed / cancelled)
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from ...orchestration.events import EventBus, ScanEvent, ScanEventType

_log = logging.getLogger(__name__)

from .session_projection import (
    SessionProjection, EMPTY_SESSION, build_session_from_event,
)
from .phase_projection import (
    PhaseProjection, PHASE_ORDER, canonical_phase,
    initial_phase_map, build_phase_from_checkpoint,
)
from .metrics_projection import (
    MetricsProjection, EMPTY_METRICS, build_metrics_from_progress, merge_metrics,
)
from .compatibility_projection import (
    CompatibilityProjection, EMPTY_COMPAT,
    build_compat_from_event_payload,
)
from .deletion_projection import DeletionReadinessProjection, EMPTY_DELETION

# Poll interval (ms): how often the Tk main thread checks for dirty projections.
POLL_MS = 80

# Throttle per projection type (ms between consecutive deliveries to UI).
# 0 = deliver as soon as dirty (next poll tick). Larger values reduce UI work on large scans.
THROTTLE_MS: Dict[str, int] = {
    "session":       0,
    "phase":         150,   # was 0; avoid flooding timeline on rapid progress
    "compatibility": 0,
    "terminal":      0,
    "metrics":       400,   # was 300
    "events_log":    1200,  # was 750; listbox refresh is costly
    "deletion":      0,
}

Callback = Callable[[Any], None]


class ProjectionHub:
    """
    Central projection broker wired to the engine EventBus.
    Must be created on the Tk main thread (owns the after() schedule).
    """

    def __init__(self, event_bus: EventBus, tk_root):
        self._bus      = event_bus
        self._root     = tk_root
        self._lock     = threading.Lock()
        self._alive    = True

        # --- Current projection snapshots ---
        self._session:  SessionProjection       = EMPTY_SESSION
        self._phases:   Dict[str, PhaseProjection] = initial_phase_map()
        self._metrics:  MetricsProjection        = EMPTY_METRICS
        self._compat:   CompatibilityProjection  = EMPTY_COMPAT
        self._deletion: DeletionReadinessProjection = EMPTY_DELETION
        self._events_log: List[str]              = []

        # --- Checkpoint throttling: per-phase {phase: files} and timestamps ---
        self._last_checkpoint: Dict[str, Any] = {}  # phase -> files, phase_ts -> time

        # --- Dirty flags and last-delivery timestamps ---
        self._dirty: Dict[str, bool]  = {k: False for k in THROTTLE_MS}
        self._last_delivered: Dict[str, float] = {k: 0.0 for k in THROTTLE_MS}

        # --- UI subscribers: type -> list of callbacks ---
        self._subscribers: Dict[str, List[Callback]] = {k: [] for k in THROTTLE_MS}
        self._sub_lock = threading.Lock()

        # Subscribe to every engine event type
        for et in ScanEventType:
            self._bus.subscribe(et, self._handle_event)

        # Start the Tk poll loop
        self._schedule_poll()

    # ------------------------------------------------------------------
    # Public subscription API
    # ------------------------------------------------------------------

    def subscribe(self, projection_type: str, callback: Callback) -> Callable[[], None]:
        """
        Subscribe to a projection type.
        callback(snapshot) is always called on the Tk main thread.
        Returns an unsubscribe function.
        """
        with self._sub_lock:
            self._subscribers.setdefault(projection_type, []).append(callback)

        def unsub():
            with self._sub_lock:
                try:
                    self._subscribers[projection_type].remove(callback)
                except (KeyError, ValueError):
                    pass
        return unsub

    # ------------------------------------------------------------------
    # Current snapshot accessors (thread-safe reads for initial pull)
    # ------------------------------------------------------------------

    @property
    def session(self) -> SessionProjection:
        with self._lock:
            return self._session

    @property
    def phases(self) -> Dict[str, PhaseProjection]:
        with self._lock:
            return dict(self._phases)

    @property
    def metrics(self) -> MetricsProjection:
        with self._lock:
            return self._metrics

    @property
    def compat(self) -> CompatibilityProjection:
        with self._lock:
            return self._compat

    @property
    def deletion(self) -> DeletionReadinessProjection:
        with self._lock:
            return self._deletion

    # ------------------------------------------------------------------
    # External push (from ReviewPage keep-selection changes, etc.)
    # ------------------------------------------------------------------

    def push_deletion(self, proj: DeletionReadinessProjection) -> None:
        """Allow the ReviewPage to push a new DeletionReadinessProjection."""
        with self._lock:
            self._deletion = proj
            self._dirty["deletion"] = True

    def push_event_log_entry(self, entry: str) -> None:
        with self._lock:
            self._events_log.insert(0, entry)
            if len(self._events_log) > 500:
                self._events_log = self._events_log[:500]
            self._dirty["events_log"] = True

    def shutdown(self) -> None:
        self._alive = False

    # ------------------------------------------------------------------
    # Engine event handler  (called on background threads)
    # ------------------------------------------------------------------

    def _handle_event(self, event: ScanEvent) -> None:
        """
        Translate a raw engine ScanEvent into projection updates.
        Called from background threads — must only touch self._lock protected state.
        """
        et      = event.event_type
        sid     = event.scan_id
        payload = event.payload or {}

        with self._lock:
            if et == ScanEventType.SESSION_STARTED:
                self._session = build_session_from_event(
                    session_id=sid,
                    status="running",
                    scan_root=self._extract_root(payload),
                )
                self._phases = initial_phase_map()
                self._metrics = EMPTY_METRICS
                self._events_log = []
                self._last_checkpoint = {}
                self._dirty["session"] = True
                self._dirty["phase"]   = True
                self._dirty["metrics"] = True

            elif et == ScanEventType.PHASE_STARTED:
                phase_raw = payload.get("phase", "")
                canon     = canonical_phase(phase_raw)
                if canon in self._phases:
                    old = self._phases[canon]
                    self._phases[canon] = PhaseProjection(
                        phase_name=old.phase_name,
                        display_label=old.display_label,
                        status="running",
                        finalized=old.finalized,
                        integrity_ok=old.integrity_ok,
                        rows_written=old.rows_written,
                        duration_ms=old.duration_ms,
                        checkpoint_cursor=old.checkpoint_cursor,
                        is_reused=old.is_reused,
                        resume_outcome=old.resume_outcome,
                        failure_reason=old.failure_reason,
                    )
                # Update session current_phase immediately
                self._session = build_session_from_event(
                    session_id=sid,
                    status="running",
                    phase=canon,
                    phase_status="running",
                    resume_policy=self._session.resume_policy,
                    resume_reason=self._session.resume_reason,
                    engine_health=self._session.engine_health,
                    warnings_count=self._session.warnings_count,
                    config_hash=self._session.config_hash,
                    schema_version=self._session.schema_version,
                    scan_root=self._session.scan_root,
                )
                self._dirty["phase"]   = True
                self._dirty["session"] = True
                ts = time.strftime("%H:%M:%S")
                desc = payload.get("description", phase_raw)
                self._events_log.insert(0, f"[{ts}] Phase started: {desc or canon}")
                self._dirty["events_log"] = True

            elif et == ScanEventType.PHASE_COMPLETED:
                phase_raw = payload.get("phase", "")
                canon = canonical_phase(phase_raw)
                if canon in self._phases:
                    old = self._phases[canon]
                    self._phases[canon] = PhaseProjection(
                        phase_name=old.phase_name,
                        display_label=old.display_label,
                        status="completed",
                        finalized=True,
                        integrity_ok=True,
                        rows_written=payload.get("completed_units", old.rows_written),
                        duration_ms=old.duration_ms,
                        checkpoint_cursor=old.checkpoint_cursor,
                        is_reused=old.is_reused,
                        resume_outcome=old.resume_outcome,
                        failure_reason="",
                    )
                self._dirty["phase"] = True
                ts = time.strftime("%H:%M:%S")
                self._events_log.insert(0, f"[{ts}] Phase completed: {canon}")
                self._dirty["events_log"] = True

            elif et == ScanEventType.SCAN_PROGRESS:
                # Rebuild metrics from progress dict (with ETA estimate when engine doesn't provide)
                self._metrics = self._metrics_from_dict(payload)
                self._dirty["metrics"] = True
                # Update session.current_phase so StatusRibbon shows correct phase
                phase_raw = payload.get("phase", "")
                if phase_raw and self._session.status == "running":
                    canon = canonical_phase(phase_raw)
                    self._session = build_session_from_event(
                        session_id=sid,
                        status="running",
                        phase=canon,
                        phase_status="running",
                        resume_policy=self._session.resume_policy,
                        resume_reason=self._session.resume_reason,
                        engine_health=self._session.engine_health,
                        warnings_count=self._session.warnings_count,
                        config_hash=self._session.config_hash,
                        schema_version=self._session.schema_version,
                        scan_root=self._session.scan_root,
                    )
                    self._dirty["session"] = True
                # Update phase rows
                if phase_raw:
                    canon = canonical_phase(phase_raw)
                    if canon in self._phases:
                        old = self._phases[canon]
                        phase_completed = payload.get("phase_completed_units", payload.get("files_found", old.rows_written))
                        self._phases[canon] = PhaseProjection(
                            phase_name=old.phase_name,
                            display_label=old.display_label,
                            status="running",
                            finalized=old.finalized,
                            integrity_ok=old.integrity_ok,
                            rows_written=phase_completed,
                            duration_ms=old.duration_ms,
                            checkpoint_cursor=old.checkpoint_cursor,
                            is_reused=old.is_reused,
                            resume_outcome=old.resume_outcome,
                            failure_reason=old.failure_reason,
                        )
                        self._dirty["phase"] = True

            elif et == ScanEventType.RESUME_VALIDATED:
                compat = build_compat_from_event_payload(payload)
                self._compat = compat
                outcome  = payload.get("outcome", "safe_resume")
                reason   = payload.get("reason", "")
                self._session = build_session_from_event(
                    session_id=sid,
                    status="running",
                    phase=payload.get("first_phase", self._session.current_phase),
                    phase_status="running",
                    resume_policy=self._map_outcome_to_policy(outcome),
                    resume_reason=reason,
                    engine_health=self._session.engine_health,
                    warnings_count=self._session.warnings_count,
                    config_hash=payload.get("config_hash", self._session.config_hash),
                    schema_version=payload.get("schema_version", self._session.schema_version),
                    scan_root=self._session.scan_root,
                )
                # Mark reused phases and merge time_saved for Work Saved panel
                reused = payload.get("reused_phases") or []
                for pname, ph in self._phases.items():
                    if pname in reused:
                        self._phases[pname] = PhaseProjection(
                            phase_name=ph.phase_name,
                            display_label=ph.display_label,
                            status="completed",  # Reused = completed in prior run
                            finalized=True,
                            integrity_ok=ph.integrity_ok,
                            rows_written=ph.rows_written,
                            duration_ms=ph.duration_ms,
                            checkpoint_cursor=ph.checkpoint_cursor,
                            is_reused=True,
                            resume_outcome=ph.resume_outcome,
                            failure_reason=ph.failure_reason,
                        )
                time_saved = payload.get("time_saved_estimate") or 0.0
                if time_saved > 0:
                    self._metrics = merge_metrics(self._metrics, time_saved_estimate=time_saved)
                    self._dirty["metrics"] = True
                self._dirty["phase"]        = True
                self._dirty["compatibility"] = True
                self._dirty["session"]       = True
                ts = time.strftime("%H:%M:%S")
                self._events_log.insert(0,
                    f"[{ts}] Resume validated: {outcome} — {reason[:60]}")
                self._dirty["events_log"] = True

            elif et == ScanEventType.RESUME_REJECTED:
                compat = build_compat_from_event_payload(
                    {**payload, "outcome": "restart_required"})
                self._compat = compat
                reason = payload.get("reason", "")
                self._session = build_session_from_event(
                    session_id=sid,
                    status="running",
                    phase=self._session.current_phase,
                    resume_policy="restart_required",
                    resume_reason=reason,
                    engine_health="Warning",
                    warnings_count=self._session.warnings_count + 1,
                    config_hash=self._session.config_hash,
                    schema_version=self._session.schema_version,
                    scan_root=self._session.scan_root,
                )
                self._dirty["compatibility"] = True
                self._dirty["session"]       = True
                ts = time.strftime("%H:%M:%S")
                self._events_log.insert(0,
                    f"[{ts}] Resume rejected: restart required — {reason[:60]}")
                self._dirty["events_log"] = True

            elif et in (ScanEventType.SESSION_COMPLETED, ScanEventType.SCAN_COMPLETED):
                result = payload.get("result", {}) or {}
                benchmark = result.get("benchmark_report", {}) or {}
                compat = result.get("incremental_discovery_report", {}) or {}
                self._metrics = merge_metrics(
                    self._metrics,
                    files_discovered_total=int(
                        benchmark.get("files_discovered_total") or
                        result.get("files_scanned") or
                        self._metrics.files_discovered_total or 0
                    ),
                    files_discovered_fresh=int(benchmark.get("files_discovered_fresh", self._metrics.files_discovered_fresh) or 0),
                    files_reused_from_prior_inventory=int(
                        benchmark.get("files_reused_from_prior_inventory", self._metrics.files_reused_from_prior_inventory) or 0
                    ),
                    dirs_scanned=int(benchmark.get("dirs_scanned", self._metrics.dirs_scanned) or 0),
                    dirs_reused=int(benchmark.get("dirs_reused", self._metrics.dirs_reused) or 0),
                    duplicate_groups_live=int(
                        len(result.get("duplicate_groups", [])) or
                        self._metrics.duplicate_groups_live or 0
                    ),
                    result_duplicate_files=int(result.get("total_duplicates", 0) or 0),
                    result_duplicate_groups=int(len(result.get("duplicate_groups", [])) or 0),
                    result_rows_assembled=int(result.get("total_duplicates", 0) or 0),
                    result_reclaimable_bytes=int(result.get("total_reclaimable_bytes", 0) or 0),
                    result_files_scanned=int(result.get("files_scanned", 0) or 0),
                    result_verification_level=str(result.get("verification_level", "") or ""),
                    results_ready=True,
                    elapsed_s=self._elapsed_from_session_completed(result, benchmark, self._metrics.elapsed_s),
                    discovery_reuse_mode=str(benchmark.get("discovery_reuse_mode", "none")),
                    dirs_skipped_via_manifest=int(benchmark.get("dirs_skipped_via_manifest", 0) or 0),
                    prior_session_compatible=bool(benchmark.get("prior_session_compatible", False)),
                    prior_session_rejected_reason=str(
                        benchmark.get(
                            "prior_session_rejected_reason",
                            compat.get("reason", "none"),
                        )
                    ),
                    time_saved_estimate=float(benchmark.get("time_saved_estimate_s", 0.0) or 0.0),
                    hash_cache_hits=int(benchmark.get("hash_cache_hits", 0) or 0),
                    hash_cache_misses=int(benchmark.get("hash_cache_misses", 0) or 0),
                )
                self._session = build_session_from_event(
                    session_id=sid,
                    status="completed",
                    phase="result_assembly",
                    phase_status="completed",
                    resume_policy=self._session.resume_policy,
                    resume_reason=self._session.resume_reason,
                    engine_health="Healthy",
                    warnings_count=self._session.warnings_count,
                    config_hash=self._session.config_hash,
                    schema_version=self._session.schema_version,
                    scan_root=self._session.scan_root,
                )
                # Mark all running phases as completed
                for pname, ph in self._phases.items():
                    if ph.status == "running":
                        self._phases[pname] = PhaseProjection(
                            phase_name=ph.phase_name,
                            display_label=ph.display_label,
                            status="completed",
                            finalized=True,
                            integrity_ok=True,
                            rows_written=ph.rows_written,
                            duration_ms=ph.duration_ms,
                            checkpoint_cursor=ph.checkpoint_cursor,
                            is_reused=ph.is_reused,
                            resume_outcome=ph.resume_outcome,
                            failure_reason="",
                        )
                self._dirty["session"]  = True
                self._dirty["phase"]    = True
                self._dirty["metrics"]  = True
                self._dirty["terminal"] = True
                ts = time.strftime("%H:%M:%S")
                self._events_log.insert(0, f"[{ts}] Scan completed")
                self._dirty["events_log"] = True

            elif et in (ScanEventType.SESSION_CANCELLED, ScanEventType.SCAN_CANCELLED):
                self._session = build_session_from_event(
                    session_id=sid,
                    status="cancelled",
                    phase=self._session.current_phase,
                    resume_policy=self._session.resume_policy,
                    engine_health=self._session.engine_health,
                    config_hash=self._session.config_hash,
                    schema_version=self._session.schema_version,
                    scan_root=self._session.scan_root,
                )
                self._dirty["session"]  = True
                self._dirty["terminal"] = True

            elif et in (ScanEventType.SESSION_FAILED, ScanEventType.SCAN_ERROR):
                err = payload.get("error", "")
                self._session = build_session_from_event(
                    session_id=sid,
                    status="failed",
                    phase=self._session.current_phase,
                    engine_health="Degraded",
                    warnings_count=self._session.warnings_count + 1,
                    config_hash=self._session.config_hash,
                    schema_version=self._session.schema_version,
                    scan_root=self._session.scan_root,
                )
                self._dirty["session"]  = True
                self._dirty["terminal"] = True
                ts = time.strftime("%H:%M:%S")
                self._events_log.insert(0, f"[{ts}] ERROR: {err[:80]}")
                self._dirty["events_log"] = True

            elif et == ScanEventType.PHASE_CHECKPOINTED:
                # Throttle: only log when files_found jumped by 1000+ or 5s since last
                phase_raw = payload.get("phase", "")
                canon = canonical_phase(phase_raw)
                files = payload.get("files_found", 0)
                now = time.monotonic()
                last = getattr(self, "_last_checkpoint", {})
                last_files = last.get(canon, -1)
                last_ts = last.get(f"{canon}_ts", 0.0)
                if (files - last_files >= 1000 or (now - last_ts) >= 5.0) and canon in self._phases:
                    self._last_checkpoint = {canon: files, f"{canon}_ts": now}
                    ts = time.strftime("%H:%M:%S")
                    self._events_log.insert(0, f"[{ts}] Checkpointed: {canon} ({files:,} files)")
                    self._dirty["events_log"] = True

    # ------------------------------------------------------------------
    # Throttled Tk poll loop
    # ------------------------------------------------------------------

    def _schedule_poll(self) -> None:
        if not self._alive:
            return
        try:
            self._root.after(POLL_MS, self._poll)
        except Exception as e:
            if self._alive:
                _log.warning("Hub poll schedule failed (root may be destroyed): %s", e)
                try:
                    from ...infrastructure.diagnostics import get_diagnostics_recorder, CATEGORY_HUB_DELIVERY
                    get_diagnostics_recorder().record(CATEGORY_HUB_DELIVERY, "Poll schedule failed", str(e))
                except Exception:
                    pass

    def _poll(self) -> None:
        """Called on Tk main thread every POLL_MS ms."""
        if not self._alive:
            return
        now = time.monotonic()
        try:
            self._flush(now)
        except Exception as e:
            _log.warning("Hub flush failed: %s", e)
            try:
                from ...infrastructure.diagnostics import get_diagnostics_recorder, CATEGORY_HUB_DELIVERY
                get_diagnostics_recorder().record(CATEGORY_HUB_DELIVERY, "Flush failed", str(e))
            except Exception:
                pass
        self._schedule_poll()

    def _flush(self, now: float) -> None:
        """Deliver dirty projections to UI subscribers if throttle allows."""
        deliveries: Dict[str, Any] = {}

        with self._lock:
            for ptype, throttle in THROTTLE_MS.items():
                if not self._dirty.get(ptype):
                    continue
                elapsed_ms = (now - self._last_delivered.get(ptype, 0.0)) * 1000
                if elapsed_ms >= throttle:
                    self._dirty[ptype] = False
                    self._last_delivered[ptype] = now
                    deliveries[ptype] = self._snapshot(ptype)

        for ptype, snapshot in deliveries.items():
            with self._sub_lock:
                callbacks = self._subscribers.get(ptype, [])[:]
            for cb in callbacks:
                try:
                    cb(snapshot)
                except Exception as e:
                    _log.warning("Hub delivery callback failed for %s: %s", ptype, e)
                    try:
                        from ...infrastructure.diagnostics import get_diagnostics_recorder, CATEGORY_HUB_DELIVERY
                        get_diagnostics_recorder().record(
                            CATEGORY_HUB_DELIVERY, f"Callback failed ({ptype})", str(e)
                        )
                    except Exception:
                        pass

    def _snapshot(self, ptype: str) -> Any:
        """Return the current snapshot for a projection type (called under lock)."""
        if ptype == "session" or ptype == "terminal":
            return self._session
        if ptype == "phase":
            return dict(self._phases)
        if ptype == "metrics":
            return self._metrics
        if ptype == "compatibility":
            return self._compat
        if ptype == "deletion":
            return self._deletion
        if ptype == "events_log":
            return list(self._events_log[:200])
        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_root(payload: dict) -> str:
        roots = payload.get("roots", [])
        if roots:
            from pathlib import Path
            return Path(roots[0]).name if roots[0] else ""
        config = payload.get("config", {})
        if isinstance(config, dict):
            r = config.get("roots", [])
            if r:
                from pathlib import Path
                return Path(r[0]).name if r[0] else ""
        return ""

    @staticmethod
    def _elapsed_from_session_completed(
        result: dict,
        benchmark: dict,
        prior_elapsed: float,
    ) -> float:
        """
        Derive a truthful total elapsed seconds value for terminal metrics.

        Preference order:
        1. benchmark['total_elapsed_ms'] if present
        2. prior_elapsed (last live elapsed_s from progress stream)
        """
        try:
            total_ms = benchmark.get("total_elapsed_ms")
            if isinstance(total_ms, (int, float)) and total_ms > 0:
                return float(total_ms) / 1000.0
        except Exception:
            pass
        return float(prior_elapsed or 0.0)

    @staticmethod
    def _map_outcome_to_policy(outcome: str) -> str:
        return {
            "safe_resume":              "safe",
            "rebuild_current_phase":    "rebuild_phase",
            "restart_required":         "restart_required",
        }.get(outcome, "none")

    @staticmethod
    def _metrics_from_dict(d: dict) -> MetricsProjection:
        bps = d.get("bytes_per_second") or 0.0
        fps = d.get("files_per_second") or 0.0
        eta = d.get("estimated_remaining_seconds")
        elapsed = d.get("elapsed_seconds") or 0.0
        files_found = d.get("files_found", 0)
        files_total = d.get("files_total")
        # Estimate ETA when engine doesn't provide it: remaining files / rate
        if eta is None and files_total and files_total > 0 and fps and fps > 0:
            remaining = max(0, files_total - files_found)
            if remaining > 0:
                eta = remaining / fps
                eta_conf = "low"
        eta_conf = "unknown" if eta is None else (
            "medium" if elapsed > 30 else "low" if eta is not None else "unknown"
        )
        if eta is not None and elapsed > 120:
            eta_conf = "high"

        return MetricsProjection(
            files_discovered_total=d.get("files_found", 0),
            files_discovered_fresh=d.get("files_found", 0),
            files_reused_from_prior_inventory=0,
            dirs_scanned=int(d.get("dirs_scanned", 0) or 0),
            dirs_reused=int(d.get("dirs_reused", 0) or 0),
            elapsed_s=elapsed,
            duplicate_groups_live=d.get("groups_found", 0),
            current_phase_name=d.get("phase", "") or "",
            current_phase_progress=(
                f"{int(d.get('phase_completed_units', d.get('files_found', 0)) or 0):,} / "
                f"{int(d['phase_total_units']):,}" if d.get("phase_total_units") is not None
                else f"{int(d.get('phase_completed_units', d.get('files_found', 0)) or 0):,} / —"
            ),
            current_phase_rows_processed=int(d.get("phase_completed_units", d.get("files_found", 0)) or 0),
            current_phase_total_units=(
                int(d["phase_total_units"]) if d.get("phase_total_units") is not None else None
            ),
            current_phase_elapsed_s=float(d.get("phase_elapsed_s", elapsed) or 0.0),
            current_phase_started_at=d.get("phase_started_at"),
            current_phase_last_updated_at=d.get("phase_last_updated_at"),
            current_file=d.get("current_file", "") or "",
            result_duplicate_files=0,
            result_duplicate_groups=0,
            result_rows_assembled=0,
            result_reclaimable_bytes=0,
            result_files_scanned=0,
            result_verification_level="",
            results_ready=False,
            discovery_reuse_mode="none",
            dirs_skipped_via_manifest=0,
            prior_session_compatible=False,
            prior_session_rejected_reason="none",
            time_saved_estimate=0.0,
            disk_read_bps=bps,
            rows_per_sec=fps,
            cache_hit_rate=0.0,
            hash_cache_hits=0,
            hash_cache_misses=0,
            eta_seconds=eta,
            eta_confidence=eta_conf,
        )
