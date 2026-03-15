# Discovery & Pipeline Bottleneck Analysis

Based on your architecture and measured result (125,522 files in 21m 9s ≈ 99 files/sec during discovery).

---

## 1. Discovery-Specific Bottleneck Analysis

### Hot path per file

For each discovered file, the following happens:

```
os.scandir() → iterate entries
  → entry.is_dir() / entry.is_file()     [~0]
  → entry.stat()                         [1 syscall – primary cost]
  → Path(entry.path).resolve()           [1–2 syscalls on Windows; very costly on OneDrive/network]
  → FileMetadata(...)
  → result_queue.put(metadata)
```

Main thread (per 1000 files):

```
  → progress_cb() [every 100ms]
  → shadow_write_inventory(1000 rows)    [executemany + COMMIT]
  → _update_phase_checkpoint()           [upsert + shadow_update_session + 2x COMMIT]
```

### Identified discovery bottlenecks

| Bottleneck | Location | Impact |
|-----------|----------|--------|
| `Path(...).resolve()` on every file | `discovery.py:226` | High – on Windows/OneDrive each resolve() can do network/cloud I/O |
| `entry.stat()` for every file | `discovery.py:207` | Medium–high – main syscall; antivirus hooks into this |
| `num_workers = min(4, 4)` | `discovery.py:114` | Medium – discovery capped at 4 threads regardless of I/O wait |
| `commit()` per batch | `inventory_repo.py:63` | Medium – fsync every 1000 files |
| `_update_phase_checkpoint` per batch | `pipeline.py:718-724` | Low–medium – 2 DB writes + 2 commits per 1000 files |
| `result_queue` maxsize=1000 | `discovery.py:106` | Low – can backpressure workers |
| No WAL/synchronous tuning | `persistence.py:86` | Medium – default SQLite settings are conservative |

---

## 2. Full Pipeline Phase-by-Phase Bottleneck Analysis

| Phase | Main bottleneck | Why |
|-------|-----------------|-----|
| **Discovery** | `stat()` + `resolve()` + per-batch DB commits | Disk/network I/O per file; path resolution on Windows/cloud; DB write every 1000 files |
| **Size reduction** | In-memory grouping of full list | `_discovered_files` fully in memory; grouping is O(n) |
| **Partial hash** | Reading first 4KB of each candidate file | Disk I/O; many small files → many small reads |
| **Full hash** | Reading full files | Highest I/O; sequential reads |
| **Result assembly** | Minimal | Mostly in-memory work |

---

## 3. Likely Causes Ranked by Probability

Given G:\gallery\Takeout and ~99 files/sec:

| Rank | Cause | Probability | Rationale |
|------|-------|-------------|-----------|
| 1 | OneDrive or synced folders | Very high | Takeout often in OneDrive; cloud/sync adds latency to every stat/read |
| 2 | `Path.resolve()` on each file | Very high | Known to be expensive on Windows with OneDrive/junctions; done 125k+ times |
| 3 | Drive type (HDD/USB/network) | High | Takeout can live on external or network drives |
| 4 | Antivirus | High | Real-time scanning hooks into stat/open; common on Windows |
| 5 | Too many small files | Medium | Takeout: many JSON/HTML/thumbnails → many stat() calls per second |
| 6 | Windows `stat()` overhead | Medium | Slower than Linux; antivirus/Defender add more |
| 7 | Checkpoint/repository write overhead | Medium | 125 commits for inventory + 125 checkpoint writes during discovery |
| 8 | UI/event overhead | Low | Worker throttles to ~10 progress/sec; hub throttles deliveries |
| 9 | Inefficient directory walking | Low | `os.scandir` is appropriate; no obvious structural issues |

---

## 4. Instrumentation to Prove Dominant Cause

### 4.1 Add timing probes

Create `dedup/infrastructure/profiler.py`:

```python
"""Optional profiling probes – enable via DEDUP_PROFILE=1."""
import os
import time
from contextlib import contextmanager
from typing import Dict

_enabled = os.environ.get("DEDUP_PROFILE") == "1"
_timers: Dict[str, list] = {}

@contextmanager
def measure(name: str):
    if not _enabled:
        yield
        return
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        _timers.setdefault(name, []).append(elapsed)

def get_stats() -> Dict[str, dict]:
    if not _enabled:
        return {}
    result = {}
    for name, values in _timers.items():
        n = len(values)
        total = sum(values)
        result[name] = {"count": n, "total_s": total, "avg_ms": (total/n)*1000 if n else 0}
    return result
```

(Note: fix typo `_timimers` → `_timers` in the loop.)
```

### 4.2 Instrument discovery

In `discovery.py` `_scan_directory`:

```python
# Around line 207, wrap:
with measure("discovery.stat"):
    st = entry.stat(follow_symlinks=...)

# Around line 226, wrap:
with measure("discovery.resolve"):
    path_str = str(Path(entry.path).resolve())
```

### 4.3 Instrument pipeline writes

In `pipeline.py` `_discover_files`:

```python
with measure("pipeline.inventory_write"):
    self.persistence.shadow_write_inventory(...)
with measure("pipeline.checkpoint_write"):
    self._update_phase_checkpoint(...)
```

### 4.4 Quick diagnostic script

Add `scripts/profile_discovery.py`:

```python
"""Run: DEDUP_PROFILE=1 python -m dedup.scripts.profile_discovery G:\\path\\to\\Takeout --limit 5000"""
import os
import sys
import time
from pathlib import Path

# Ensure profile env is set
os.environ["DEDUP_PROFILE"] = "1"

from dedup.engine.discovery import FileDiscovery, DiscoveryOptions

def main():
    root = Path(sys.argv[1])
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 5000
    opts = DiscoveryOptions(roots=[root], min_size_bytes=1, max_workers=4)
    disc = FileDiscovery(opts)
    start = time.perf_counter()
    count = 0
    for f in disc.discover():
        count += 1
        if count >= limit:
            break
    elapsed = time.perf_counter() - start
    print(f"Files: {count}, Time: {elapsed:.2f}s, Rate: {count/elapsed:.0f} files/sec")
```

### 4.5 Minimal change: resolve() bypass

Fast check for `resolve()` impact:

```python
# In discovery.py line 226, temporarily replace:
path_str = str(Path(entry.path).resolve())
# With:
path_str = entry.path  # Skip resolve – test only
```

Re-run a small subset. If throughput jumps significantly, `resolve()` is a major bottleneck.

---

## 5. Top Code Changes (Ranked by Impact)

| Rank | Change | File | Impact | Effort |
|------|--------|------|--------|--------|
| 1 | **Remove or lazy `Path.resolve()`** | `discovery.py:226` | Very high | Low |
| 2 | **Use WAL + synchronous=NORMAL** | `persistence.py:_get_connection` | High | Low |
| 3 | **Larger inventory batch size** | `ScanConfig.batch_size` | Medium–high | Trivial |
| 4 | **Batch checkpoint writes** | `pipeline.py` | Medium | Medium |
| 5 | **Optional `resolve()`** | Config flag `resolve_paths: bool = False` | High (when disabled) | Low |
| 6 | **Increase discovery workers** | `discovery.py:114` | Medium | Trivial |
| 7 | **Defer inventory writes** | Write every 5k–10k files | Medium | Medium |
| 8 | **Use `entry.path` only** | Skip resolve when not needed for dedup logic | Very high | Low |

### Recommended first change: resolve()

```python
# discovery.py line 226 – make resolve optional
use_resolved = getattr(self.options, 'resolve_paths', False)
path_str = str(Path(entry.path).resolve()) if use_resolved else entry.path
```

Default `resolve_paths=False`; set `True` only when you need canonical paths (e.g. symlinks).

---

## 6. Top System/Environment Changes

| Rank | Change | Impact | Notes |
|------|--------|--------|------|
| 1 | **Move scan root off OneDrive/sync** | Very high | Copy Takeout to local SSD, scan there |
| 2 | **Exclude folder from real-time antivirus** | High | Add scan path to Defender exclusion list |
| 3 | **Use local SSD** | High | Local NVMe vs HDD/USB/network |
| 4 | **Close OneDrive sync during scan** | High | Pause sync for target folder |
| 5 | **Reduce concurrency if on HDD** | Medium | 1–2 workers can be faster than 4 on HDD |
| 6 | **Disable Windows Search indexer** | Low–medium | Can reduce I/O contention |

---

## 7. Recommended Benchmark Method

### 7.1 Standard benchmark script

Create `scripts/bench_discovery.py`:

```python
"""Benchmark discovery only. Usage: python -m dedup.scripts.bench_discovery <path> [--files N] [--runs 3]"""
import argparse
import statistics
import sys
import time
from pathlib import Path

from dedup.engine.discovery import FileDiscovery, DiscoveryOptions
from dedup.engine.models import ScanConfig


def run_discovery(root: Path, max_files: int | None = None, resolve: bool = False) -> tuple[int, float]:
    config = ScanConfig(roots=[root], min_size_bytes=1)
    opts = DiscoveryOptions.from_config(config)
    if hasattr(opts, 'resolve_paths'):
        opts.resolve_paths = resolve
    disc = FileDiscovery(opts)
    start = time.perf_counter()
    count = 0
    for _ in disc.discover():
        count += 1
        if max_files and count >= max_files:
            break
    elapsed = time.perf_counter() - start
    return count, elapsed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", type=Path)
    ap.add_argument("--files", type=int, default=None, help="Stop after N files")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--resolve", action="store_true", help="Use Path.resolve() (slow)")
    args = ap.parse_args()

    rates = []
    for i in range(args.runs):
        count, elapsed = run_discovery(args.path, args.files, args.resolve)
        rate = count / elapsed
        rates.append(rate)
        print(f"Run {i+1}: {count} files in {elapsed:.2f}s = {rate:.0f} files/sec")

    if len(rates) > 1:
        print(f"Mean: {statistics.mean(rates):.0f} files/sec, stdev: {statistics.stdev(rates):.0f}")
    sys.exit(0)
```

### 7.2 Benchmark protocol

1. **Baseline**: Run 3 times, report mean ± stdev.
2. **Isolation**: Use a small subtree (e.g. 10k files) for quick A/B tests.
3. **Storage**: Note drive type (HDD/SSD/NVMe, internal/external, sync status).
4. **Before/after**: Same path and settings before and after each change.

### 7.3 Example

```bash
# Baseline (current code)
python -m dedup.scripts.bench_discovery "G:\gallery\Takeout\Takeout\Mail" --files 20000 --runs 3

# With resolve disabled (if implemented)
python -m dedup.scripts.bench_discovery "G:\gallery\Takeout\Takeout\Mail" --files 20000 --runs 3

# On local SSD copy
python -m dedup.scripts.bench_discovery "C:\temp\Takeout_copy\Mail" --files 20000 --runs 3
```

---

## Summary

- **Discovery** is dominated by `entry.stat()` and `Path.resolve()` on Windows/OneDrive.
- **Top code fix**: Make `Path.resolve()` optional or remove it where not required.
- **Top environment fix**: Scan from a local, non-synced SSD and exclude from real-time antivirus.
- Add the suggested instrumentation to quantify the effect of each change.
