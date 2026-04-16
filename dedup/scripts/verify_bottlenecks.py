"""
Verify bottleneck-fix claims from code + runtime guards.

Usage:
  python -m dedup.scripts.verify_bottlenecks
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class Claim:
    bn: str
    sha: str
    summary: str


CLAIMS: tuple[Claim, ...] = (
    Claim("BN-001", "c910f42", "File deletion offloaded to background thread"),
    Claim("BN-002", "8dca932", "Diagnostics artifact scan offloaded"),
    Claim("BN-003", "3749dbb", "PIL image loading offloaded"),
    Claim("BN-004", "420bf3c", "GradientBar resize debounced"),
    Claim("BN-005", "db0692c", "History rows cached and reused"),
    Claim("BN-006", "0abc815", "Mission sessions skip rebuild when unchanged"),
    Claim("BN-008", "25a97ed", "Diagnostics tab content skips unchanged rebuild"),
    Claim("BN-009", "a684aa1", "Themes stop-chip updates in-place"),
    Claim("BN-010", "6068ef9", "Skip redundant label configure() calls"),
    Claim("BN-011", "0d5cf40", "Removed forced update_idletasks redraw"),
    Claim("BN-012", "dd14a50", "Cinematic backdrop repaint debounced"),
)


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, capture_output=True, check=False)


def _claim_on_origin_main(sha: str) -> bool:
    cp = _run(["git", "merge-base", "--is-ancestor", sha, "origin/main"])
    return cp.returncode == 0


def _run_guard_tests() -> bool:
    cp = _run([sys.executable, "-m", "pytest", "-q", "-m", "bottleneck_guard"])
    sys.stdout.write(cp.stdout)
    sys.stderr.write(cp.stderr)
    return cp.returncode == 0


def main() -> int:
    results: dict[str, dict[str, str | bool]] = {}
    all_commits_ok = True
    for c in CLAIMS:
        on_main = _claim_on_origin_main(c.sha)
        all_commits_ok &= on_main
        results[c.bn] = {"sha": c.sha, "summary": c.summary, "on_origin_main": on_main}

    guards_ok = _run_guard_tests()
    report = {
        "commit_claims_ok": all_commits_ok,
        "guard_tests_ok": guards_ok,
        "claims": results,
    }
    print("\n=== bottleneck verification report ===")
    print(json.dumps(report, indent=2))
    return 0 if (all_commits_ok and guards_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
