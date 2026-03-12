"""
Discovery tests: streaming, cancellation, error handling.
"""

from __future__ import annotations

import os
import pytest
from pathlib import Path

from dedup.engine.discovery import FileDiscovery, DiscoveryOptions
from dedup.engine.models import FileMetadata


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


def test_discovery_no_subfolders_skips_nested_files(temp_dir):
    (temp_dir / "root.txt").write_text("abc")
    nested = temp_dir / "nested"
    nested.mkdir()
    (nested / "inside.txt").write_text("xyz")
    options = DiscoveryOptions(roots=[temp_dir], min_size_bytes=1, scan_subfolders=False)
    discovery = FileDiscovery(options)
    files = list(discovery.discover())
    assert len(files) == 1
    assert files[0].filename == "root.txt"


def test_discovery_symlink_when_follow_enabled(temp_dir):
    target = temp_dir / "target.txt"
    target.write_text("hello")
    link = temp_dir / "target_link.txt"
    try:
        os.symlink(target, link)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation not supported in this environment")

    options = DiscoveryOptions(
        roots=[temp_dir],
        min_size_bytes=1,
        follow_symlinks=True,
        max_workers=1,
    )
    discovery = FileDiscovery(options)
    files = list(discovery.discover())
    names = [f.filename for f in files]
    assert "target.txt" in names
    assert "target_link.txt" in names


def test_discovery_permission_error_does_not_crash(temp_dir, monkeypatch):
    (temp_dir / "a.txt").write_text("x")
    options = DiscoveryOptions(roots=[temp_dir], min_size_bytes=1, max_workers=1)
    discovery = FileDiscovery(options)

    def _boom(*args, **kwargs):
        raise PermissionError("denied")

    monkeypatch.setattr(discovery, "_scan_directory", _boom)
    files = list(discovery.discover())
    assert files == []
    assert discovery.get_stats()["errors"] >= 1
