"""
Coordinator tests: option pass-through and media category mapping.
"""

from __future__ import annotations

from pathlib import Path

from dedup.infrastructure.persistence import Persistence
from dedup.orchestration import coordinator as coordinator_module
from dedup.orchestration.coordinator import ScanCoordinator


def test_start_scan_passes_scan_options_to_worker(temp_dir, monkeypatch):
    db = temp_dir / "coord.db"
    persistence = Persistence(db_path=db)
    captured = {}

    class FakeWorker:
        def __init__(self, config, event_bus, **kwargs):
            captured["config"] = config
            captured["kwargs"] = kwargs
            self.callbacks = type("Callbacks", (), {})()
            self.is_running = False
            self.scan_id = "fake-scan-id"

        def start(self):
            return "fake-scan-id"

        def cancel(self):
            return None

        def join(self, timeout=None):
            return True

    monkeypatch.setattr(coordinator_module, "ScanWorker", FakeWorker)

    try:
        coordinator = ScanCoordinator(persistence=persistence)
        scan_id = coordinator.start_scan(
            roots=[temp_dir],
            min_size=123,
            max_size=456,
            include_hidden=True,
            follow_symlinks=True,
            scan_subfolders=False,
            media_category="images",
            partial_hash_bytes=8192,
            full_hash_workers=3,
            batch_size=333,
            progress_interval_ms=250,
            exclude_dirs={"tmp", "build"},
        )
        assert scan_id == "fake-scan-id"
        cfg = captured["config"]
        assert cfg.min_size_bytes == 123
        assert cfg.max_size_bytes == 456
        assert cfg.include_hidden is True
        assert cfg.follow_symlinks is True
        assert cfg.scan_subfolders is False
        assert cfg.partial_hash_bytes == 8192
        assert cfg.full_hash_workers == 3
        assert cfg.batch_size == 333
        assert cfg.progress_interval_ms == 250
        assert "tmp" in cfg.exclude_dirs
        assert "jpg" in (cfg.allowed_extensions or set())
        assert cfg.use_streaming is False  # default

        coordinator.start_scan(
            roots=[temp_dir],
            use_streaming=True,
            streaming_batch_size=9999,
        )
        cfg_streaming = captured["config"]
        assert cfg_streaming.use_streaming is True
        assert cfg_streaming.streaming_batch_size == 9999
    finally:
        persistence.close()
