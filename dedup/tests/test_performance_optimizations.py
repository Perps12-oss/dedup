"""Regression tests for hashing throughput, batch DB writes, and progress throttling."""

from __future__ import annotations

import sqlite3

from dedup.engine.hashing import HashEngine, HashStrategy
from dedup.engine.models import FileMetadata
from dedup.infrastructure.repositories.hash_repo import FullHashRepository, PartialHashRepository


def test_hash_batch_partial_progress_throttled(tmp_path):
    """Progress callback should fire rarely when interval is very large."""
    files = []
    for i in range(40):
        p = tmp_path / f"f{i}.txt"
        p.write_text("x")
        files.append(FileMetadata(path=str(p.resolve()), size=1, mtime_ns=0))

    calls: list[int] = []
    engine = HashEngine(algorithm=HashStrategy.MD5, partial_bytes=64, workers=4)
    engine.progress_interval_ms = 1_000_000_000.0  # effectively one burst

    list(engine.hash_batch_partial(files, progress_cb=lambda n: calls.append(n)))

    assert len(calls) < 15


def test_partial_hash_upsert_batch_inserts_rows(tmp_path):
    """Batch upsert writes all rows in one executemany."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE partial_hashes (
            session_id TEXT NOT NULL,
            file_id INTEGER NOT NULL,
            algorithm TEXT NOT NULL,
            strategy_version TEXT NOT NULL,
            sample_spec_json TEXT NOT NULL,
            partial_hash TEXT NOT NULL,
            computed_at TEXT NOT NULL,
            PRIMARY KEY (session_id, file_id)
        );
        """
    )
    repo = PartialHashRepository(conn)
    rows = [
        ("s1", i, "md5", "v1", "{}", f"h{i}", "2020-01-01T00:00:00")
        for i in range(50)
    ]
    repo.upsert_batch(rows)
    n = conn.execute("SELECT COUNT(*) AS c FROM partial_hashes").fetchone()["c"]
    assert n == 50


def test_full_hash_upsert_batch_inserts_rows():
    """Batch full-hash upsert writes all rows in one executemany."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE full_hashes (
            session_id TEXT NOT NULL,
            file_id INTEGER NOT NULL,
            algorithm TEXT NOT NULL,
            full_hash TEXT NOT NULL,
            computed_at TEXT NOT NULL,
            PRIMARY KEY (session_id, file_id, algorithm)
        );
        """
    )
    repo = FullHashRepository(conn)
    rows = [("s1", i, "md5", f"h{i}", "2020-01-01T00:00:00") for i in range(50)]
    repo.upsert_batch(rows)
    n = conn.execute("SELECT COUNT(*) AS c FROM full_hashes").fetchone()["c"]
    assert n == 50


def test_partial_hash_empty_file(tmp_path):
    engine = HashEngine(algorithm=HashStrategy.MD5, partial_bytes=256, workers=2)
    p = tmp_path / "empty.bin"
    p.write_bytes(b"")
    m = FileMetadata(path=str(p.resolve()), size=0, mtime_ns=0)
    h = engine.hash_partial(m)
    assert h is not None
