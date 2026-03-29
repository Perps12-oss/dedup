"""
Pytest fixtures for DEDUP tests.
Provides temporary directories and minimal scan configs.
"""

from __future__ import annotations

# Ensure dedup package is importable (project root = parent of dedup folder)
import sys
import tempfile
from pathlib import Path

import pytest

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


@pytest.fixture
def tk_root():
    """Minimal Tk root for UIStateStore / CTK tests (headless CI may skip)."""
    import tkinter as tk

    try:
        root = tk.Tk()
    except Exception as e:
        pytest.skip(f"Tk unavailable: {e}")
    root.withdraw()
    yield root
    try:
        root.destroy()
    except Exception:
        pass
