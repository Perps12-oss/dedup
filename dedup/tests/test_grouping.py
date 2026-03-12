"""
Grouping tests: size grouping, duplicate confirmation, cancellation.
"""

from __future__ import annotations

from pathlib import Path

from dedup.engine.models import FileMetadata
from dedup.engine.hashing import HashEngine, HashStrategy
from dedup.engine.grouping import GroupingEngine


def test_group_by_size_filters_unique():
    engine = GroupingEngine(hash_engine=HashEngine(algorithm=HashStrategy.MD5, partial_bytes=64, workers=1))
    files = [
        FileMetadata(path="/a", size=10, mtime_ns=1),
        FileMetadata(path="/b", size=10, mtime_ns=1),
        FileMetadata(path="/c", size=20, mtime_ns=1),
    ]
    groups = engine.group_by_size(iter(files), scan_id="s1")
    assert set(groups.keys()) == {10}
    assert len(groups[10]) == 2


def test_find_duplicates_confirms_with_full_hash(temp_dir):
    p1 = temp_dir / "a.bin"
    p2 = temp_dir / "b.bin"
    p3 = temp_dir / "c.bin"
    p1.write_bytes(b"same content")
    p2.write_bytes(b"same content")
    p3.write_bytes(b"different")

    files = [
        FileMetadata(path=str(p1.resolve()), size=p1.stat().st_size, mtime_ns=1),
        FileMetadata(path=str(p2.resolve()), size=p2.stat().st_size, mtime_ns=1),
        FileMetadata(path=str(p3.resolve()), size=p3.stat().st_size, mtime_ns=1),
    ]
    grouping = GroupingEngine(hash_engine=HashEngine(algorithm=HashStrategy.MD5, partial_bytes=64, workers=2))
    dupes = grouping.find_duplicates(iter(files), scan_id="s2")
    assert len(dupes) == 1
    assert len(dupes[0].files) == 2
    names = {Path(f.path).name for f in dupes[0].files}
    assert names == {"a.bin", "b.bin"}


def test_find_duplicates_respects_cancel(temp_dir):
    p1 = temp_dir / "a.bin"
    p2 = temp_dir / "b.bin"
    p1.write_bytes(b"x" * 100)
    p2.write_bytes(b"x" * 100)
    files = [
        FileMetadata(path=str(p1.resolve()), size=100, mtime_ns=1),
        FileMetadata(path=str(p2.resolve()), size=100, mtime_ns=1),
    ]
    grouping = GroupingEngine(hash_engine=HashEngine(algorithm=HashStrategy.MD5, partial_bytes=64, workers=1))
    dupes = grouping.find_duplicates(iter(files), scan_id="s3", cancel_check=lambda: True)
    assert dupes == []
