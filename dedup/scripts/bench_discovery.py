"""
Benchmark discovery-only throughput for before/after optimization comparison.

Usage:
    python -m dedup.scripts.bench_discovery "G:\\gallery\\Takeout" --files 20000 --runs 3
    python -m dedup.scripts.bench_discovery "C:\\temp\\Takeout_copy" --files 20000 --resolve --workers 8

Suggested benchmark sequence:
    # Baseline (resolve off, default workers)
    python -m dedup.scripts.bench_discovery "G:\\gallery\\Takeout" --files 20000 --runs 3

    # With resolve (A/B test)
    python -m dedup.scripts.bench_discovery "G:\\gallery\\Takeout" --files 20000 --runs 3 --resolve

    # Worker tuning
    python -m dedup.scripts.bench_discovery "G:\\gallery\\Takeout" --files 20000 --workers 2 --runs 3
    python -m dedup.scripts.bench_discovery "G:\\gallery\\Takeout" --files 20000 --workers 8 --runs 3

    # SSD comparison (copy Takeout to local SSD first)
    python -m dedup.scripts.bench_discovery "C:\\temp\\Takeout_copy" --files 20000 --runs 3
"""
from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

# Add project root for imports
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from dedup.engine.discovery import FileDiscovery, DiscoveryOptions
from dedup.engine.models import ScanConfig


def run_once(
    root: Path,
    max_files: int | None,
    resolve_paths: bool,
    workers: int,
) -> tuple[int, float]:
    """Run discovery once, return (count, elapsed_seconds)."""
    config = ScanConfig(
        roots=[root],
        min_size_bytes=1,
        batch_size=5000,
        full_hash_workers=workers,
        resolve_paths=resolve_paths,
        checkpoint_every_files=5000,
        discovery_max_workers=workers,
    )
    opts = DiscoveryOptions.from_config(config)
    disc = FileDiscovery(opts)

    start = time.perf_counter()
    count = 0
    for _ in disc.discover():
        count += 1
        if max_files is not None and count >= max_files:
            break
    elapsed = time.perf_counter() - start
    return count, elapsed


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Benchmark file discovery throughput."
    )
    ap.add_argument("path", type=Path, help="Root path to scan")
    ap.add_argument("--files", type=int, default=None, help="Stop after N files")
    ap.add_argument("--runs", type=int, default=3, help="Number of runs for mean/stdev")
    ap.add_argument("--resolve", action="store_true", help="Use Path.resolve() (slow on Windows/OneDrive)")
    ap.add_argument("--workers", type=int, default=4, help="Discovery worker threads")
    args = ap.parse_args()

    if not args.path.exists():
        print(f"Error: path does not exist: {args.path}", file=sys.stderr)
        return 1

    rates: list[float] = []
    for i in range(args.runs):
        count, elapsed = run_once(
            args.path,
            args.files,
            args.resolve,
            args.workers,
        )
        rate = count / elapsed if elapsed else 0
        rates.append(rate)
        print(f"Run {i + 1}: {count} files in {elapsed:.2f}s = {rate:.0f} files/sec")

    mean = statistics.mean(rates)
    stdev = statistics.stdev(rates) if len(rates) > 1 else 0.0
    print(f"Mean: {mean:.0f} files/sec, stdev: {stdev:.0f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
