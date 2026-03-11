#!/usr/bin/env python3
"""
Generate synthetic datasets for DEDUP stress and correctness testing.

Profiles:
  1. many_small   - Many small files
  2. many_large   - Few large files
  3. mixed        - Mixed sizes
  4. same_size_non_dupes - Many same-size but different content (collision stress)
  5. true_duplicates - Many identical copies
  6. near_collision - Same prefix, different rest (partial hash stress)
  7. deep_tree    - Deep directory structure
  8. permission_denied - Dir we can't read (platform-dependent)
  9. unicode_paths - Paths with non-ASCII names

Usage:
  python scripts/generate_stress_datasets.py <output_dir> [--profile NAME] [--count N]
"""

from __future__ import annotations

import argparse
import os
import random
import string
import sys
from pathlib import Path

# Project root
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


def random_bytes(n: int) -> bytes:
    return bytes(random.randint(0, 255) for _ in range(n))


def profile_many_small(root: Path, count: int = 5000) -> None:
    """Many small files (1–2 KB)."""
    d = ensure_dir(root / "many_small")
    for i in range(count):
        (d / f"file_{i:06d}.bin").write_bytes(random_bytes(random.randint(1024, 2048)))
    print(f"  Wrote {count} small files under {d}")


def profile_many_large(root: Path, count: int = 20, size_mb: int = 10) -> None:
    """Few large files."""
    d = ensure_dir(root / "many_large")
    chunk = 1024 * 1024  # 1 MB
    for i in range(count):
        with open(d / f"large_{i:04d}.bin", "wb") as f:
            for _ in range(size_mb):
                f.write(random_bytes(chunk))
    print(f"  Wrote {count} large files ({size_mb} MB each) under {d}")


def profile_mixed(root: Path, count: int = 1000) -> None:
    """Mixed file sizes."""
    d = ensure_dir(root / "mixed")
    for i in range(count):
        size = random.choice([100, 500, 2000, 50000, 100000])
        (d / f"mixed_{i:05d}.bin").write_bytes(random_bytes(size))
    print(f"  Wrote {count} mixed-size files under {d}")


def profile_same_size_non_dupes(root: Path, count: int = 500, size: int = 4096) -> None:
    """Many same-size files with different content (stress partial hash grouping)."""
    d = ensure_dir(root / "same_size_non_dupes")
    for i in range(count):
        (d / f"same_size_{i:05d}.bin").write_bytes(random_bytes(size))
    print(f"  Wrote {count} same-size ({size} B) different-content files under {d}")


def profile_true_duplicates(root: Path, copies: int = 50, group_count: int = 10) -> None:
    """Multiple groups of identical files."""
    d = ensure_dir(root / "true_duplicates")
    for g in range(group_count):
        content = random_bytes(random.randint(500, 5000))
        for c in range(copies):
            (d / f"group{g}_copy{c:03d}.bin").write_bytes(content)
    print(f"  Wrote {group_count} groups x {copies} copies under {d}")


def profile_near_collision(root: Path, count: int = 100, prefix_len: int = 4096, total: int = 8192) -> None:
    """Same first N bytes, different rest (partial hash collision candidates)."""
    d = ensure_dir(root / "near_collision")
    prefix = random_bytes(prefix_len)
    for i in range(count):
        (d / f"near_{i:04d}.bin").write_bytes(prefix + random_bytes(total - prefix_len))
    print(f"  Wrote {count} near-collision files (prefix {prefix_len}, total {total}) under {d}")


def profile_deep_tree(root: Path, depth: int = 10, files_per_dir: int = 5) -> None:
    """Deep directory tree with few files per dir."""
    d = root / "deep_tree"
    ensure_dir(d)
    def make_level(path: Path, level: int):
        if level <= 0:
            return
        for i in range(3):
            sub = path / f"dir_{i}"
            ensure_dir(sub)
            for j in range(files_per_dir):
                (sub / f"f_{j}.bin").write_bytes(random_bytes(100 + level * 10))
            make_level(sub, level - 1)
    make_level(d, depth)
    print(f"  Wrote deep tree (depth {depth}, ~{files_per_dir} files per dir) under {d}")


def profile_unicode_paths(root: Path, count: int = 50) -> None:
    """Paths with non-ASCII names."""
    d = ensure_dir(root / "unicode")
    names = ["café", "naïve", "日本語", "émoji", "München", "Zürich", "файл", "тест"]
    for i in range(count):
        name = f"{random.choice(names)}_{i:04d}.bin"
        (d / name).write_bytes(random_bytes(200))
    print(f"  Wrote {count} files with unicode names under {d}")


def main():
    ap = argparse.ArgumentParser(description="Generate DEDUP stress test datasets")
    ap.add_argument("output_dir", type=Path, help="Output directory")
    ap.add_argument("--profile", choices=[
        "many_small", "many_large", "mixed", "same_size_non_dupes",
        "true_duplicates", "near_collision", "deep_tree", "unicode", "all",
    ], default="all", help="Dataset profile")
    ap.add_argument("--count", type=int, default=0, help="Override count for small/mixed profiles")
    args = ap.parse_args()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    count = args.count or 5000
    profiles = [
        "many_small", "many_large", "mixed", "same_size_non_dupes",
        "true_duplicates", "near_collision", "deep_tree", "unicode",
    ] if args.profile == "all" else [args.profile]
    for name in profiles:
        print(f"Profile: {name}")
        if name == "many_small":
            profile_many_small(out, min(count, 5000))
        elif name == "many_large":
            profile_many_large(out)
        elif name == "mixed":
            profile_mixed(out, min(count, 2000))
        elif name == "same_size_non_dupes":
            profile_same_size_non_dupes(out)
        elif name == "true_duplicates":
            profile_true_duplicates(out)
        elif name == "near_collision":
            profile_near_collision(out)
        elif name == "deep_tree":
            profile_deep_tree(out)
        elif name == "unicode":
            profile_unicode_paths(out)
    print("Done.")


if __name__ == "__main__":
    main()
