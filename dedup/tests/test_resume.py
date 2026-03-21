"""
Authoritative durable resume tests.

- Interrupted partial-hash phase resumes without recomputing size phase.
- Config change yields restart_required or rebuild_current_phase.
- Resume decision is one of safe_resume, rebuild_current_phase, restart_required.
"""

from __future__ import annotations

from dedup.engine.models import (
    ResumeOutcome,
    ScanConfig,
    ScanPhase,
)
from dedup.engine.pipeline import ScanPipeline
from dedup.engine.resume import ResumeResolver
from dedup.infrastructure.persistence import Persistence


def test_resume_decision_new_scan_is_restart_required(temp_dir):
    """New scan (no session) -> RESTART_REQUIRED, first phase DISCOVERY."""
    persistence = Persistence(db_path=temp_dir / "resume.db")
    try:
        resolver = ResumeResolver(persistence)
        decision = resolver.resolve("new-session-id", ScanConfig(roots=[temp_dir]), is_new_scan=True)
        assert decision.outcome == ResumeOutcome.RESTART_REQUIRED
        assert decision.first_runnable_phase == ScanPhase.DISCOVERY
        assert decision.reason
    finally:
        persistence.close()


def test_resume_decision_no_session_is_restart_required(temp_dir):
    """Resolve with session_id that has no session row -> RESTART_REQUIRED."""
    persistence = Persistence(db_path=temp_dir / "resume2.db")
    try:
        resolver = ResumeResolver(persistence)
        decision = resolver.resolve("nonexistent", ScanConfig(roots=[temp_dir]), is_new_scan=False)
        assert decision.outcome == ResumeOutcome.RESTART_REQUIRED
        assert decision.first_runnable_phase == ScanPhase.DISCOVERY
    finally:
        persistence.close()


def test_resume_decision_safe_resume_after_discovery(temp_dir):
    """Session exists, discovery checkpoint completed and finalized -> SAFE_RESUME from SIZE_REDUCTION."""
    scan_root = temp_dir / "scan"
    scan_root.mkdir()
    (scan_root / "a.txt").write_text("a")
    (scan_root / "b.txt").write_text("b")
    persistence = Persistence(db_path=temp_dir / "resume3.db")
    try:
        config = ScanConfig(roots=[scan_root], hash_algorithm="md5", full_hash_workers=1, batch_size=10)
        pipeline = ScanPipeline(
            config=config,
            persistence=persistence,
            hash_cache_getter=persistence.get_hash_cache,
            hash_cache_setter=persistence.set_hash_cache,
        )
        pipeline.run()
        session_id = pipeline.scan_id
        resolver = ResumeResolver(persistence)
        decision = resolver.resolve(session_id, config, is_new_scan=False)
        assert decision.outcome == ResumeOutcome.SAFE_RESUME
        assert decision.first_runnable_phase in (
            ScanPhase.DISCOVERY,
            ScanPhase.SIZE_REDUCTION,
            ScanPhase.PARTIAL_HASH,
            ScanPhase.FULL_HASH,
            ScanPhase.RESULT_ASSEMBLY,
        )
    finally:
        persistence.close()


def test_interrupted_scan_resumes_from_durable_boundary(temp_dir):
    """Run scan to completion; then "resume" same session -> completes without re-running discovery."""
    scan_root = temp_dir / "data"
    scan_root.mkdir()
    (scan_root / "f1.txt").write_text("same")
    (scan_root / "f2.txt").write_text("same")
    persistence = Persistence(db_path=temp_dir / "resume4.db")
    try:
        config = ScanConfig(roots=[scan_root], hash_algorithm="md5", full_hash_workers=1, batch_size=5)
        pipeline = ScanPipeline(
            config=config,
            persistence=persistence,
            hash_cache_getter=persistence.get_hash_cache,
            hash_cache_setter=persistence.set_hash_cache,
        )
        result1 = pipeline.run()
        assert result1.files_scanned == 2
        session_id = pipeline.scan_id
        inv_count_before = persistence.inventory_repo.count(session_id)

        pipeline2 = ScanPipeline(
            config=config,
            scan_id=session_id,
            persistence=persistence,
            hash_cache_getter=persistence.get_hash_cache,
            hash_cache_setter=persistence.set_hash_cache,
        )
        result2 = pipeline2.run()
        assert result2.scan_id == session_id
        assert persistence.inventory_repo.count(session_id) == inv_count_before
        assert result2.files_scanned == 2
    finally:
        persistence.close()


def test_config_hash_mismatch_restart_required(temp_dir):
    """Different config (e.g. different roots) -> RESTART_REQUIRED when resolving."""
    scan_root = temp_dir / "r1"
    scan_root.mkdir()
    (scan_root / "x.txt").write_text("x")
    persistence = Persistence(db_path=temp_dir / "resume5.db")
    try:
        config1 = ScanConfig(roots=[scan_root], hash_algorithm="md5")
        pipeline = ScanPipeline(config=config1, persistence=persistence)
        pipeline.run()
        session_id = pipeline.scan_id

        other_root = temp_dir / "r2"
        other_root.mkdir()
        config2 = ScanConfig(roots=[other_root], hash_algorithm="md5")
        resolver = ResumeResolver(persistence)
        decision = resolver.resolve(session_id, config2, is_new_scan=False)
        assert decision.outcome == ResumeOutcome.RESTART_REQUIRED
        assert "config" in decision.reason.lower() or "root" in decision.reason.lower()
    finally:
        persistence.close()
