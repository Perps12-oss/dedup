"""
Discovery tests: streaming, cancellation, error handling.
"""

from __future__ import annotations

import pytest

from dedup.engine.discovery import DiscoveryOptions, FileDiscovery


@pytest.fixture
def discovery_options(temp_dir):
    return DiscoveryOptions(roots=[temp_dir], min_size_bytes=1, max_workers=2)


def test_discovery_yields_files(temp_dir, discovery_options):
    (temp_dir / "a.txt").write_text("a")
    (temp_dir / "b.txt").write_text("bb")
    discovery = FileDiscovery(discovery_options)
    files = list(discovery.discover())
    assert len(files) == 2
    paths = {f.path for f in files}
    assert any("a.txt" in p for p in paths)
    assert any("b.txt" in p for p in paths)


def test_discovery_respects_min_size(temp_dir, discovery_options):
    (temp_dir / "small.txt").write_text("x")  # 1 byte
    discovery_options.min_size_bytes = 10
    discovery = FileDiscovery(discovery_options)
    files = list(discovery.discover())
    assert len(files) == 0


def test_discovery_cancel(discovery_options):
    discovery = FileDiscovery(discovery_options)
    discovery.cancel()
    count = 0
    for _ in discovery.discover():
        count += 1
        if count > 10:
            break
    assert discovery.is_cancelled


def test_discovery_stats(temp_dir, discovery_options):
    (temp_dir / "f1.txt").write_text("1")
    discovery = FileDiscovery(discovery_options)
    list(discovery.discover())
    stats = discovery.get_stats()
    assert stats["files_found"] == 1
    assert stats["dirs_scanned"] >= 1
