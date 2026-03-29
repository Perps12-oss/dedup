"""Tests for critical discovery/deletion fixes (chunk O(n), AppleScript escaping)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from dedup.engine.deletion import _escape_posix_path_for_applescript
from dedup.engine.discovery import DiscoveryCursor, DiscoveryOptions, DiscoveryService, FileDiscovery


def test_escape_posix_path_for_applescript_quotes() -> None:
    assert _escape_posix_path_for_applescript('/tmp/foo"bar') == r'/tmp/foo\"bar'
    assert _escape_posix_path_for_applescript(r"a\b") == r"a\\b"


def test_discover_chunk_linear_not_quadratic(tmp_path: Path) -> None:
    """Second chunk continues the same iterator (no re-walk of prior files)."""
    for i in range(5):
        (tmp_path / f"f{i}.txt").write_text("x", encoding="utf-8")

    opts = DiscoveryOptions(roots=[tmp_path], min_size_bytes=1)
    svc = DiscoveryService(opts)
    cur = DiscoveryCursor()

    b1, cur2, _ = svc.discover_chunk(cur, max_items=2)
    assert len(b1) == 2
    assert cur2 is not None
    assert cur2.files_emitted == 2

    b2, cur3, _ = svc.discover_chunk(cur2, max_items=2)
    assert len(b2) == 2
    assert cur3 is not None
    assert cur3.files_emitted == 4

    paths_round1 = {r.path for r in b1}
    paths_round2 = {r.path for r in b2}
    assert paths_round1.isdisjoint(paths_round2)


def test_discovery_exclude_paths_skips_subtree(tmp_path: Path) -> None:
    skip_dir = tmp_path / "skipped"
    skip_dir.mkdir()
    (skip_dir / "inner.txt").write_text("x", encoding="utf-8")
    (tmp_path / "visible.txt").write_text("y", encoding="utf-8")

    opts = DiscoveryOptions(
        roots=[tmp_path],
        min_size_bytes=1,
        exclude_paths={str(skip_dir.resolve())},
    )
    paths = {m.path for m in FileDiscovery(opts).discover()}
    assert any("visible.txt" in p for p in paths)
    assert not any("skipped" in p for p in paths)
