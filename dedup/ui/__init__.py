"""
CEREBRO Dedup Engine — Modern-classic operations UI.

Shell: fixed nav rail, top command bar, status strip, insight drawer.
Pages: Mission, Scan, Review, History, Diagnostics, Settings.
Themes: 15 multigradient themes via semantic token system.
"""

from .app import CerebroApp, DedupApp, main

__all__ = ["CerebroApp", "DedupApp", "main"]
