"""
CustomTkinter Themes page — premium CEREBRO theme lab.

Features:
- 16 preset theme swatches with live preview
- Appearance mode (Dark/Light/System)
- Accent gradient editor with draggable stops
- WCAG contrast snapshot
- JSON import/export for theme bundles
"""

from __future__ import annotations

import json
import tkinter as tk
from datetime import datetime, timezone
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox
from typing import Callable, List, Optional, Tuple

import customtkinter as ctk

from ..theme.contrast import contrast_ratio, format_ratio, passes_aa_normal
from ..theme.gradients import color_at_gradient_position, draw_horizontal_multi_stop
from ..theme.theme_config import ThemeConfig
from ..theme.theme_manager import get_theme_manager
from ..theme.theme_registry import DEFAULT_THEME, THEMES, get_theme, get_theme_names

_MAX_STOPS = 8
_THEME_EXPORT_FORMAT = "cerebro_theme_config_v1"


class ThemesPageCTK(ctk.CTkFrame):
    """Premium theme lab with presets, gradient editor, and import/export."""

    def __init__(
        self,
        parent,
        *,
        on_theme_change: Optional[Callable[[str], None]] = None,
        on_preference_changed: Optional[Callable[[], None]] = None,
        on_toast: Optional[Callable[[str], None]] = None,
        **kwargs,
    ) -> None:
        super().__init__(parent, **kwargs)
        self._on_theme_change = on_theme_change
        self._on_preference_changed = on_preference_changed
        self._on_toast = on_toast
        self._tm = get_theme_manager()
        self._working_stops: List[Tuple[float, str]] = []
        self._current_theme_key = DEFAULT_THEME

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build()
        self._tm.subscribe(self._on_tokens_update)
        self._on_tokens_update(self._tm.tokens)

    def _build(self) -> None:
        self._panel_sections: list[ctk.CTkFrame] = []
        # Main scrollable container
        # Avoid "transparent" here: CTkScrollableFrame uses an internal Tk Canvas which can
        # repaint with raw Tk defaults (white) on hover/scroll unless we give it a real color.
        self._scroll = ctk.CTkScrollableFrame(self, fg_color=("#F6F7F9", "#0f131c"))
        self._scroll.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        self._scroll.grid_columnconfigure(0, weight=1)

        # Header
        self._build_header(self._scroll)

        # Content grid: left for presets, right for gradient + contrast
        content = ctk.CTkFrame(self._scroll, fg_color="transparent")
        content.grid(row=1, column=0, sticky="ew", pady=(20, 0))
        content.grid_columnconfigure(0, weight=3)
        content.grid_columnconfigure(1, weight=2)

        # Left column: Presets
        self._build_presets_section(content)

        # Right column: Appearance + Gradient + Contrast
        right = ctk.CTkFrame(content, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew", padx=(20, 0))
        right.grid_columnconfigure(0, weight=1)

        self._build_appearance_section(right)
        self._build_gradient_section(right)
        self._build_contrast_section(right)
        self._build_import_export(right)

    def _on_mode(self, value: str) -> None:
        """Handle appearance mode change."""
        ctk.set_appearance_mode(value)
        mode_map = {"Dark": "dark", "Light": "light", "System": "system"}
        self._tm.set_appearance_mode(mode_map.get(value, "dark"))

    def _build_header(self, parent: ctk.CTkFrame) -> None:
        header = ctk.CTkFrame(parent, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="Themes",
            font=ctk.CTkFont(size=28, weight="bold"),
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            header,
            text=(
                "Presets, accent, top-bar gradient, and contrast tools — saved with your UI preferences. "
                "Global shortcut: Ctrl+7."
            ),
            font=ctk.CTkFont(size=12),
            text_color=("gray40", "gray70"),
            wraplength=720,
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

    def _build_presets_section(self, parent: ctk.CTkFrame) -> None:
        """Build the preset swatches grid."""
        section = ctk.CTkFrame(parent, fg_color="transparent")
        section.grid(row=0, column=0, sticky="nsew")
        section.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            section,
            text="Presets",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).grid(row=0, column=0, sticky="w", pady=(0, 12))

        # Swatches grid (4 columns)
        swatches_frame = ctk.CTkFrame(section, fg_color="transparent")
        swatches_frame.grid(row=1, column=0, sticky="ew")

        self._swatch_buttons: dict[str, ctk.CTkButton] = {}
        col, row = 0, 0

        for key in get_theme_names():
            theme = get_theme(key)
            btn = ctk.CTkButton(
                swatches_frame,
                text=theme.get("name", key),
                width=140,
                height=40,
                corner_radius=8,
                fg_color=theme.get("accent_primary", "#3B8ED0"),
                hover_color=theme.get("accent_secondary", "#36719F"),
                text_color=theme.get("text_on_accent", "#FFFFFF"),
                command=lambda k=key: self._select_theme(k),
            )
            btn.grid(row=row, column=col, padx=6, pady=6)
            self._swatch_buttons[key] = btn

            col += 1
            if col >= 4:
                col = 0
                row += 1

    def _build_appearance_section(self, parent: ctk.CTkFrame) -> None:
        """Appearance mode selector."""
        section = ctk.CTkFrame(parent, fg_color=("gray95", "gray15"))
        self._panel_sections.append(section)
        section.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        section.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            section,
            text="Appearance",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(12, 8))

        mode_frame = ctk.CTkFrame(section, fg_color="transparent")
        mode_frame.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 12))

        ctk.CTkLabel(mode_frame, text="Mode").pack(side="left")

        mode = ctk.CTkSegmentedButton(
            mode_frame,
            values=["Dark", "Light", "System"],
            command=self._on_mode,
            width=200,
        )
        mode.pack(side="right")
        cur_raw = str(ctk.get_appearance_mode() or "dark")
        cur_map = {"dark": "Dark", "light": "Light", "system": "System"}
        mode.set(cur_map.get(cur_raw.lower(), "Dark"))

    def _build_gradient_section(self, parent: ctk.CTkFrame) -> None:
        """Accent gradient editor with canvas-based preview."""
        section = ctk.CTkFrame(parent, fg_color=("gray95", "gray15"))
        self._panel_sections.append(section)
        section.grid(row=1, column=0, sticky="ew", pady=(0, 16))
        section.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            section,
            text="Accent Gradient",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(12, 4))

        ctk.CTkLabel(
            section,
            text="Used for accent bars and highlights.",
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray70"),
        ).grid(row=1, column=0, sticky="w", padx=16, pady=(0, 8))

        # Gradient preview canvas
        # NOTE: Tk `Canvas` does not understand "transparent" as a color name.
        # Use the CTk frame's resolved `fg_color` so Tk gets a valid color string.
        canvas_bg = section._apply_appearance_mode(section._fg_color)
        self._grad_canvas = tk.Canvas(
            section,
            height=56,
            highlightthickness=0,
            borderwidth=0,
            bg=canvas_bg,
        )
        self._grad_canvas.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 8))
        self._grad_canvas.bind("<Configure>", self._paint_gradient)

        # Stop controls
        self._stops_frame = ctk.CTkFrame(section, fg_color="transparent")
        self._stops_frame.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 8))

        # Action buttons
        btn_frame = ctk.CTkFrame(section, fg_color="transparent")
        btn_frame.grid(row=4, column=0, sticky="ew", padx=16, pady=(0, 12))

        ctk.CTkButton(
            btn_frame,
            text="Add Stop",
            width=90,
            height=28,
            command=self._add_gradient_stop,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_frame,
            text="Apply",
            width=90,
            height=28,
            fg_color=("#3B8ED0", "#1F6AA5"),
            command=self._apply_gradient,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_frame,
            text="Reset",
            width=90,
            height=28,
            fg_color=("gray70", "gray30"),
            command=self._reset_gradient,
        ).pack(side="left")

        self._working_stops = self._load_editor_stops()
        self._rebuild_stop_rows()

    def _build_contrast_section(self, parent: ctk.CTkFrame) -> None:
        """WCAG contrast snapshot."""
        section = ctk.CTkFrame(parent, fg_color=("gray95", "gray15"))
        section.grid(row=2, column=0, sticky="ew", pady=(0, 16))
        section.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            section,
            text="Contrast (WCAG)",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(12, 8))

        self._contrast_lbl = ctk.CTkLabel(
            section,
            text="",
            font=ctk.CTkFont(family="Consolas", size=11),
            justify="left",
        )
        self._contrast_lbl.grid(row=1, column=0, sticky="w", padx=16, pady=(0, 12))

    def _build_import_export(self, parent: ctk.CTkFrame) -> None:
        """Import/export theme bundles."""
        section = ctk.CTkFrame(parent, fg_color=("gray95", "gray15"))
        self._panel_sections.append(section)
        section.grid(row=3, column=0, sticky="ew")
        section.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            section,
            text="Import / Export",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(12, 12))

        btn_frame = ctk.CTkFrame(section, fg_color="transparent")
        btn_frame.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 12))

        ctk.CTkButton(
            btn_frame,
            text="Export JSON…",
            width=120,
            command=self._export_theme_json,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_frame,
            text="Import JSON…",
            width=120,
            command=self._import_theme_json,
        ).pack(side="left")

        ctk.CTkLabel(
            section,
            text="Export includes theme key, gradient stops, and UI flags.",
            font=ctk.CTkFont(size=10),
            text_color=("gray50", "gray60"),
        ).grid(row=2, column=0, sticky="w", padx=16, pady=(0, 12))

    def _paint_gradient(self, event=None) -> None:
        """Paint the gradient preview on canvas."""
        w = max(2, self._grad_canvas.winfo_width())
        h = max(2, self._grad_canvas.winfo_height())
        if len(self._working_stops) >= 2:
            draw_horizontal_multi_stop(self._grad_canvas, w, h, self._working_stops, segments=120)

    def _rebuild_stop_rows(self) -> None:
        """Rebuild the gradient stop control rows."""
        for w in self._stops_frame.winfo_children():
            w.destroy()

        for i, (pos, col) in enumerate(self._working_stops):
            row = ctk.CTkFrame(self._stops_frame, fg_color="transparent")
            row.pack(fill="x", pady=2)

            # Position spinbox (using tk.Spinbox within CTK)
            pos_frame = ctk.CTkFrame(row, fg_color="transparent", width=80)
            pos_frame.pack(side="left")
            pos_frame.pack_propagate(False)

            var = tk.StringVar(value=f"{pos:.3f}")
            sp = tk.Spinbox(
                pos_frame,
                from_=0.0,
                to=1.0,
                increment=0.01,
                textvariable=var,
                width=8,
                command=lambda idx=i, v=var: self._spin_pos_commit(idx, v),
            )
            sp.pack(fill="x")
            sp.bind("<FocusOut>", lambda e, idx=i, v=var: self._spin_pos_commit(idx, v))
            sp.bind("<Return>", lambda e, idx=i, v=var: self._spin_pos_commit(idx, v))

            # Color chip
            chip = tk.Label(
                row,
                text="   ",
                width=3,
                background=col,
                relief="solid",
                borderwidth=1,
            )
            chip.pack(side="left", padx=(8, 8))

            # Color picker button
            ctk.CTkButton(
                row,
                text="Color",
                width=60,
                height=24,
                command=lambda idx=i: self._pick_stop_color(idx),
            ).pack(side="left", padx=(0, 4))

            # Remove button (disabled if only 2 stops)
            ctk.CTkButton(
                row,
                text="×",
                width=28,
                height=24,
                fg_color=("#E74C3C", "#C0392B"),
                hover_color=("#C0392B", "#A93226"),
                command=lambda idx=i: self._remove_stop(idx),
            ).pack(side="right")

    def _spin_pos_commit(self, index: int, var: tk.StringVar) -> None:
        try:
            v = float(var.get())
            v = max(0.0, min(1.0, v))
        except (TypeError, ValueError):
            v = self._working_stops[index][0]
            var.set(f"{v:.3f}")
            return

        _, c = self._working_stops[index]
        self._working_stops[index] = (v, c)
        var.set(f"{v:.3f}")
        self._paint_gradient()

    def _pick_stop_color(self, index: int) -> None:
        if index >= len(self._working_stops):
            return
        pos, col = self._working_stops[index]
        rgb, hx = colorchooser.askcolor(color=col, parent=self.winfo_toplevel(), title="Stop Color")
        if hx:
            self._working_stops[index] = (pos, hx)
            self._rebuild_stop_rows()
            self._paint_gradient()

    def _remove_stop(self, index: int) -> None:
        if len(self._working_stops) <= 2 or index < 0 or index >= len(self._working_stops):
            return
        del self._working_stops[index]
        self._rebuild_stop_rows()
        self._paint_gradient()

    def _add_gradient_stop(self) -> None:
        if len(self._working_stops) >= _MAX_STOPS:
            self._notify_toast("Maximum 8 stops allowed")
            return
        srt = sorted(self._working_stops, key=lambda x: x[0])
        mid_c = color_at_gradient_position(srt, 0.5)
        self._working_stops.append((0.5, mid_c))
        self._rebuild_stop_rows()
        self._paint_gradient()

    def _apply_gradient(self) -> None:
        srt = sorted(self._working_stops, key=lambda x: x[0])
        if len(srt) < 2:
            messagebox.showwarning("Gradient", "Add at least two color stops.")
            return

        # Store in theme manager
        self._tm.set_custom_gradient_stops(srt)
        self._notify_toast("Accent gradient applied")

        if self._on_preference_changed:
            try:
                self._on_preference_changed()
            except Exception:
                pass

    def _reset_gradient(self) -> None:
        self._tm.clear_custom_gradient_stops()
        self._working_stops = self._load_editor_stops()
        self._rebuild_stop_rows()
        self._paint_gradient()
        self._notify_toast("Using preset gradient")

        if self._on_preference_changed:
            try:
                self._on_preference_changed()
            except Exception:
                pass

    def _load_editor_stops(self) -> List[Tuple[float, str]]:
        """Load gradient stops from theme manager or use defaults."""
        custom = self._tm.get_custom_gradient_stops()
        if custom:
            return list(custom)

        tokens = self._tm.tokens
        gs = str(tokens.get("gradient_start", "#1f6feb"))
        ge = str(tokens.get("gradient_end", "#58a6ff"))
        gm = str(tokens.get("gradient_mid", color_at_gradient_position([(0.0, gs), (1.0, ge)], 0.5)))
        return [(0.0, gs), (0.5, gm), (1.0, ge)]

    def _select_theme(self, key: str) -> None:
        """Select a preset theme."""
        self._current_theme_key = key

        # Update visual selection
        for k, btn in self._swatch_buttons.items():
            if k == key:
                btn.configure(
                    border_width=2,
                    border_color=("#FFFFFF", "#FFFFFF"),
                )
            else:
                btn.configure(border_width=0)

        # Apply theme
        self._tm.apply_theme(key)

        if self._on_theme_change:
            try:
                self._on_theme_change(key)
            except Exception:
                pass

        # Reset gradient to theme defaults
        if not self._tm.get_custom_gradient_stops():
            self._working_stops = self._load_editor_stops()
            self._rebuild_stop_rows()
            self._paint_gradient()

        self._notify_toast(f"Applied: {THEMES[key].get('name', key)}")

    def _on_tokens_update(self, tokens: dict) -> None:
        """Handle theme token updates."""
        self._refresh_contrast(tokens)
        if not self._tm.get_custom_gradient_stops():
            self._working_stops = self._load_editor_stops()
            self._rebuild_stop_rows()
        self._paint_gradient()

    def _refresh_contrast(self, tokens: dict) -> None:
        """Update contrast display."""
        bg = tokens.get("bg_base", "#000000")
        fg = tokens.get("text_primary", "#ffffff")
        acc = tokens.get("accent_primary", "#888888")

        r1 = contrast_ratio(fg, bg)
        r2 = contrast_ratio(acc, bg)
        ok1 = "✓ AA" if passes_aa_normal(r1) else "✗ below AA"
        ok2 = "✓ AA" if passes_aa_normal(r2) else "✗ below AA"

        lines = (
            f"Text/BG:   {format_ratio(r1)}  ({ok1})",
            f"Accent/BG: {format_ratio(r2)}  ({ok2})",
        )
        self._contrast_lbl.configure(text="\n".join(lines))

    def _export_theme_json(self) -> None:
        """Export current theme configuration to JSON."""
        path = filedialog.asksaveasfilename(
            parent=self.winfo_toplevel(),
            title="Export Theme",
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return

        tc = ThemeConfig(
            theme_key=self._current_theme_key,
            custom_gradient_stops=self._tm.get_custom_gradient_stops(),
        )

        payload = {
            "export_format": _THEME_EXPORT_FORMAT,
            "exported_at_utc": datetime.now(timezone.utc).isoformat(),
            "theme_key": self._current_theme_key,
            "theme_config": tc.to_dict(),
        }

        try:
            Path(path).write_text(
                json.dumps(payload, indent=2, default=lambda o: list(o) if isinstance(o, tuple) else o),
                encoding="utf-8",
            )
            messagebox.showinfo("Export", f"Theme saved to:\n{path}")
            self._notify_toast("Theme exported")
        except OSError as ex:
            messagebox.showerror("Export failed", str(ex))

    def _import_theme_json(self) -> None:
        """Import theme configuration from JSON."""
        path = filedialog.askopenfilename(
            parent=self.winfo_toplevel(),
            title="Import Theme",
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

        if data.get("export_format") != _THEME_EXPORT_FORMAT:
            messagebox.showerror("Import failed", f"Expected format: {_THEME_EXPORT_FORMAT!r}")
            return

        key = str(data.get("theme_key") or "").strip()
        if not key or key not in THEMES:
            messagebox.showerror("Import failed", f"Unknown theme_key: {key!r}")
            return

        tc = ThemeConfig.from_dict(dict(data.get("theme_config") or {}))

        # Apply theme
        self._select_theme(key)

        # Apply custom gradient if present
        if tc.custom_gradient_stops:
            self._tm.set_custom_gradient_stops(tc.custom_gradient_stops)
            self._working_stops = list(tc.custom_gradient_stops)
            self._rebuild_stop_rows()
            self._paint_gradient()

        messagebox.showinfo("Import", f"Applied theme: {THEMES[key].get('name', key)}")
        self._notify_toast("Theme imported")

    def _notify_toast(self, msg: str) -> None:
        if self._on_toast:
            try:
                self._on_toast(msg)
            except Exception:
                pass

    def set_current_theme(self, key: str) -> None:
        """Set the current theme externally."""
        self._current_theme_key = key
        for k, btn in self._swatch_buttons.items():
            if k == key:
                btn.configure(
                    border_width=2,
                    border_color=("#FFFFFF", "#FFFFFF"),
                )
            else:
                btn.configure(border_width=0)

    def apply_theme_tokens(self, tokens: dict) -> None:
        panel = str(tokens.get("bg_panel", "#161b22"))
        bg = str(tokens.get("bg_base", "#0f131c"))
        for f in self._panel_sections:
            f.configure(fg_color=panel)
        if hasattr(self, "_scroll"):
            self._scroll.configure(fg_color=("#F6F7F9", bg))
        if hasattr(self, "_grad_canvas"):
            parent = self._grad_canvas.master
            if parent is not None and hasattr(parent, "_apply_appearance_mode"):
                cb = parent._apply_appearance_mode(parent._fg_color)
                self._grad_canvas.configure(bg=cb)
            self._paint_gradient()

    def on_show(self) -> None:
        """Called when page becomes visible."""
        self._working_stops = self._load_editor_stops()
        self._rebuild_stop_rows()
        self._paint_gradient()
        self._on_tokens_update(self._tm.tokens)
