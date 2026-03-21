"""Benchmark repeated-scan performance for incremental discovery."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from dedup.engine.benchmark_metrics import format_operator_summary
from dedup.engine.models import ScanConfig
from dedup.engine.pipeline import ScanPipeline
from dedup.infrastructure.persistence import Persistence


def _make_config(root: Path, workers: int, resolve_paths: bool, include_hidden: bool) -> ScanConfig:
    return ScanConfig(
        roots=[root],
        min_size_bytes=1,
        batch_size=5000,
        full_hash_workers=workers,
        discovery_max_workers=workers,
        resolve_paths=resolve_paths,
        include_hidden=include_hidden,
        checkpoint_every_files=5000,
        incremental_discovery=True,
    )


def _run_one_scan(
    config: ScanConfig,
    persistence: Persistence,
    *,
    scan_id: Optional[str] = None,
) -> Dict[str, Any]:
    pipeline = ScanPipeline(
        config=config,
        scan_id=scan_id or str(uuid.uuid4())[:12],
        persistence=persistence,
        hash_cache_getter=persistence.get_hash_cache,
        hash_cache_setter=persistence.set_hash_cache,
    )
    start = time.perf_counter()
    result = pipeline.run()
    wall_ms = int((time.perf_counter() - start) * 1000)
    report = dict(result.benchmark_report or {})
    report["wall_clock_ms"] = wall_ms
    report["files_scanned"] = result.files_scanned
    report["errors"] = list(result.errors)
    report["scan_id"] = result.scan_id
    return report


def _touch_localized_change(root: Path, rel_subtree: str) -> None:
    subtree = (root / rel_subtree).resolve()
    subtree.mkdir(parents=True, exist_ok=True)
    marker = subtree / ".bench_change_marker.txt"
    marker.write_text(f"changed at {time.time()}", encoding="utf-8")


def run_scenario(
    root: Path,
    scenario: str,
    workers: int,
    resolve_paths: bool,
    touch_subtree: Optional[str] = None,
) -> Dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="dedup-bench-") as tmp:
        db_path = Path(tmp) / "bench.db"
        persistence = Persistence(db_path=db_path)
        try:
            first_cfg = _make_config(root, workers, resolve_paths, include_hidden=False)
            baseline = _run_one_scan(first_cfg, persistence)

            if scenario == "localized_change":
                _touch_localized_change(root, touch_subtree or ".")

            second_cfg = _make_config(
                root,
                workers,
                resolve_paths,
                include_hidden=(scenario == "incompatible_config"),
            )
            second_scan_id = None
            if scenario == "same_session_resume":
                second_scan_id = baseline["scan_id"]
            second = _run_one_scan(second_cfg, persistence, scan_id=second_scan_id)

            return {
                "scenario": scenario,
                "baseline": baseline,
                "second": second,
                "speedup_vs_first": (
                    baseline.get("total_elapsed_ms", 0) / second.get("total_elapsed_ms", 1)
                    if second.get("total_elapsed_ms", 0)
                    else 0.0
                ),
            }
        finally:
            persistence.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark incremental repeated scans.")
    parser.add_argument("path", type=Path, help="Root dataset path")
    parser.add_argument(
        "--scenario",
        choices=[
            "unchanged",
            "localized_change",
            "incompatible_config",
            "same_session_resume",
        ],
        default="unchanged",
        help="Scenario to benchmark",
    )
    parser.add_argument("--runs", type=int, default=3, help="Number of repetitions")
    parser.add_argument("--workers", type=int, default=4, help="Discovery/hash workers")
    parser.add_argument("--resolve", action="store_true", help="Enable Path.resolve() in discovery")
    parser.add_argument(
        "--subtree",
        type=str,
        default=".",
        help="Relative subtree under path to benchmark",
    )
    parser.add_argument(
        "--touch-subtree",
        type=str,
        default=".",
        help="Relative subtree to mutate for localized_change scenario",
    )
    parser.add_argument("--json-out", type=Path, default=None, help="Optional JSON output file")
    args = parser.parse_args()

    root = (args.path / args.subtree).resolve()
    if not root.exists():
        print(f"Error: benchmark path does not exist: {root}", file=sys.stderr)
        return 1

    outcomes: list[Dict[str, Any]] = []
    second_discovery_ms: list[int] = []
    second_total_ms: list[int] = []
    speedups: list[float] = []

    for idx in range(args.runs):
        run = run_scenario(
            root=root,
            scenario=args.scenario,
            workers=args.workers,
            resolve_paths=args.resolve,
            touch_subtree=args.touch_subtree,
        )
        outcomes.append(run)
        second = run["second"]
        second_discovery_ms.append(int(second.get("discovery_elapsed_ms", 0)))
        second_total_ms.append(int(second.get("total_elapsed_ms", 0)))
        speedups.append(float(run.get("speedup_vs_first", 0.0)))

        print(f"Run {idx + 1}/{args.runs} scenario={args.scenario}")
        print("  First :", format_operator_summary(run["baseline"]))
        print("  Second:", format_operator_summary(run["second"]))
        print(f"  Speedup vs first (total): {run['speedup_vs_first']:.2f}x")

    summary = {
        "scenario": args.scenario,
        "runs": args.runs,
        "path": str(root),
        "second_discovery_elapsed_ms_mean": statistics.mean(second_discovery_ms),
        "second_discovery_elapsed_ms_stdev": statistics.stdev(second_discovery_ms)
        if len(second_discovery_ms) > 1
        else 0.0,
        "second_total_elapsed_ms_mean": statistics.mean(second_total_ms),
        "second_total_elapsed_ms_stdev": statistics.stdev(second_total_ms) if len(second_total_ms) > 1 else 0.0,
        "speedup_mean": statistics.mean(speedups),
        "speedup_stdev": statistics.stdev(speedups) if len(speedups) > 1 else 0.0,
    }

    print(
        "Summary: second-scan discovery mean={:.1f}ms stdev={:.1f}; total mean={:.1f}ms stdev={:.1f}; speedup mean={:.2f}x".format(
            summary["second_discovery_elapsed_ms_mean"],
            summary["second_discovery_elapsed_ms_stdev"],
            summary["second_total_elapsed_ms_mean"],
            summary["second_total_elapsed_ms_stdev"],
            summary["speedup_mean"],
        )
    )

    payload = {"summary": summary, "runs": outcomes}
    if args.json_out:
        args.json_out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote JSON report: {args.json_out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
