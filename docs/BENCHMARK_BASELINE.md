# Benchmark and profiling baseline

Lightweight baseline for measuring scan pipeline performance. Use this to compare results before/after performance work (e.g. discovery hot-path, persistence tuning).

## How to run

### 1. Discovery-only throughput

```bash
python -m dedup.scripts.bench_discovery <path> [--files N] [--runs 3] [--resolve] [--workers N]
```

- **path**: Root directory to scan.
- **--files N**: Stop after N files (optional).
- **--runs**: Number of runs for mean/stdev (default 3).
- **--resolve**: Use `Path.resolve()` (slower on Windows/OneDrive).
- **--workers**: Discovery worker threads (default 4).

### 2. Full-pipeline scenarios (fresh / resume / unchanged / changed)

```bash
python -m dedup.scripts.bench_incremental_scan <path> --scenario <scenario> [--runs 3] [--json-out report.json]
```

Scenarios:

| Scenario              | Description                          |
|-----------------------|--------------------------------------|
| `unchanged`           | Second run over same tree, no changes (unchanged rerun). |
| `localized_change`    | Touch a subtree between runs (changed rerun). |
| `same_session_resume` | Second run resumes from first scan_id (resume scan). |
| `incompatible_config` | Second run with different config (e.g. include_hidden) so no reuse. |

The **first run** in each scenario is a **fresh scan**; the **second** is the scenario under test.

### 3. All scenarios in one go (baseline snapshot)

```bash
python -m dedup.scripts.run_baseline <path> [--runs 2] [--json-out baseline.json]
```

Runs fresh, resume, unchanged, and changed; writes one JSON with wall time and stage timings for later comparison.

## Profiling hooks (optional)

- **DEDUP_PROFILE=1**: Enable `dedup.infrastructure.profiler` timing probes. Use `measure("name")` in code; read with `get_stats()`.
- **DEDUP_BENCH=1**: Enable `dedup.engine.bench` BenchCollector for phase-level metrics (if wired in pipeline).

Profiler and bench are **optional** and do not change production behavior when disabled.

## Metrics captured

- **Wall clock**: Total elapsed time per run.
- **Stage timings**: Where supported (e.g. from pipeline benchmark_report): discovery, grouping, hashing, result assembly.
- **Throughput**: Files/sec from discovery or full scan.
- **Speedup**: For incremental scenarios, ratio of first-scan time to second-scan time.

Output format (from `bench_incremental_scan` and `run_baseline`): JSON with `summary` and per-run details, so later PRs can diff or compare numerically.

## Environment notes

- **Windows + OneDrive / AV**: Can cause noisy timings. Prefer a local copy of the test tree or exclude AV on the benchmark path.
- **Same root, same machine**: For comparable baselines, run on the same path and machine; document root path and run date in the JSON or commit message.

## Comparing results later

1. Run `run_baseline` (or individual scripts) before changes; save JSON.
2. Apply performance changes.
3. Run again with same path and runs.
4. Compare `summary.second_total_elapsed_ms_mean`, `summary.second_discovery_elapsed_ms_mean`, and scenario speedups.

No production behavior change is required to run benchmarks; they use the same pipeline and persistence APIs as the app.

## Discovery hot path

- **Default**: `resolve_paths=False` in ScanConfig and DiscoveryOptions; discovery does not call `Path.resolve()` per file, keeping the hot path minimal. Paths are used as returned by the OS (e.g. scandir).
- **Comparison**: Use `--resolve` in `bench_discovery` to measure the cost of enabling path resolution; compare against the default run to validate hot-path reduction.
- **Boundary**: Discovery-time data (path, size, mtime_ns, inode) is sufficient for hashing and grouping; any later path normalization is outside the discovery hot path.
