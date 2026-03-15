from __future__ import annotations

from dedup.engine.benchmark_metrics import ScanBenchmarkReport, format_operator_summary
from dedup.engine.models import ScanConfig
from dedup.engine.pipeline import ScanPipeline
from dedup.infrastructure.persistence import Persistence
from dedup.scripts.bench_incremental_scan import run_scenario


def test_format_operator_summary_contains_core_fields():
    report = ScanBenchmarkReport(scan_id="abc123")
    report.discovery_reuse_mode = "merge"
    report.files_discovered_total = 10
    text = format_operator_summary(report)
    assert "discovery mode: merge" in text
    assert "files fresh=" in text
    assert "hash cache:" in text


def test_pipeline_benchmark_report_includes_discovery_and_hash_metrics(temp_dir):
    root = temp_dir / "scan-root"
    root.mkdir()
    (root / "a.txt").write_text("same")
    (root / "b.txt").write_text("same")

    persistence = Persistence(db_path=temp_dir / "bench-metrics.db")
    try:
        config = ScanConfig(roots=[root], hash_algorithm="md5", full_hash_workers=1, batch_size=1)
        result = ScanPipeline(
            config=config,
            persistence=persistence,
            hash_cache_getter=persistence.get_hash_cache,
            hash_cache_setter=persistence.set_hash_cache,
        ).run()
        metrics = result.benchmark_report or {}
        assert metrics["files_discovered_total"] == 2
        assert metrics["inventory_write_batches"] >= 1
        assert metrics["inventory_rows_written"] == 2
        assert "hash_cache_hits" in metrics
        assert "phase_metrics" in metrics
        assert "discovery" in metrics["phase_metrics"]
    finally:
        persistence.close()


def test_pipeline_reports_subtree_skip_metrics(temp_dir):
    root = temp_dir / "dataset"
    root.mkdir()
    sub = root / "sub"
    sub.mkdir()
    (sub / "a.txt").write_text("x")

    persistence = Persistence(db_path=temp_dir / "subtree-metrics.db")
    try:
        config = ScanConfig(roots=[root], hash_algorithm="md5", full_hash_workers=1, batch_size=1)
        ScanPipeline(config=config, persistence=persistence).run()
        second = ScanPipeline(config=config, persistence=persistence).run()
        metrics = second.benchmark_report or {}
        assert metrics["prior_session_found"] is True
        assert metrics["prior_session_compatible"] is True
        assert metrics["dirs_skipped_via_manifest"] >= 1
        assert metrics["files_discovered_fresh"] <= metrics["files_discovered_total"]
    finally:
        persistence.close()


def test_run_scenario_incompatible_config_reports_fallback(temp_dir):
    root = temp_dir / "scenario-root"
    root.mkdir()
    (root / "a.txt").write_text("a")
    outcome = run_scenario(
        root=root,
        scenario="incompatible_config",
        workers=1,
        resolve_paths=False,
    )
    assert outcome["second"]["prior_session_compatible"] is False
    assert outcome["second"]["discovery_reuse_mode"] == "none"


def test_run_scenario_same_session_resume_is_not_cross_session_reuse(temp_dir):
    root = temp_dir / "resume-root"
    root.mkdir()
    (root / "a.txt").write_text("a")
    outcome = run_scenario(
        root=root,
        scenario="same_session_resume",
        workers=1,
        resolve_paths=False,
    )
    assert outcome["second"]["prior_session_found"] is False
