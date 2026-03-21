"""
Themes page — presets, live preview swatches, WCAG contrast summary, JSON import/export.

Gradient editor (multi-stop UI) remains future work; stops round-trip in JSON for forward compatibility.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Optional

from ..theme.contrast import contrast_ratio, format_ratio, passes_aa_normal
from ..theme.design_system import font_tuple
from ..theme.theme_config import ThemeConfig
from ..theme.theme_manager import get_theme_manager
from ..theme.theme_preview import ThemeSwatchGrid
from ..theme.theme_registry import THEMES
from ..utils.ui_state import UIState


def _S(n: int) -> int:
    return n * 4


THEME_EXPORT_FORMAT = "cerebro_theme_config_v1"


class ThemePage(ttk.Frame):
    """Dedicated surface for theme exploration (beyond TopBar combo)."""

    def __init__(
        self,
        parent,
        *,
        state: UIState,
        on_theme_change: Callable[[str], None],
        on_preference_changed: Optional[Callable[[], None]] = None,
        on_toast: Optional[Callable[[str], None]] = None,
        **kwargs,
    ) -> None:
        super().__init__(parent, **kwargs)
        self._state = state
        self._on_theme_change = on_theme_change
        self._on_preference_changed = on_preference_changed
        self._on_toast = on_toast
        self._tm = get_theme_manager()
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self._build()
        self._tm.subscribe(self._refresh_contrast)
        self._refresh_contrast(self._tm.tokens)

    def _build(self) -> None:
        pad = _S(6)
        outer = ttk.Frame(self, padding=(pad, pad, pad, pad))
        outer.grid(row=0, column=0, rowspan=2, sticky="nsew")
        outer.columnconfigure(0, weight=1)

        title = ttk.Label(outer, text="Themes", font=font_tuple("page_title"))
        title.grid(row=0, column=0, sticky="w")
        sub = ttk.Label(
            outer,
            text="Choose a preset. Contrast checks use WCAG relative luminance (informative, not legal advice).",
            style="Muted.TLabel",
            font=font_tuple("page_subtitle"),
            wraplength=720,
            justify="left",
        )
        sub.grid(row=1, column=0, sticky="w", pady=(_S(1), _S(4)))

        sw_frame = ttk.LabelFrame(outer, text="Presets (15 + CEREBRO Noir)", padding=_S(2))
        sw_frame.grid(row=2, column=0, sticky="ew", pady=(0, _S(4)))
        self._swatches = ThemeSwatchGrid(
            sw_frame,
            on_select=self._select_theme,
            current_key=self._state.settings.theme_key,
        )
        self._swatches.pack(fill="x")

        cf = ttk.LabelFrame(outer, text="Contrast snapshot (current theme)", padding=_S(2))
        cf.grid(row=3, column=0, sticky="ew")
        self._contrast_lbl = ttk.Label(
            cf,
            text="",
            style="Muted.TLabel",
            font=("Consolas", 10),
            justify="left",
        )
        self._contrast_lbl.pack(anchor="w")

        io = ttk.LabelFrame(outer, text="Import / export", padding=_S(2))
        io.grid(row=4, column=0, sticky="ew", pady=(_S(4), 0))
        ior = ttk.Frame(io)
        ior.pack(fill="x")
        ttk.Button(
            ior,
            text="Export theme JSON…",
            style="Ghost.TButton",
            command=self._export_theme_json,
        ).pack(side="left", padx=(0, _S(2)))
        ttk.Button(
            ior,
            text="Import theme JSON…",
            style="Ghost.TButton",
            command=self._import_theme_json,
        ).pack(side="left")

        note = ttk.Label(
            outer,
            text="Export includes preset key, ThemeConfig fields, and motion/contrast UI flags. "
            "Import applies a known preset and optional flags. Multi-stop gradient editor UI is still planned.",
            style="Muted.TLabel",
            font=font_tuple("caption"),
            wraplength=720,
            justify="left",
        )
        note.grid(row=5, column=0, sticky="w", pady=(_S(3), 0))

    def _notify_toast(self, msg: str) -> None:
        if self._on_toast:
            try:
                self._on_toast(msg)
            except Exception:
                pass

    def _export_theme_json(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self.winfo_toplevel(),
            title="Export theme",
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        s = self._state.settings
        tc = ThemeConfig(
            theme_key=s.theme_key,
            reduced_motion=s.reduced_motion,
        )
        payload = {
            "export_format": THEME_EXPORT_FORMAT,
            "exported_at_utc": datetime.now(timezone.utc).isoformat(),
            "theme_key": s.theme_key,
            "theme_config": tc.to_dict(),
            "ui": {
                "reduced_motion": s.reduced_motion,
                "reduced_gradients": s.reduced_gradients,
                "high_contrast": s.high_contrast,
            },
        }
        try:
            Path(path).write_text(
                json.dumps(payload, indent=2, default=lambda o: list(o) if isinstance(o, tuple) else o),
                encoding="utf-8",
            )
            messagebox.showinfo("Export", f"Theme bundle saved to:\n{path}")
            self._notify_toast("Theme bundle exported")
        except OSError as ex:
            messagebox.showerror("Export failed", str(ex))

    def _import_theme_json(self) -> None:
        path = filedialog.askopenfilename(
            parent=self.winfo_toplevel(),
            title="Import theme",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            raw = Path(path).read_text(encoding="utf-8")
            data = json.loads(raw)
        except (OSError, json.JSONDecodeError) as ex:
            messagebox.showerror("Import failed", str(ex))
            return
        if data.get("export_format") != THEME_EXPORT_FORMAT:
            messagebox.showerror(
                "Import failed",
                f"Expected export_format {THEME_EXPORT_FORMAT!r}.",
            )
            return
        key = str(data.get("theme_key") or "").strip()
        if not key or key not in THEMES:
            messagebox.showerror("Import failed", f"Unknown or missing theme_key: {key!r}")
            return
        tc = ThemeConfig.from_dict(dict(data.get("theme_config") or {}))
        ui = dict(data.get("ui") or {})
        s = self._state.settings
        s.theme_key = key
        s.reduced_motion = bool(ui.get("reduced_motion", tc.reduced_motion))
        s.reduced_gradients = bool(ui.get("reduced_gradients", s.reduced_gradients))
        s.high_contrast = bool(ui.get("high_contrast", s.high_contrast))
        try:
            self._state.save()
        except Exception:
            pass
        self._on_theme_change(key)
        self._swatches.set_current(key)
        if self._on_preference_changed:
            try:
                self._on_preference_changed()
            except Exception:
                pass
        messagebox.showinfo("Import", f"Applied theme preset: {THEMES[key].get('name', key)}")

    def _select_theme(self, key: str) -> None:
        self._state.settings.theme_key = key
        self._on_theme_change(key)
        self._swatches.set_current(key)

    def _refresh_contrast(self, tokens: dict) -> None:
        bg = tokens.get("bg_base", "#000000")
        fg = tokens.get("text_primary", "#ffffff")
        acc = tokens.get("accent_primary", "#888888")
        r1 = contrast_ratio(fg, bg)
        r2 = contrast_ratio(acc, bg)
        ok1 = "AA text" if passes_aa_normal(r1) else "below AA normal"
        ok2 = "AA text" if passes_aa_normal(r2) else "below AA normal"
        lines = (
            f"text_primary / bg_base   {format_ratio(r1)}  ({ok1})",
            f"accent_primary / bg_base {format_ratio(r2)}  ({ok2})",
        )
        self._contrast_lbl.configure(text="\n".join(lines))

    def on_show(self) -> None:
        self._swatches.set_current(self._state.settings.theme_key)
        self._refresh_contrast(self._tm.tokens)
