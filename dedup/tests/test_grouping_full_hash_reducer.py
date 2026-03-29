"""Sanity checks for FullHashReducer: batch full-hash persistence vs duplicate group creation."""

from __future__ import annotations

import pytest

from dedup.engine.grouping import FullHashReducer
from dedup.engine.hashing import HashEngine, HashStrategy
from dedup.engine.models import FileMetadata


def test_full_hash_reducer_upsert_batch_before_create_group(tmp_path):
    """Batch insert runs before duplicate_group_repo.create_group; one group for two identical files."""
    from unittest.mock import MagicMock

    p1 = tmp_path / "a.txt"
    p2 = tmp_path / "b.txt"
    content = b"identical-bytes-for-full-hash"
    p1.write_bytes(content)
    p2.write_bytes(content)

    f1 = FileMetadata(path=str(p1.resolve()), size=len(content), mtime_ns=1)
    f2 = FileMetadata(path=str(p2.resolve()), size=len(content), mtime_ns=1)
    # Same partial-hash bucket (engine will confirm via full hash)
    partial_groups = {"fake_partial": [f1, f2]}

    engine = HashEngine(algorithm=HashStrategy.MD5, workers=2)
    reducer = FullHashReducer(hash_engine=engine)

    mock_p = MagicMock()
    mock_p.inventory_repo.get_file_ids_by_paths.return_value = {
        str(p1.resolve()): 10,
        str(p2.resolve()): 11,
    }
    order: list[str] = []

    def on_batch(_rows):
        order.append("upsert_batch")

    def on_create(**_kwargs):
        order.append("create_group")

    mock_p.full_hash_repo.upsert_batch.side_effect = on_batch
    mock_p.duplicate_group_repo.create_group.side_effect = on_create

    out = reducer.reduce(partial_groups, "session-z", mock_p)

    mock_p.full_hash_repo.upsert_batch.assert_called_once()
    batch_rows = mock_p.full_hash_repo.upsert_batch.call_args[0][0]
    assert len(batch_rows) == 2
    mock_p.duplicate_group_repo.create_group.assert_called_once()
    assert len(out) == 1
    assert len(out[0].files) == 2
    assert order == ["upsert_batch", "create_group"]


def test_full_hash_reducer_batch_failure_skips_create_group(tmp_path):
    """If upsert_batch fails, duplicate groups are not created (single DB transaction failed before)."""
    from unittest.mock import MagicMock

    p1 = tmp_path / "one.txt"
    p2 = tmp_path / "two.txt"
    p1.write_bytes(b"x")
    p2.write_bytes(b"x")
    f1 = FileMetadata(path=str(p1.resolve()), size=1, mtime_ns=0)
    f2 = FileMetadata(path=str(p2.resolve()), size=1, mtime_ns=0)
    partial_groups = {"p": [f1, f2]}

    engine = HashEngine(algorithm=HashStrategy.MD5, workers=2)
    reducer = FullHashReducer(hash_engine=engine)

    mock_p = MagicMock()
    mock_p.inventory_repo.get_file_ids_by_paths.return_value = {
        str(p1.resolve()): 1,
        str(p2.resolve()): 2,
    }
    mock_p.full_hash_repo.upsert_batch.side_effect = OSError("disk full")

    with pytest.raises(OSError, match="disk full"):
        reducer.reduce(partial_groups, "session-z", mock_p)

    mock_p.duplicate_group_repo.create_group.assert_not_called()
