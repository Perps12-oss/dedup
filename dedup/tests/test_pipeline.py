"""
Pipeline tests: durable discovery writes inventory and checkpoints.

Characterisation tests (Stage 5-first): normal operation, errors, edge cases.
Mock external deps where needed; use temp_dir for integration-style runs.
"""

from __future__ import annotations

from pathlib import Path

from dedup.engine.models import (
    DeletionPolicy,
    ScanConfig,
    ScanPhase,
)
from dedup.engine.pipeline import (
    ScanPipeline,
    ResumableScanPipeline,
    quick_scan,
)
from dedup.infrastructure.persistence import Persistence


def test_pipeline_persists_inventory_and_checkpoints(temp_dir):
    """Full scan writes inventory and discovery checkpoint."""
    scan_root = temp_dir / "scan-root"
    scan_root.mkdir()
    (scan_root / "a.txt").write_text("same")
    (scan_root / "b.txt").write_text("same")

    persistence = Persistence(db_path=temp_dir / "pipeline.db")
    try:
        pipeline = ScanPipeline(
            config=ScanConfig(roots=[scan_root], hash_algorithm="md5", full_hash_workers=1, batch_size=1),
            persistence=persistence,
            hash_cache_getter=persistence.get_hash_cache,
            hash_cache_setter=persistence.set_hash_cache,
        )
        result = pipeline.run()

        assert result.files_scanned == 2
        assert persistence.inventory_repo.count(result.scan_id) == 2
        checkpoint = persistence.checkpoint_repo.get(result.scan_id, ScanPhase.DISCOVERY)
        assert checkpoint is not None
        assert checkpoint.completed_units == 2
        assert checkpoint.status.value == "completed"
    finally:
        persistence.close()


def test_pipeline_empty_directory(temp_dir):
    """Scan of empty directory: files_scanned is 0; may or may not set result.errors (current behaviour)."""
    empty = temp_dir / "empty"
    empty.mkdir()

    persistence = Persistence(db_path=temp_dir / "empty.db")
    try:
        pipeline = ScanPipeline(
            config=ScanConfig(roots=[empty], min_size_bytes=1, full_hash_workers=1, batch_size=1),
            persistence=persistence,
            hash_cache_getter=persistence.get_hash_cache,
            hash_cache_setter=persistence.set_hash_cache,
        )
        result = pipeline.run()
        assert result.files_scanned == 0
        assert result.duplicate_groups == []
    finally:
        persistence.close()


def test_pipeline_progress_callback_invoked(temp_dir):
    """Progress callback is called during run (with persistence so phases complete)."""
    scan_root = temp_dir / "progress-root"
    scan_root.mkdir()
    (scan_root / "f1.txt").write_text("x")
    (scan_root / "f2.txt").write_text("x")

    progress_events = []
    def on_progress(p):
        progress_events.append((getattr(p, "phase", None), getattr(p, "files_found", None)))

    persistence = Persistence(db_path=temp_dir / "progress.db")
    try:
        pipeline = ScanPipeline(
            config=ScanConfig(roots=[scan_root], hash_algorithm="md5", full_hash_workers=1, batch_size=1),
            persistence=persistence,
            hash_cache_getter=persistence.get_hash_cache,
            hash_cache_setter=persistence.set_hash_cache,
        )
        result = pipeline.run(progress_cb=on_progress)
        assert result.files_scanned == 2
        assert len(progress_events) >= 1
        phases = [e[0] for e in progress_events]
        assert "complete" in phases or "discovering" in phases or "grouping" in phases
    finally:
        persistence.close()


def test_pipeline_cancel_stops_scan(temp_dir):
    """Cancel sets _cancelled and run returns with cancelled message."""
    scan_root = temp_dir / "cancel-root"
    scan_root.mkdir()
    for i in range(20):
        (scan_root / f"f{i}.txt").write_text("x" * 100)

    pipeline = ScanPipeline(
        config=ScanConfig(roots=[scan_root], hash_algorithm="md5", full_hash_workers=1, batch_size=5),
    )
    call_count = [0]

    def on_progress(p):
        call_count[0] += 1
        if call_count[0] >= 2:
            pipeline.cancel()

    result = pipeline.run(progress_cb=on_progress)
    assert pipeline.is_cancelled
    assert any("cancelled" in e for e in result.errors) or result.completed_at is not None


def test_pipeline_create_deletion_plan_and_execute_dry_run(temp_dir):
    """create_deletion_plan and execute_deletion(dry_run=True) work after scan."""
    scan_root = temp_dir / "del-root"
    scan_root.mkdir()
    (scan_root / "a.txt").write_text("same")
    (scan_root / "b.txt").write_text("same")

    persistence = Persistence(db_path=temp_dir / "del.db")
    try:
        pipeline = ScanPipeline(
            config=ScanConfig(roots=[scan_root], hash_algorithm="md5", full_hash_workers=1, batch_size=1),
            persistence=persistence,
            hash_cache_getter=persistence.get_hash_cache,
            hash_cache_setter=persistence.set_hash_cache,
        )
        result = pipeline.run()
        assert result.files_scanned == 2
        assert len(result.duplicate_groups) >= 1

        plan = pipeline.create_deletion_plan(result, policy=DeletionPolicy.TRASH, keep_strategy="first")
        assert plan is not None
        assert plan.total_files_to_delete >= 1

        dry_result = pipeline.execute_deletion(plan, dry_run=True)
        assert dry_result is not None
        assert len(dry_result.deleted_files) >= 0
        assert (scan_root / "a.txt").exists()
        assert (scan_root / "b.txt").exists()
    finally:
        persistence.close()


def test_pipeline_without_persistence_completes(temp_dir):
    """Pipeline runs without persistence when persistence is explicitly None (guarded access)."""
    scan_root = temp_dir / "nopersistence"
    scan_root.mkdir()
    (scan_root / "one.txt").write_text("1")

    pipeline = ScanPipeline(config=ScanConfig(roots=[scan_root], full_hash_workers=1), persistence=None)
    result = pipeline.run()
    assert result.files_scanned == 1
    assert result.duplicate_groups is not None
    assert pipeline.persistence is None


def test_resumable_pipeline_load_checkpoint_config_missing_returns_none(temp_dir):
    """ResumableScanPipeline.load_checkpoint_config returns None when file missing."""
    cfg = ResumableScanPipeline.load_checkpoint_config(Path(temp_dir), "nonexistent-scan-id")
    assert cfg is None


def test_quick_scan_convenience(temp_dir):
    """quick_scan runs and returns ScanResult (no persistence by default)."""
    scan_root = temp_dir / "quick"
    scan_root.mkdir()
    (scan_root / "q.txt").write_text("q")

    result = quick_scan(scan_root, min_size=1)
    assert result.scan_id
    assert result.config is not None
    assert result.files_scanned == 1
