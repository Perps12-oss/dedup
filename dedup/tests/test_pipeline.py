"""
Pipeline tests: durable discovery writes inventory and checkpoints.
"""

from __future__ import annotations

from dedup.engine.models import ScanConfig, ScanPhase
from dedup.engine.pipeline import ScanPipeline
from dedup.infrastructure.persistence import Persistence


def test_pipeline_persists_inventory_and_checkpoints(temp_dir):
    scan_root = temp_dir / "scan-root"
    scan_root.mkdir()
    (scan_root / "a.txt").write_text("same")
    (scan_root / "b.txt").write_text("same")

    persistence = Persistence(db_path=temp_dir / "pipeline.db")
    try:
        pipeline = ScanPipeline(
            config=ScanConfig(roots=[scan_root], hash_algorithm="md5", full_hash_workers=1, batch_size=1),
            persistence=persistence,
            hash_cache_getter=persistence.get_hash_cache,
            hash_cache_setter=persistence.set_hash_cache,
        )
        result = pipeline.run()

        assert result.files_scanned == 2
        assert persistence.inventory_repo.count(result.scan_id) == 2
        checkpoint = persistence.checkpoint_repo.get(result.scan_id, ScanPhase.DISCOVERY)
        assert checkpoint is not None
        assert checkpoint.completed_units == 2
        assert checkpoint.status.value == "completed"
    finally:
        persistence.close()
