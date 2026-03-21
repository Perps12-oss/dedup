from __future__ import annotations

from datetime import datetime

from dedup.engine.discovery import DiscoveryOptions, FileDiscovery
from dedup.engine.discovery_compat import (
    build_discovery_merge_report,
    discovery_config_hash,
    find_compatible_prior_session,
    root_fingerprint,
)
from dedup.engine.models import CheckpointInfo, FileMetadata, PhaseStatus, ScanConfig, ScanPhase
from dedup.engine.pipeline import ScanPipeline
from dedup.infrastructure.persistence import Persistence


def test_discovery_config_hash_changes_for_discovery_settings(temp_dir):
    base = ScanConfig(roots=[temp_dir], min_size_bytes=1, resolve_paths=False)
    same = ScanConfig(roots=[temp_dir], min_size_bytes=1, resolve_paths=False)
    changed = ScanConfig(roots=[temp_dir], min_size_bytes=2, resolve_paths=False)

    assert discovery_config_hash(base) == discovery_config_hash(same)
    assert discovery_config_hash(base) != discovery_config_hash(changed)


def test_find_compatible_prior_session_returns_completed_discovery(temp_dir):
    persistence = Persistence(db_path=temp_dir / "compat.db")
    try:
        config = ScanConfig(roots=[temp_dir], hash_algorithm="md5")
        session_id = "prior-1"
        persistence.shadow_write_session(
            session_id=session_id,
            config_json="{}",
            config_hash="full-cfg",
            root_fingerprint=root_fingerprint(config),
            discovery_config_hash=discovery_config_hash(config),
            status="completed",
            current_phase=ScanPhase.RESULT_ASSEMBLY.value,
        )
        persistence.checkpoint_repo.upsert(
            CheckpointInfo(
                session_id=session_id,
                phase_name=ScanPhase.DISCOVERY,
                completed_units=1,
                total_units=1,
                status=PhaseStatus.COMPLETED,
                updated_at=datetime.now(),
                metadata_json={
                    "schema_version": persistence.schema_version,
                    "is_finalized": True,
                    "config_hash": "full-cfg",
                },
            )
        )

        match, report = find_compatible_prior_session(persistence, config)
        assert match == session_id
        assert report.compatible is True
        assert report.reason == "compatible"
    finally:
        persistence.close()


def test_find_compatible_prior_session_rejects_schema_mismatch(temp_dir):
    persistence = Persistence(db_path=temp_dir / "compat-schema.db")
    try:
        config = ScanConfig(roots=[temp_dir], hash_algorithm="md5")
        session_id = "prior-schema"
        persistence.shadow_write_session(
            session_id=session_id,
            config_json="{}",
            config_hash="full-cfg",
            root_fingerprint=root_fingerprint(config),
            discovery_config_hash=discovery_config_hash(config),
            status="completed",
            current_phase=ScanPhase.RESULT_ASSEMBLY.value,
        )
        persistence.checkpoint_repo.upsert(
            CheckpointInfo(
                session_id=session_id,
                phase_name=ScanPhase.DISCOVERY,
                completed_units=1,
                total_units=1,
                status=PhaseStatus.COMPLETED,
                updated_at=datetime.now(),
                metadata_json={
                    "schema_version": persistence.schema_version + 1,
                    "is_finalized": True,
                    "config_hash": "full-cfg",
                },
            )
        )

        match, report = find_compatible_prior_session(persistence, config)
        assert match is None
        assert report.reason == "schema_version_mismatch"
    finally:
        persistence.close()


def test_build_discovery_merge_report_classifies_paths():
    current = [
        FileMetadata(path="/a", size=10, mtime_ns=1),
        FileMetadata(path="/b", size=20, mtime_ns=2),
        FileMetadata(path="/c", size=30, mtime_ns=3),
    ]
    prior = [
        FileMetadata(path="/a", size=10, mtime_ns=1),
        FileMetadata(path="/b", size=25, mtime_ns=2),
        FileMetadata(path="/d", size=40, mtime_ns=4),
    ]

    report = build_discovery_merge_report(current, prior, prior_session_id="prior")
    assert report.unchanged == 1
    assert report.changed == 1
    assert report.new == 1
    assert report.deleted == 1


def test_pipeline_full_walk_merge_reports_changed_new_deleted(temp_dir):
    root = temp_dir / "scan-root"
    root.mkdir()
    (root / "same.txt").write_text("same")
    (root / "change.txt").write_text("before")
    (root / "delete.txt").write_text("gone")

    persistence = Persistence(db_path=temp_dir / "merge.db")
    try:
        config = ScanConfig(roots=[root], hash_algorithm="md5", full_hash_workers=1, batch_size=2)
        first = ScanPipeline(config=config, persistence=persistence)
        first.run()

        (root / "change.txt").write_text("after")
        (root / "delete.txt").unlink()
        (root / "new.txt").write_text("new")

        second = ScanPipeline(config=config, persistence=persistence)
        result = second.run()
        report = result.incremental_discovery_report or {}
        assert report["unchanged"] == 1
        assert report["changed"] == 1
        assert report["new"] == 1
        assert report["deleted"] == 1
        assert persistence.inventory_repo.count(result.scan_id) == 3
    finally:
        persistence.close()


def test_pipeline_falls_back_when_discovery_config_changes(temp_dir):
    root = temp_dir / "cfg-root"
    root.mkdir()
    (root / "a.txt").write_text("a")

    persistence = Persistence(db_path=temp_dir / "cfg.db")
    try:
        base = ScanConfig(roots=[root], min_size_bytes=1, hash_algorithm="md5")
        ScanPipeline(config=base, persistence=persistence).run()

        changed = ScanConfig(roots=[root], min_size_bytes=10, hash_algorithm="md5")
        result = ScanPipeline(config=changed, persistence=persistence).run()
        report = result.incremental_discovery_report or {}
        assert report["reason"] == "discovery_config_hash_mismatch"
    finally:
        persistence.close()


def test_subtree_skip_reuses_prior_files_when_directory_mtime_matches(temp_dir):
    root = temp_dir / "root"
    root.mkdir()
    (root / "current.txt").write_text("current")
    root_mtime_ns = root.stat().st_mtime_ns

    discovery = FileDiscovery(
        DiscoveryOptions(roots=[root], min_size_bytes=1, max_workers=1),
        prior_session_id="prior",
        prior_dir_mtimes={str(root): root_mtime_ns},
        get_prior_files_under_dir=lambda _: iter([FileMetadata(path="reused.txt", size=7, mtime_ns=1)]),
        dir_mtimes_sink={},
    )

    files = list(discovery.discover())
    assert [file.path for file in files] == ["reused.txt"]


def test_subtree_skip_falls_back_on_missing_manifest_row(temp_dir):
    root = temp_dir / "root"
    root.mkdir()
    (root / "current.txt").write_text("current")

    discovery = FileDiscovery(
        DiscoveryOptions(roots=[root], min_size_bytes=1, max_workers=1),
        prior_session_id="prior",
        prior_dir_mtimes={},
        get_prior_files_under_dir=lambda _: iter([FileMetadata(path="reused.txt", size=7, mtime_ns=1)]),
        dir_mtimes_sink={},
    )

    files = list(discovery.discover())
    assert any(file.path.endswith("current.txt") for file in files)


def test_directory_manifest_persisted_for_completed_scan(temp_dir):
    root = temp_dir / "manifest-root"
    child = root / "child"
    child.mkdir(parents=True)
    (child / "a.txt").write_text("a")

    persistence = Persistence(db_path=temp_dir / "manifest.db")
    try:
        config = ScanConfig(roots=[root], hash_algorithm="md5", full_hash_workers=1)
        pipeline = ScanPipeline(config=config, persistence=persistence)
        pipeline.run()

        dir_mtimes = persistence.discovery_dir_repo.get_dir_mtimes(pipeline.scan_id)
        assert str(root) in dir_mtimes
        assert str(child) in dir_mtimes
    finally:
        persistence.close()
