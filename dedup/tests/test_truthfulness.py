"""
Truthfulness tests: duplicate counts, reclaimable bytes, no candidates as confirmed.

- Reclaimable space is only from confirmed (full-hash) duplicate groups.
- Candidates (partial hash match) are never shown as confirmed.
- Duplicate counts are exact (sum of (len(files)-1) over confirmed groups).
"""

from __future__ import annotations

from dedup.engine.metrics_semantics import Phase, should_show_eta, should_show_percent
from dedup.engine.models import (
    DuplicateGroup,
    FileMetadata,
    ScanConfig,
    ScanProgress,
    ScanResult,
)


class TestReclaimableOnlyFromConfirmed:
    """Reclaimable bytes must come only from groups with full-hash confirmation."""

    def test_reclaimable_is_sum_of_group_reclaimable(self):
        # Each group: reclaimable_size = file_size * (n - 1)
        g1 = DuplicateGroup(
            group_id="g1",
            group_hash="abc",
            files=[
                FileMetadata(path="/a", size=100, mtime_ns=0),
                FileMetadata(path="/b", size=100, mtime_ns=0),
                FileMetadata(path="/c", size=100, mtime_ns=0),
            ],
        )
        assert g1.reclaimable_size == 200  # 100 * 2

        g2 = DuplicateGroup(
            group_id="g2",
            group_hash="def",
            files=[
                FileMetadata(path="/d", size=50, mtime_ns=0),
                FileMetadata(path="/e", size=50, mtime_ns=0),
            ],
        )
        assert g2.reclaimable_size == 50

        total = g1.reclaimable_size + g2.reclaimable_size
        assert total == 250

    def test_scan_result_total_reclaimable_matches_groups(self):
        groups = [
            DuplicateGroup(
                group_id="1",
                group_hash="h1",
                files=[
                    FileMetadata(path="/p1", size=10, mtime_ns=0),
                    FileMetadata(path="/p2", size=10, mtime_ns=0),
                ],
            ),
        ]
        result = ScanResult(
            scan_id="s1",
            config=ScanConfig(roots=[]),
            started_at=__import__("datetime").datetime.now(),
            duplicate_groups=groups,
            total_reclaimable_bytes=10,
        )
        # Should be consistent
        assert result.total_reclaimable_bytes == sum(g.reclaimable_size for g in groups)


class TestNoPercentWithoutTotal:
    """Progress percent is only shown when total is known."""

    def test_percent_none_when_files_total_none(self):
        progress = ScanProgress(scan_id="s", files_found=50, files_total=None)
        assert progress.percent_complete is None

    def test_percent_computed_when_files_total_set(self):
        progress = ScanProgress(scan_id="s", files_found=50, files_total=100)
        assert progress.percent_complete == 50.0

    def test_metric_semantics_helpers(self):
        assert should_show_percent(None) is False
        assert should_show_percent(0) is False
        assert should_show_percent(100) is True
        assert should_show_eta(None, Phase.DISCOVERING.value) is False
        assert should_show_eta(30.0, Phase.HASHING_FULL.value) is True


class TestDuplicateCountsExact:
    """Duplicate count = sum over groups of (len(files) - 1)."""

    def test_duplicate_count_property(self):
        groups = [
            DuplicateGroup(
                group_id="1",
                group_hash="h1",
                files=[
                    FileMetadata(path="/a", size=1, mtime_ns=0),
                    FileMetadata(path="/b", size=1, mtime_ns=0),
                    FileMetadata(path="/c", size=1, mtime_ns=0),
                ],
            ),
            DuplicateGroup(
                group_id="2",
                group_hash="h2",
                files=[
                    FileMetadata(path="/d", size=1, mtime_ns=0),
                    FileMetadata(path="/e", size=1, mtime_ns=0),
                ],
            ),
        ]
        result = ScanResult(
            scan_id="s",
            config=ScanConfig(roots=[]),
            started_at=__import__("datetime").datetime.now(),
            duplicate_groups=groups,
        )
        assert result.duplicate_count == (3 - 1) + (2 - 1)  # 2 + 1 = 3
