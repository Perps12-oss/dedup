"""
Persistence tests: save/load scan, hash cache, recovery.
"""

from __future__ import annotations

import pytest
from pathlib import Path
from datetime import datetime

from dedup.engine.models import ScanResult, ScanConfig, DuplicateGroup, FileMetadata
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
