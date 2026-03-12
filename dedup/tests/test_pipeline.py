"""
Pipeline tests: end-to-end scan, cancellation, resumable checkpoints, cache wiring.
"""

from __future__ import annotations

from pathlib import Path

from dedup.engine.models import ScanConfig, FileMetadata
from dedup.engine.pipeline import ScanPipeline, ResumableScanPipeline


def test_pipeline_integration_scan(temp_dir):
    # two duplicates + one unique
    (temp_dir / "a.txt").write_text("dup")
    (temp_dir / "b.txt").write_text("dup")
    (temp_dir / "c.txt").write_text("unique")

    cfg = ScanConfig(roots=[temp_dir], min_size_bytes=1, hash_algorithm="md5", full_hash_workers=2)
    result = ScanPipeline(cfg).run()
    assert result.files_scanned >= 3
    assert len(result.duplicate_groups) == 1
    assert result.total_duplicates == 1
    assert result.total_reclaimable_bytes > 0


def test_pipeline_cancel_before_run(temp_dir):
    (temp_dir / "a.txt").write_text("x")
    cfg = ScanConfig(roots=[temp_dir], min_size_bytes=1)
    pipeline = ScanPipeline(cfg)
    pipeline.cancel()
    result = pipeline.run()
    assert any("cancelled" in e.lower() for e in result.errors)


def test_resumable_save_and_load_checkpoint(temp_dir):
    cp = temp_dir / "checkpoints"
    cp.mkdir(parents=True, exist_ok=True)
    cfg = ScanConfig(roots=[temp_dir], min_size_bytes=1, hash_algorithm="md5")
    pipeline = ResumableScanPipeline(cfg, scan_id="scan_x", checkpoint_dir=cp)
    files = [FileMetadata(path=str((temp_dir / "a.txt").resolve()), size=1, mtime_ns=1)]
    pipeline._save_checkpoint(files)
    loaded = pipeline._load_checkpoint()
    assert loaded is not None
    assert len(loaded) == 1
    assert loaded[0].path.endswith("a.txt")


def test_resumable_run_uses_checkpoint_without_discovery(temp_dir, monkeypatch):
    cp = temp_dir / "checkpoints"
    cp.mkdir(parents=True, exist_ok=True)
    file_path = temp_dir / "dup.txt"
    file_path.write_text("dup")
    cfg = ScanConfig(roots=[temp_dir], min_size_bytes=1, hash_algorithm="md5")

    # create checkpoint using one pipeline instance
    prep = ResumableScanPipeline(cfg, scan_id="scan_y", checkpoint_dir=cp)
    prep._save_checkpoint([
        FileMetadata(path=str(file_path.resolve()), size=file_path.stat().st_size, mtime_ns=1),
        FileMetadata(path=str(file_path.resolve()), size=file_path.stat().st_size, mtime_ns=1),
    ])

    # run another instance with same scan_id: discovery should be skipped
    pipeline = ResumableScanPipeline(cfg, scan_id="scan_y", checkpoint_dir=cp)

    def _should_not_run(_cb=None):
        raise AssertionError("discovery should be skipped when checkpoint is present")

    monkeypatch.setattr(pipeline, "_discover_files", _should_not_run)
    result = pipeline.run()
    assert result.files_scanned == 2


def test_pipeline_hash_cache_callbacks_are_used(temp_dir):
    p1 = temp_dir / "x1.txt"
    p2 = temp_dir / "x2.txt"
    p1.write_text("hello")
    p2.write_text("hello")
    cfg = ScanConfig(roots=[temp_dir], min_size_bytes=1, hash_algorithm="md5")

    cache = {}
    calls = {"get": 0, "set": 0}

    def cache_get(path: str):
        calls["get"] += 1
        return cache.get(path)

    def cache_set(file: FileMetadata):
        calls["set"] += 1
        cache[file.path] = {
            "path": file.path,
            "size": file.size,
            "mtime_ns": file.mtime_ns,
            "hash_partial": file.hash_partial,
            "hash_full": file.hash_full,
        }
        return True

    result = ScanPipeline(cfg, hash_cache_getter=cache_get, hash_cache_setter=cache_set).run()
    assert result.files_scanned >= 2
    assert calls["get"] >= 1
    assert calls["set"] >= 1
