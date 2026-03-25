"""canonical_scan_root policy."""

from __future__ import annotations

from pathlib import Path

from dedup.infrastructure.path_policy import canonical_scan_root


def test_canonical_scan_root_resolves(tmp_path):
    d = tmp_path / "sub"
    d.mkdir()
    out = canonical_scan_root(d)
    assert out.is_absolute()
    assert out == d.resolve()


def test_canonical_scan_root_accepts_str(tmp_path):
    d = tmp_path / "a"
    d.mkdir()
    assert canonical_scan_root(str(d)) == Path(d).resolve()
