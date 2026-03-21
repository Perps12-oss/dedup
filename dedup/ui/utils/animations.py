"""
Lightweight Tk-friendly easing helpers (no extra deps).

Respect AppSettings.reduced_motion: callers should skip animation when True.
"""

from __future__ import annotations

from typing import Callable, Optional


def ease_out_cubic(t: float) -> float:
    t = max(0.0, min(1.0, t))
    p = t - 1.0
    return p * p * p + 1.0


def ease_in_out_quad(t: float) -> float:
    t = max(0.0, min(1.0, t))
    if t < 0.5:
        return 2 * t * t
    return 1 - ((-2 * t + 2) ** 2) / 2


def animate_scalar(
    root,
    duration_ms: int,
    tick_ms: int,
    on_frame: Callable[[float], None],
    on_done: Optional[Callable[[], None]] = None,
    easing: Callable[[float], float] = ease_out_cubic,
) -> None:
    """Run on_frame(progress) where progress goes 0→1 over duration_ms."""
    if duration_ms <= 0 or tick_ms <= 0:
        on_frame(1.0)
        if on_done:
            on_done()
        return
    steps = max(1, duration_ms // tick_ms)
    start = [0]

    def _step() -> None:
        start[0] += 1
        t = start[0] / steps
        on_frame(easing(t))
        if start[0] < steps:
            root.after(tick_ms, _step)
        else:
            if on_done:
                on_done()

    _step()
