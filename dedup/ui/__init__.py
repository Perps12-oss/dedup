"""
CEREBRO Dedup Engine — Modern-classic operations UI.

Shell: fixed nav rail, top command bar, status strip, insight drawer.
Pages: Mission, Scan, Review, History, Diagnostics, Settings.
Themes: 15 multigradient themes via semantic token system.
"""

"""
IMPORTANT:
This package is imported by both the classic ttk backend and the CustomTkinter (CTK) backend.
The classic backend imports ttkbootstrap, which can monkey-patch tkinter widgets globally.

To prevent those side effects from impacting the CTK backend, keep this module import-light
and avoid importing the classic app at module import time.
"""

__all__ = ["CerebroApp", "DedupApp", "main"]


def CerebroApp(*args, **kwargs):  # type: ignore[misc]
    from .app import CerebroApp as _CerebroApp

    return _CerebroApp(*args, **kwargs)


def DedupApp(*args, **kwargs):  # type: ignore[misc]
    from .app import DedupApp as _DedupApp

    return _DedupApp(*args, **kwargs)


def main(*args, **kwargs):  # type: ignore[misc]
    from .app import main as _main

    return _main(*args, **kwargs)
