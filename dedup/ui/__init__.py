"""
DEDUP UI - Minimal user interface.

A clean, minimal interface with only essential screens:
- Home / Scan Setup
- Live Scan
- Results / Review
- History

Uses tkinter (built into Python) for zero external dependencies.
"""

from .app import DedupApp
from .home_frame import HomeFrame
from .scan_frame import ScanFrame
from .results_frame import ResultsFrame
from .history_frame import HistoryFrame

__all__ = [
    "DedupApp",
    "HomeFrame",
    "ScanFrame", 
    "ResultsFrame",
    "HistoryFrame",
]
