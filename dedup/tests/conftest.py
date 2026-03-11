"""
Pytest fixtures for DEDUP tests.
Provides temporary directories and minimal scan configs.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

# Ensure dedup package is importable (project root = parent of dedup folder)
import sys
_dedup_root = Path(__file__).resolve().parent.parent
_project_root = _dedup_root.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


@pytest.fixture
def temp_dir():
    """Temporary directory; cleaned up after test."""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def sample_roots(temp_dir):
    """Path to a temp dir for scan roots."""
    return temp_dir
