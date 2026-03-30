"""Tests for duplicate-group keep selection helpers."""

from __future__ import annotations

from datetime import datetime

from dedup.engine.models import DuplicateGroup, FileMetadata, ScanConfig, ScanResult
from dedup.ui.utils.review_keep import coerce_keep_selections, default_keep_map_from_result


def _group(gid: str, paths: list[str]) -> DuplicateGroup:
    files = [FileMetadata(path=p, size=10, mtime_ns=i, inode=i + 1) for i, p in enumerate(paths)]
    return DuplicateGroup(group_id=gid, group_hash="h", files=files)


def _minimal_result(groups: list[DuplicateGroup]) -> ScanResult:
    return ScanResult(
        scan_id="s1",
        config=ScanConfig(roots=[], min_size_bytes=1),
        started_at=datetime.now(),
        duplicate_groups=groups,
    )


def test_default_keep_map_one_per_group():
    r = _minimal_result(
        [
            _group("g1", ["/a", "/b"]),
            _group("g2", ["/c", "/d", "/e"]),
        ]
    )
    m = default_keep_map_from_result(r)
    assert m["g1"] == "/a"
    assert m["g2"] == "/c"


def test_coerce_replaces_invalid_path():
    r = _minimal_result([_group("g1", ["/a", "/b"])])
    fixed = coerce_keep_selections(r, {"g1": "/stale"})
    assert fixed["g1"] == "/a"


def test_coerce_fills_missing_group():
    r = _minimal_result([_group("g1", ["/a", "/b"])])
    fixed = coerce_keep_selections(r, {})
    assert fixed["g1"] == "/a"
