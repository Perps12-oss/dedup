"""
Themes page — presets, live preview swatches, WCAG contrast summary,
accent-bar multi-stop gradient editor, JSON import/export.
"""

from __future__ import annotations

import json
import tkinter as tk
from datetime import datetime, timezone
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, ttk
from typing import Callable, List, Optional, Tuple

from ..theme.contrast import contrast_ratio, format_ratio, passes_aa_normal
from ..theme.design_system import font_tuple
from ..theme.gradients import color_at_gradient_position, draw_horizontal_multi_stop
from ..theme.theme_config import ThemeConfig
from ..theme.theme_manager import get_theme_manager, parse_gradient_stops_from_raw
from ..theme.theme_preview import ThemeSwatchGrid
from ..theme.theme_registry import THEMES, get_theme
from ..utils.ui_state import UIState


def _S(n: int) -> int:
    return n * 4


THEME_EXPORT_FORMAT = "cerebro_theme_config_v1"

_MAX_STOPS = 8


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
        self.rowconfigure(0, weight=1)
        self._working_stops: List[Tuple[float, str]] = []
        self._build()
        self._tm.subscribe(self._on_tokens_update)
        self._on_tokens_update(self._tm.tokens)

    def _build(self) -> None:
        pad = _S(6)
        outer = ttk.Frame(self, padding=(pad, pad, pad, pad))
        outer.grid(row=0, column=0, sticky="nsew")
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

        gf = ttk.LabelFrame(outer, text="Top accent bar gradient", padding=_S(2))
        gf.grid(row=4, column=0, sticky="ew", pady=(_S(4), 0))
        self._grad_preview = tk.Canvas(
            gf,
            height=32,
            highlightthickness=1,
            highlightbackground="#888888",
        )
        self._grad_preview.pack(fill="x", pady=(0, _S(2)))
        self._grad_preview.bind("<Configure>", lambda e: self._refresh_gradient_preview_canvas())
        hint = ttk.Label(
            gf,
            text="Positions are 0 (left) → 1 (right). At least two stops. Applies to the thin strip under the top bar.",
            style="Muted.TLabel",
            font=font_tuple("caption"),
            wraplength=720,
            justify="left",
        )
        hint.pack(anchor="w", pady=(0, _S(2)))
        self._stops_inner = ttk.Frame(gf)
        self._stops_inner.pack(fill="x")
        gbtns = ttk.Frame(gf)
        gbtns.pack(fill="x", pady=(_S(2), 0))
        ttk.Button(gbtns, text="Add stop", style="Ghost.TButton", command=self._add_gradient_stop).pack(
            side="left", padx=(0, _S(2))
        )
        ttk.Button(gbtns, text="Apply", style="Accent.TButton", command=self._apply_gradient).pack(
            side="left", padx=(0, _S(2))
        )
        ttk.Button(gbtns, text="Reset to preset", style="Ghost.TButton", command=self._reset_gradient).pack(side="left")

        self._working_stops = self._load_editor_stops()
        self._rebuild_stop_rows()

        io = ttk.LabelFrame(outer, text="Import / export", padding=_S(2))
        io.grid(row=5, column=0, sticky="ew", pady=(_S(4), 0))
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
            text="Export includes preset key, ThemeConfig (incl. custom gradient stops), and motion/contrast UI flags. "
            "Import applies a known preset, optional gradient stops, and flags.",
            style="Muted.TLabel",
            font=font_tuple("caption"),
            wraplength=720,
            justify="left",
        )
        note.grid(row=6, column=0, sticky="w", pady=(_S(3), 0))

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
            custom_gradient_stops=parse_gradient_stops_from_raw(s.custom_gradient_stops),
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
        if tc.custom_gradient_stops:
            s.custom_gradient_stops = [[float(p), str(c)] for p, c in tc.custom_gradient_stops]
        else:
            s.custom_gradient_stops = None
        try:
            self._state.save()
        except Exception:
            pass
        self._on_theme_change(key)
        self._swatches.set_current(key)
        self._working_stops = self._load_editor_stops()
        self._rebuild_stop_rows()
        self._refresh_gradient_preview_canvas()
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
        if not self._state.settings.custom_gradient_stops:
            self._working_stops = self._defaults_from_theme_key(key)
            self._rebuild_stop_rows()
            self._refresh_gradient_preview_canvas()

    def _on_tokens_update(self, tokens: dict) -> None:
        self._refresh_contrast(tokens)
        if not self._state.settings.custom_gradient_stops:
            self._working_stops = self._defaults_from_tokens(tokens)
            self._rebuild_stop_rows()
        self._refresh_gradient_preview_canvas()

    def _defaults_from_theme_key(self, key: str) -> List[Tuple[float, str]]:
        t = get_theme(key)
        return self._defaults_from_tokens(t)

    def _defaults_from_tokens(self, t: dict) -> List[Tuple[float, str]]:
        gs = str(t.get("gradient_start", "#1f6feb"))
        ge = str(t.get("gradient_end", "#58a6ff"))
        gm = str(t.get("gradient_mid", color_at_gradient_position([(0.0, gs), (1.0, ge)], 0.5)))
        return [(0.0, gs), (0.5, gm), (1.0, ge)]

    def _load_editor_stops(self) -> List[Tuple[float, str]]:
        parsed = parse_gradient_stops_from_raw(self._state.settings.custom_gradient_stops)
        if parsed:
            return list(parsed)
        return self._defaults_from_tokens(self._tm.tokens)

    def _rebuild_stop_rows(self) -> None:
        for w in self._stops_inner.winfo_children():
            w.destroy()
        for i in range(len(self._working_stops)):
            pos, col = self._working_stops[i]
            row = ttk.Frame(self._stops_inner)
            row.pack(fill="x", pady=1)
            ttk.Label(row, text="pos", width=4).pack(side="left")
            var = tk.StringVar(value=f"{pos:.4f}")
            sp = tk.Spinbox(
                row,
                from_=0.0,
                to=1.0,
                increment=0.01,
                textvariable=var,
                width=8,
                command=lambda idx=i, v=var: self._spin_pos_commit(idx, v),
            )
            sp.pack(side="left", padx=(0, _S(2)))
            sp.bind("<FocusOut>", lambda e, idx=i, v=var: self._spin_pos_commit(idx, v))
            sp.bind("<Return>", lambda e, idx=i, v=var: self._spin_pos_commit(idx, v))
            chip = tk.Label(row, text="   ", width=4, background=col, relief="solid", borderwidth=1)
            chip.pack(side="left", padx=(0, _S(2)))
            ttk.Button(row, text="Color…", style="Ghost.TButton", command=lambda idx=i: self._pick_stop_color(idx)).pack(
                side="left", padx=(0, _S(2))
            )
            rm_state = "disabled" if len(self._working_stops) <= 2 else "normal"
            ttk.Button(
                row,
                text="Remove",
                style="Ghost.TButton",
                command=lambda idx=i: self._remove_stop(idx),
                state=rm_state,
            ).pack(side="left")

    def _spin_pos_commit(self, index: int, var: tk.StringVar) -> None:
        if index >= len(self._working_stops):
            return
        try:
            v = float(var.get())
            v = max(0.0, min(1.0, v))
        except (TypeError, ValueError):
            v = self._working_stops[index][0]
            var.set(f"{v:.4f}")
            return
        _, c = self._working_stops[index]
        self._working_stops[index] = (v, c)
        var.set(f"{v:.4f}")
        self._refresh_gradient_preview_canvas()

    def _pick_stop_color(self, index: int) -> None:
        if index >= len(self._working_stops):
            return
        pos, col = self._working_stops[index]
        rgb, hx = colorchooser.askcolor(color=col, parent=self.winfo_toplevel(), title="Stop color")
        if hx:
            self._working_stops[index] = (pos, hx)
            self._rebuild_stop_rows()
            self._refresh_gradient_preview_canvas()

    def _remove_stop(self, index: int) -> None:
        if len(self._working_stops) <= 2 or index < 0 or index >= len(self._working_stops):
            return
        del self._working_stops[index]
        self._rebuild_stop_rows()
        self._refresh_gradient_preview_canvas()

    def _add_gradient_stop(self) -> None:
        if len(self._working_stops) >= _MAX_STOPS:
            self._notify_toast("Maximum stops reached")
            return
        srt = sorted(self._working_stops, key=lambda x: x[0])
        mid_c = color_at_gradient_position(srt, 0.5)
        self._working_stops.append((0.5, mid_c))
        self._rebuild_stop_rows()
        self._refresh_gradient_preview_canvas()

    def _apply_gradient(self) -> None:
        srt = sorted(self._working_stops, key=lambda x: x[0])
        if len(srt) < 2:
            messagebox.showwarning("Gradient", "Add at least two color stops.")
            return
        self._state.settings.custom_gradient_stops = [[float(p), str(c)] for p, c in srt]
        try:
            self._state.save()
        except Exception:
            pass
        self._on_theme_change(self._state.settings.theme_key)
        self._notify_toast("Accent gradient applied")

    def _reset_gradient(self) -> None:
        self._state.settings.custom_gradient_stops = None
        try:
            self._state.save()
        except Exception:
            pass
        self._on_theme_change(self._state.settings.theme_key)
        self._working_stops = self._load_editor_stops()
        self._rebuild_stop_rows()
        self._refresh_gradient_preview_canvas()
        self._notify_toast("Using preset gradient")

    def _refresh_gradient_preview_canvas(self) -> None:
        try:
            w = max(2, self._grad_preview.winfo_width())
            h = max(2, self._grad_preview.winfo_height())
        except Exception:
            return
        srt = sorted(self._working_stops, key=lambda x: x[0])
        if len(srt) >= 2:
            draw_horizontal_multi_stop(self._grad_preview, w, h, srt)
        else:
            self._grad_preview.delete("gradient")

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
        self._working_stops = self._load_editor_stops()
        self._rebuild_stop_rows()
        self._on_tokens_update(self._tm.tokens)
