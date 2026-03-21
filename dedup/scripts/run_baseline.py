"""
Run all benchmark scenarios and write a single baseline JSON for later comparison.

Usage:
    python -m dedup.scripts.run_baseline <path> [--runs 2] [--json-out baseline.json]

Scenarios run: unchanged (fresh + unchanged rerun), same_session_resume (fresh + resume),
localized_change (fresh + changed). No production behavior change.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from dedup.scripts.bench_incremental_scan import run_scenario

SCENARIOS = ("unchanged", "same_session_resume", "localized_change")


def run_baseline(
    root: Path,
    runs: int = 2,
    workers: int = 4,
    resolve_paths: bool = False,
    touch_subtree: str = ".",
) -> Dict[str, Any]:
    """Run each scenario `runs` times and collect wall time + stage timings."""
    results: List[Dict[str, Any]] = []
    for scenario in SCENARIOS:
        for i in range(runs):
            t0 = time.perf_counter()
            out = run_scenario(
                root=root,
                scenario=scenario,
                workers=workers,
                resolve_paths=resolve_paths,
                touch_subtree=touch_subtree,
            )
            wall_s = time.perf_counter() - t0
            results.append(
                {
                    "scenario": scenario,
                    "run": i + 1,
                    "wall_s": round(wall_s, 2),
                    "baseline_total_ms": out.get("baseline", {}).get("total_elapsed_ms"),
                    "second_total_ms": out.get("second", {}).get("total_elapsed_ms"),
                    "speedup_vs_first": out.get("speedup_vs_first"),
                }
            )
    return {
        "scenarios": SCENARIOS,
        "runs_per_scenario": runs,
        "path": str(root),
        "workers": workers,
        "resolve_paths": resolve_paths,
        "env": {"DEDUP_PROFILE": os.environ.get("DEDUP_PROFILE"), "DEDUP_BENCH": os.environ.get("DEDUP_BENCH")},
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run benchmark baseline (fresh/resume/unchanged/changed).")
    parser.add_argument("path", type=Path, help="Root path to scan")
    parser.add_argument("--runs", type=int, default=2, help="Runs per scenario")
    parser.add_argument("--workers", type=int, default=4, help="Workers")
    parser.add_argument("--resolve", action="store_true", help="Use Path.resolve() in discovery")
    parser.add_argument("--json-out", type=Path, default=None, help="Write baseline JSON here")
    parser.add_argument("--touch-subtree", type=str, default=".", help="Subtree to touch for localized_change")
    args = parser.parse_args()

    if not args.path.exists():
        print(f"Error: path does not exist: {args.path}", file=sys.stderr)
        return 1

    root = args.path.resolve()
    payload = run_baseline(
        root,
        runs=args.runs,
        workers=args.workers,
        resolve_paths=args.resolve,
        touch_subtree=args.touch_subtree,
    )

    print(json.dumps(payload, indent=2))
    if args.json_out:
        args.json_out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote: {args.json_out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
