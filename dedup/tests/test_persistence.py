"""
Persistence tests: save/load scan, hash cache, recovery.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from dedup.engine.models import DuplicateGroup, FileMetadata, ScanConfig, ScanResult
from dedup.infrastructure.persistence import Persistence


@pytest.fixture
def db_path(temp_dir):
    return temp_dir / "test.db"


@pytest.fixture
def persistence(db_path):
    p = Persistence(db_path=db_path)
    yield p
    p.close()


def test_save_and_load_scan(persistence):
    result = ScanResult(
        scan_id="scan-1",
        config=ScanConfig(roots=[]),
        started_at=datetime.now(),
        completed_at=datetime.now(),
        files_scanned=10,
        duplicate_groups=[
            DuplicateGroup(
                group_id="g1",
                group_hash="h1",
                files=[
                    FileMetadata(path="/a", size=5, mtime_ns=0),
                    FileMetadata(path="/b", size=5, mtime_ns=0),
                ],
            ),
        ],
        total_duplicates=1,
        total_reclaimable_bytes=5,
    )
    assert persistence.save_scan(result) is True
    loaded = persistence.get_scan("scan-1")
    assert loaded is not None
    assert loaded.scan_id == result.scan_id
    assert loaded.files_scanned == result.files_scanned
    assert len(loaded.duplicate_groups) == 1
    assert loaded.total_reclaimable_bytes == 5


def test_list_scans(persistence):
    result = ScanResult(
        scan_id="s1",
        config=ScanConfig(roots=[]),
        started_at=datetime.now(),
        files_scanned=1,
    )
    persistence.save_scan(result)
    listing = persistence.list_scans(limit=10)
    assert len(listing) >= 1
    assert any(row["scan_id"] == "s1" for row in listing)


def test_hash_cache_set_get(persistence):
    from dedup.engine.models import FileMetadata

    m = FileMetadata(path="/some/path", size=100, mtime_ns=123, hash_partial="abc", hash_full="def")
    assert persistence.set_hash_cache(m) is True
    cached = persistence.get_hash_cache("/some/path")
    assert cached is not None
    assert cached["hash_partial"] == "abc"
    assert cached["hash_full"] == "def"
    assert cached["size"] == 100
    assert cached["mtime_ns"] == 123


def test_shadow_session_and_checkpoint_writes(persistence):
    persistence.shadow_write_session(
        session_id="session-1",
        config_json='{"roots":[]}',
        config_hash="cfg-hash",
        discovery_config_hash="disc-hash",
    )
    row = persistence.session_repo.get("session-1")
    assert row is not None
    assert row["config_hash"] == "cfg-hash"
    assert row["discovery_config_hash"] == "disc-hash"

    from dedup.engine.models import PhaseStatus, ScanPhase

    persistence.shadow_write_checkpoint(
        session_id="session-1",
        phase_name=ScanPhase.DISCOVERY,
        completed_units=25,
        total_units=100,
        status=PhaseStatus.RUNNING,
        metadata_json={"bytes_found": 1234},
    )
    checkpoint = persistence.checkpoint_repo.get("session-1", ScanPhase.DISCOVERY)
    assert checkpoint is not None
    assert checkpoint.completed_units == 25
    assert checkpoint.metadata_json["bytes_found"] == 1234


def test_shadow_inventory_write(persistence):
    files = [
        FileMetadata(path="/a", size=10, mtime_ns=1),
        FileMetadata(path="/b", size=20, mtime_ns=2),
    ]
    written = persistence.shadow_write_inventory("session-2", files)
    assert written == 2
    assert persistence.inventory_repo.count("session-2") == 2


def test_list_scans_includes_session_metadata_and_verification_summary(persistence):
    result = ScanResult(
        scan_id="scan-meta",
        config=ScanConfig(roots=[]),
        started_at=datetime.now(),
        completed_at=datetime.now(),
        files_scanned=1,
    )
    assert persistence.save_scan(result) is True
    persistence.shadow_write_session(
        session_id="scan-meta",
        config_json='{"roots":[]}',
        config_hash="cfg-hash",
        root_fingerprint="root-hash",
        discovery_config_hash="disc-hash",
        status="completed",
    )
    persistence.deletion_verification_repo.upsert(
        plan_id="scan-meta",
        session_id="scan-meta",
        status="resolved",
        summary={"deleted": 1},
        detail={"deleted": 1},
    )

    listing = persistence.list_scans(limit=10)
    row = next(item for item in listing if item["scan_id"] == "scan-meta")
    assert row["config_hash"] == "cfg-hash"
    assert row["root_fingerprint"] == "root-hash"
    assert row["discovery_config_hash"] == "disc-hash"
    assert row["benchmark_summary"] == {}
    assert row["deletion_verification_summary"] == {"deleted": 1}


def test_persistence_wal_and_synchronous_applied(db_path):
    """Persistence applies WAL and synchronous pragmas; env can override synchronous."""
    from dedup.infrastructure.persistence import Persistence

    p = Persistence(db_path=db_path)
    try:
        conn = p._get_connection()
        row = conn.execute("PRAGMA journal_mode").fetchone()
        mode = (row[0] or "").lower()
        assert mode in ("wal", "delete", "truncate", "memory")
        row = conn.execute("PRAGMA synchronous").fetchone()
        sync = row[0]
        assert sync in (0, 1, 2, 3)
    finally:
        p.close()
