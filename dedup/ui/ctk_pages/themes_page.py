"""
CustomTkinter Themes page — premium CEREBRO theme lab.

Features:
- 16 preset theme swatches with live preview
- Appearance mode (Dark/Light/System)
- Accent gradient editor with draggable stops
- WCAG contrast snapshot
- JSON import/export for theme bundles

REFACTORED: Visual redesign with modern aesthetics while preserving all APIs.
- Enhanced glassmorphism-inspired panels
- Improved gradient editor with better visual feedback
- Modern swatch grid with hover states
- Consistent design token usage
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
from .design_tokens import get_theme_colors
from .ui_utils import resolve_color, safe_callback

_MAX_STOPS = 8
_THEME_EXPORT_FORMAT = "cerebro_theme_config_v1"


class ThemesPageCTK(ctk.CTkFrame):
    """Premium theme lab with presets, gradient editor, and import/export."""

    # ══════════════════════════════════════════════════════════════════════════
    # PUBLIC API - PRESERVED FROM ORIGINAL
    # ══════════════════════════════════════════════════════════════════════════

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

        self._tokens = get_theme_colors()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build()
        self._tm.subscribe(self._on_tokens_update)
        self._on_tokens_update(self._tm.tokens)

    def set_current_theme(self, key: str) -> None:
        """Set the current theme externally. API UNCHANGED."""
        self._current_theme_key = key
        for k, btn in self._swatch_buttons.items():
            if k == key:
                btn.configure(
                    border_width=3,
                    border_color=self._tokens["accent_primary"],
                )
            else:
                btn.configure(border_width=0)

    def apply_theme_tokens(self, tokens: dict) -> None:
        """Apply theme tokens to the page. API UNCHANGED."""
        panel = str(tokens.get("bg_panel", "#161b22"))
        bg = str(tokens.get("bg_base", "#0f131c"))
        for f in self._panel_sections:
            f.configure(fg_color=panel)
        if hasattr(self, "_scroll"):
            self._scroll.configure(fg_color=bg)
        if hasattr(self, "_grad_canvas"):
            canvas_bg = resolve_color(self._tokens["bg_panel"])
            self._grad_canvas.configure(bg=canvas_bg)
            self._paint_gradient()

    def on_show(self) -> None:
        """Called when page becomes visible. API UNCHANGED."""
        self._working_stops = self._load_editor_stops()
        self._rebuild_stop_rows()
        self._paint_gradient()
        self._on_tokens_update(self._tm.tokens)

    # ══════════════════════════════════════════════════════════════════════════
    # PRIVATE UI BUILD METHODS - REFACTORED FOR VISUAL ENHANCEMENT
    # ══════════════════════════════════════════════════════════════════════════

    def _build(self) -> None:
        self._panel_sections: list[ctk.CTkFrame] = []

        # Main scrollable container with modern styling
        self._scroll = ctk.CTkScrollableFrame(
            self,
            fg_color=self._tokens["bg_base"],
            corner_radius=0,
        )
        self._scroll.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        self._scroll.grid_columnconfigure(0, weight=1)

        # Header
        self._build_header(self._scroll)

        # Content grid: left for presets, right for gradient + contrast
        content = ctk.CTkFrame(self._scroll, fg_color="transparent")
        content.grid(row=1, column=0, sticky="ew", pady=(24, 0), padx=24)
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

    def _build_header(self, parent: ctk.CTkFrame) -> None:
        """Build the page header with title and description."""
        header = ctk.CTkFrame(parent, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=24, pady=(24, 0))
        header.grid_columnconfigure(0, weight=1)

        # Title with icon
        title_frame = ctk.CTkFrame(header, fg_color="transparent")
        title_frame.grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            title_frame,
            text="🎨  Themes",
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color=self._tokens["text_primary"],
        ).pack(side="left")

        # Subtitle
        ctk.CTkLabel(
            header,
            text="Presets, accent gradients, and contrast tools — saved with your UI preferences. Shortcut: Ctrl+7",
            font=ctk.CTkFont(size=13),
            text_color=self._tokens["text_secondary"],
            wraplength=720,
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))

        # Accent underline
        accent_line = ctk.CTkFrame(
            header,
            height=3,
            width=80,
            fg_color=self._tokens["accent_primary"],
            corner_radius=2,
        )
        accent_line.grid(row=2, column=0, sticky="w", pady=(12, 0))

    def _build_presets_section(self, parent: ctk.CTkFrame) -> None:
        """Build the preset swatches grid."""
        section = ctk.CTkFrame(parent, fg_color="transparent")
        section.grid(row=0, column=0, sticky="nsew")
        section.grid_columnconfigure(0, weight=1)

        # Section header
        header_frame = ctk.CTkFrame(section, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="w", pady=(0, 16))

        ctk.CTkLabel(
            header_frame,
            text="Preset Themes",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=self._tokens["text_primary"],
        ).pack(side="left")

        # Count badge
        theme_count = len(get_theme_names())
        ctk.CTkLabel(
            header_frame,
            text=f"{theme_count} available",
            font=ctk.CTkFont(size=11),
            text_color=self._tokens["text_muted"],
            fg_color=self._tokens["bg_overlay"],
            corner_radius=8,
            padx=8,
            pady=3,
        ).pack(side="left", padx=(12, 0))

        # Swatches grid (4 columns) with modern card styling
        swatches_frame = ctk.CTkFrame(
            section,
            fg_color=self._tokens["bg_panel"],
            corner_radius=16,
            border_width=1,
            border_color=self._tokens["border_subtle"],
        )
        swatches_frame.grid(row=1, column=0, sticky="ew")
        self._panel_sections.append(swatches_frame)

        inner_grid = ctk.CTkFrame(swatches_frame, fg_color="transparent")
        inner_grid.pack(fill="x", padx=16, pady=16)

        self._swatch_buttons: dict[str, ctk.CTkButton] = {}
        col, row = 0, 0

        for key in get_theme_names():
            theme = get_theme(key)
            is_selected = key == self._current_theme_key

            accent = theme.get("accent_primary", "#3B8ED0")
            btn = ctk.CTkButton(
                inner_grid,
                text=theme.get("name", key),
                width=130,
                height=44,
                corner_radius=10,
                fg_color=accent,
                hover_color=theme.get("accent_secondary", "#36719F"),
                text_color=theme.get("text_on_accent", "#FFFFFF"),
                border_width=3 if is_selected else 0,
                # CTkButton rejects border_color="transparent"; match face when border_width=0
                border_color=self._tokens["accent_primary"] if is_selected else accent,
                font=ctk.CTkFont(size=12, weight="bold" if is_selected else "normal"),
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
        section = ctk.CTkFrame(
            parent,
            fg_color=self._tokens["bg_panel"],
            corner_radius=14,
            border_width=1,
            border_color=self._tokens["border_subtle"],
        )
        self._panel_sections.append(section)
        section.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        section.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            section,
            text="Appearance",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=self._tokens["text_primary"],
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(14, 10))

        mode_frame = ctk.CTkFrame(section, fg_color="transparent")
        mode_frame.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 14))

        ctk.CTkLabel(
            mode_frame,
            text="Mode",
            font=ctk.CTkFont(size=13),
            text_color=self._tokens["text_secondary"],
        ).pack(side="left")

        mode = ctk.CTkSegmentedButton(
            mode_frame,
            values=["Dark", "Light", "System"],
            command=self._on_mode,
            width=200,
            height=32,
            corner_radius=8,
            font=ctk.CTkFont(size=12),
        )
        mode.pack(side="right")
        cur_raw = str(ctk.get_appearance_mode() or "dark")
        cur_map = {"dark": "Dark", "light": "Light", "system": "System"}
        mode.set(cur_map.get(cur_raw.lower(), "Dark"))

    def _on_mode(self, value: str) -> None:
        """Handle appearance mode change."""
        ctk.set_appearance_mode(value)
        mode_map = {"Dark": "dark", "Light": "light", "System": "system"}
        self._tm.set_appearance_mode(mode_map.get(value, "dark"))

    def _build_gradient_section(self, parent: ctk.CTkFrame) -> None:
        """Accent gradient editor with canvas-based preview."""
        section = ctk.CTkFrame(
            parent,
            fg_color=self._tokens["bg_panel"],
            corner_radius=14,
            border_width=1,
            border_color=self._tokens["border_subtle"],
        )
        self._panel_sections.append(section)
        section.grid(row=1, column=0, sticky="ew", pady=(0, 16))
        section.grid_columnconfigure(0, weight=1)

        # Header
        ctk.CTkLabel(
            section,
            text="Accent Gradient",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=self._tokens["text_primary"],
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(14, 4))

        ctk.CTkLabel(
            section,
            text="Used for accent bars and highlights.",
            font=ctk.CTkFont(size=11),
            text_color=self._tokens["text_muted"],
        ).grid(row=1, column=0, sticky="w", padx=16, pady=(0, 10))

        # Gradient preview canvas with rounded container
        preview_container = ctk.CTkFrame(
            section,
            fg_color=self._tokens["bg_surface"],
            corner_radius=10,
        )
        preview_container.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 10))

        canvas_bg = resolve_color(self._tokens["bg_panel"])
        self._grad_canvas = tk.Canvas(
            preview_container,
            height=56,
            highlightthickness=0,
            borderwidth=0,
            bg=canvas_bg,
        )
        self._grad_canvas.pack(fill="x", padx=4, pady=4)
        self._grad_canvas.bind("<Configure>", self._paint_gradient)

        # Stop controls
        self._stops_frame = ctk.CTkFrame(section, fg_color="transparent")
        self._stops_frame.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 10))

        # Action buttons with modern styling
        btn_frame = ctk.CTkFrame(section, fg_color="transparent")
        btn_frame.grid(row=4, column=0, sticky="ew", padx=16, pady=(0, 14))

        ctk.CTkButton(
            btn_frame,
            text="+ Add Stop",
            width=100,
            height=32,
            corner_radius=8,
            fg_color=self._tokens["bg_elevated"],
            hover_color=self._tokens["bg_overlay"],
            text_color=self._tokens["text_primary"],
            font=ctk.CTkFont(size=12),
            command=self._add_gradient_stop,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_frame,
            text="Apply",
            width=80,
            height=32,
            corner_radius=8,
            fg_color=self._tokens["accent_primary"],
            hover_color=self._tokens["accent_secondary"],
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._apply_gradient,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_frame,
            text="Reset",
            width=80,
            height=32,
            corner_radius=8,
            fg_color=self._tokens["bg_elevated"],
            hover_color=self._tokens["bg_overlay"],
            text_color=self._tokens["text_secondary"],
            font=ctk.CTkFont(size=12),
            command=self._reset_gradient,
        ).pack(side="left")

        self._working_stops = self._load_editor_stops()
        self._rebuild_stop_rows()

    def _build_contrast_section(self, parent: ctk.CTkFrame) -> None:
        """WCAG contrast snapshot."""
        section = ctk.CTkFrame(
            parent,
            fg_color=self._tokens["bg_panel"],
            corner_radius=14,
            border_width=1,
            border_color=self._tokens["border_subtle"],
        )
        self._panel_sections.append(section)
        section.grid(row=2, column=0, sticky="ew", pady=(0, 16))
        section.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            section,
            text="Contrast (WCAG)",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=self._tokens["text_primary"],
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(14, 10))

        self._contrast_lbl = ctk.CTkLabel(
            section,
            text="",
            font=ctk.CTkFont(family="Consolas", size=11),
            text_color=self._tokens["text_secondary"],
            justify="left",
        )
        self._contrast_lbl.grid(row=1, column=0, sticky="w", padx=16, pady=(0, 14))

    def _build_import_export(self, parent: ctk.CTkFrame) -> None:
        """Import/export theme bundles."""
        section = ctk.CTkFrame(
            parent,
            fg_color=self._tokens["bg_panel"],
            corner_radius=14,
            border_width=1,
            border_color=self._tokens["border_subtle"],
        )
        self._panel_sections.append(section)
        section.grid(row=3, column=0, sticky="ew")
        section.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            section,
            text="Import / Export",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=self._tokens["text_primary"],
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(14, 12))

        btn_frame = ctk.CTkFrame(section, fg_color="transparent")
        btn_frame.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 8))

        ctk.CTkButton(
            btn_frame,
            text="📤 Export JSON",
            width=120,
            height=32,
            corner_radius=8,
            fg_color=self._tokens["bg_elevated"],
            hover_color=self._tokens["bg_overlay"],
            text_color=self._tokens["text_primary"],
            font=ctk.CTkFont(size=12),
            command=self._export_theme_json,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_frame,
            text="📥 Import JSON",
            width=120,
            height=32,
            corner_radius=8,
            fg_color=self._tokens["bg_elevated"],
            hover_color=self._tokens["bg_overlay"],
            text_color=self._tokens["text_primary"],
            font=ctk.CTkFont(size=12),
            command=self._import_theme_json,
        ).pack(side="left")

        ctk.CTkLabel(
            section,
            text="Export includes theme key, gradient stops, and UI flags.",
            font=ctk.CTkFont(size=10),
            text_color=self._tokens["text_muted"],
        ).grid(row=2, column=0, sticky="w", padx=16, pady=(0, 14))

    # ══════════════════════════════════════════════════════════════════════════
    # GRADIENT EDITOR METHODS - PRESERVED FUNCTIONALITY
    # ══════════════════════════════════════════════════════════════════════════

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
            row.pack(fill="x", pady=3)

            # Position spinbox
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

            # Color chip with modern styling
            chip = tk.Label(
                row,
                text="   ",
                width=3,
                background=col,
                relief="flat",
                borderwidth=0,
            )
            chip.pack(side="left", padx=(10, 10))

            # Color picker button
            ctk.CTkButton(
                row,
                text="Color",
                width=64,
                height=26,
                corner_radius=6,
                fg_color=self._tokens["bg_elevated"],
                hover_color=self._tokens["bg_overlay"],
                text_color=self._tokens["text_primary"],
                font=ctk.CTkFont(size=11),
                command=lambda idx=i: self._pick_stop_color(idx),
            ).pack(side="left", padx=(0, 6))

            # Remove button
            ctk.CTkButton(
                row,
                text="×",
                width=28,
                height=26,
                corner_radius=6,
                fg_color=self._tokens["error"],
                hover_color=("#B91C1C", "#DC2626"),
                font=ctk.CTkFont(size=12, weight="bold"),
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
        """Remove a gradient stop by index."""
        if len(self._working_stops) <= 2 or not (0 <= index < len(self._working_stops)):
            return
        self._working_stops = [stop for i, stop in enumerate(self._working_stops) if i != index]
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

        self._tm.set_custom_gradient_stops(srt)
        self._notify_toast("Accent gradient applied")

        safe_callback(self._on_preference_changed, context="on_preference_changed (apply gradient)")

    def _reset_gradient(self) -> None:
        self._tm.clear_custom_gradient_stops()
        self._working_stops = self._load_editor_stops()
        self._rebuild_stop_rows()
        self._paint_gradient()
        self._notify_toast("Using preset gradient")

        safe_callback(self._on_preference_changed, context="on_preference_changed (reset gradient)")

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

    # ══════════════════════════════════════════════════════════════════════════
    # THEME SELECTION AND UPDATE METHODS
    # ══════════════════════════════════════════════════════════════════════════

    def _select_theme(self, key: str) -> None:
        """Select a preset theme."""
        self._current_theme_key = key

        # Update visual selection
        for k, btn in self._swatch_buttons.items():
            if k == key:
                btn.configure(
                    border_width=3,
                    border_color=self._tokens["accent_primary"],
                )
            else:
                btn.configure(border_width=0)

        # Apply theme
        self._tm.apply_theme(key)

        safe_callback(self._on_theme_change, key, context="on_theme_change")

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

    # ══════════════════════════════════════════════════════════════════════════
    # IMPORT/EXPORT METHODS
    # ══════════════════════════════════════════════════════════════════════════

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
        safe_callback(self._on_toast, msg, context="on_toast")
