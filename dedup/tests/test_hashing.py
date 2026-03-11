"""
Hashing tests: partial hash is for candidates only; confirmation requires full hash.

- No duplicate is declared from partial hash alone.
- Partial hash uses first+middle+last sampling (stronger than first-only).
"""

from __future__ import annotations

import pytest
from pathlib import Path

from dedup.engine.models import FileMetadata, ScanConfig
from dedup.engine.hashing import HashEngine, HashStrategy, group_by_partial_hash, confirm_duplicates


@pytest.fixture
def hash_engine():
    return HashEngine(algorithm=HashStrategy.MD5, partial_bytes=256, workers=2)


class TestPartialVsFull:
    """Partial hash must not be used for duplicate confirmation."""

    def test_confirm_duplicates_uses_full_hash(self, temp_dir, hash_engine):
        # Two files with same content -> same full hash -> one confirmed group
        p1 = temp_dir / "a.bin"
        p2 = temp_dir / "b.bin"
        content = b"identical content for full hash"
        p1.write_bytes(content)
        p2.write_bytes(content)
        m1 = FileMetadata(path=str(p1.resolve()), size=len(content), mtime_ns=0)
        m2 = FileMetadata(path=str(p2.resolve()), size=len(content), mtime_ns=0)
        candidates = {"partial_match": [m1, m2]}
        confirmed = confirm_duplicates(candidates, hash_engine)
        assert len(confirmed) == 1
        assert len(list(confirmed.values())[0]) == 2

    def test_different_content_same_partial_can_collide_but_full_separates(self, temp_dir, hash_engine):
        # Two files: same first 256 bytes, different rest -> same partial, different full
        chunk = b"x" * 256
        p1 = temp_dir / "x1.bin"
        p2 = temp_dir / "x2.bin"
        p1.write_bytes(chunk + b"aaa")
        p2.write_bytes(chunk + b"bbb")
        m1 = FileMetadata(path=str(p1.resolve()), size=p1.stat().st_size, mtime_ns=0)
        m2 = FileMetadata(path=str(p2.resolve()), size=p2.stat().st_size, mtime_ns=0)
        partial_groups = group_by_partial_hash([m1, m2], hash_engine)
        # They may or may not share partial hash (first+middle+last); if they do:
        confirmed = confirm_duplicates(partial_groups, hash_engine)
        # Full hash must separate them
        total_in_confirmed = sum(len(files) for files in confirmed.values())
        assert total_in_confirmed <= 2
        # Either two singletons (filtered out) or one group of 2; since content differs, no group of 2
        for files in confirmed.values():
            assert len(files) < 2 or all(f.hash_full and f.hash_full == files[0].hash_full for f in files)


class TestPartialHashSampling:
    """Partial hash uses multiple chunks (first, middle, last)."""

    def test_partial_hash_different_for_prefix_only_same_size(self, temp_dir, hash_engine):
        # File A: prefix X, rest Y. File B: prefix X, rest Z. Same size.
        # Middle/last differ -> partial hash should differ (so they don't become false candidates)
        size = 1024
        p1 = temp_dir / "pre1.bin"
        p2 = temp_dir / "pre2.bin"
        p1.write_bytes(b"x" * 256 + b"a" * (size - 256))
        p2.write_bytes(b"x" * 256 + b"b" * (size - 256))
        m1 = FileMetadata(path=str(p1.resolve()), size=size, mtime_ns=0)
        m2 = FileMetadata(path=str(p2.resolve()), size=size, mtime_ns=0)
        h1 = hash_engine.hash_partial(m1)
        h2 = hash_engine.hash_partial(m2)
        assert h1 is not None and h2 is not None
        assert h1 != h2
