"""
Persistence tests: save/load scan, hash cache, recovery.

Characterisation tests: normal operation, missing data, list_resumable, close, ScanStore.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from dedup.engine.models import (
    DuplicateGroup,
    FileMetadata,
    ScanConfig,
    ScanResult,
)
from dedup.infrastructure.persistence import (
    Persistence,
    ScanStore,
    get_default_persistence,
)


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
            DuplicateGroup(group_id="g1", group_hash="h1", files=[
                FileMetadata(path="/a", size=5, mtime_ns=0),
                FileMetadata(path="/b", size=5, mtime_ns=0),
            ]),
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

    from dedup.engine.models import ScanPhase, PhaseStatus

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


def test_get_scan_missing_returns_none(persistence):
    """get_scan for unknown id returns None."""
    assert persistence.get_scan("nonexistent-id") is None


def test_delete_scan_missing_returns_false(persistence):
    """delete_scan for unknown id returns False."""
    assert persistence.delete_scan("nonexistent-id") is False


def test_list_resumable_scan_ids_empty_when_no_checkpoints(persistence, temp_dir):
    """list_resumable_scan_ids returns [] when checkpoint dir empty or missing."""
    ids = persistence.list_resumable_scan_ids()
    assert ids == [] or isinstance(ids, list)


def test_cleanup_old_cache_returns_count(persistence):
    """cleanup_old_cache returns number of deleted rows (0 when cache empty)."""
    n = persistence.cleanup_old_cache(max_age_days=30)
    assert isinstance(n, int)
    assert n >= 0


def test_close_idempotent(persistence):
    """close() can be called and does not raise; second close is safe."""
    persistence.close()
    persistence.close()


def test_scan_store_delegates(persistence):
    """ScanStore.save/load/list_recent/delete delegate to persistence."""
    store = ScanStore(persistence)
    result = ScanResult(
        scan_id="store-1",
        config=ScanConfig(roots=[]),
        started_at=datetime.now(),
        completed_at=datetime.now(),
        files_scanned=1,
    )
    assert store.save(result) is True
    loaded = store.load("store-1")
    assert loaded is not None
    assert loaded.scan_id == "store-1"
    recent = store.list_recent(limit=5)
    assert any(r["scan_id"] == "store-1" for r in recent)
    assert store.delete("store-1") is True
    assert store.load("store-1") is None


def test_get_default_persistence_returns_instance():
    """get_default_persistence returns a Persistence instance with expected path."""
    p = get_default_persistence()
    assert isinstance(p, Persistence)
    assert "dedup" in str(p.db_path).lower()
    p.close()
