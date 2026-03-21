"""
Tests for PhaseTimeline key aliasing — ensures canonical and alias keys resolve.
"""

from __future__ import annotations

from dedup.ui.components.phase_timeline import _KEY_ALIASES, PHASE_LABELS


class TestPhaseTimelineAliases:
    def test_aliases_map_to_known_keys(self):
        known_keys = {k for k, _ in PHASE_LABELS}
        for alias, target in _KEY_ALIASES.items():
            assert target in known_keys, f"Alias {alias!r} maps to unknown key {target!r}"

    def test_canonical_keys_not_aliased(self):
        known_keys = {k for k, _ in PHASE_LABELS}
        for key in known_keys:
            assert key not in _KEY_ALIASES, f"Canonical key {key!r} should not appear in _KEY_ALIASES"

    def test_expected_aliases(self):
        assert _KEY_ALIASES["size_reduction"] == "size"
        assert _KEY_ALIASES["partial_hash"] == "partial"
        assert _KEY_ALIASES["full_hash"] == "full"
        assert _KEY_ALIASES["result_assembly"] == "results"
