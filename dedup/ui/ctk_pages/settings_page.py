"""
CustomTkinter Settings page — full CEREBRO settings panel.

Sections:
- Appearance: theme, density, motion, contrast
- Behavior: advanced mode, view options
- Data: database path, shortcuts
"""

from __future__ import annotations

import tkinter as tk
from typing import Callable, Optional

import customtkinter as ctk

from ..utils.ui_state import UIState


class SettingsPageCTK(ctk.CTkFrame):
    """Full settings page with appearance, behavior, and data sections."""

    def __init__(
        self,
        parent,
        *,
        state: UIState,
        database_path: str,
        config_json_path: str = "",
        ui_settings_json_path: str = "",
        on_open_themes: Callable[[], None],
        on_open_diagnostics: Callable[[], None],
        on_settings_changed: Optional[Callable[[], None]] = None,
        on_toast: Optional[Callable[[str], None]] = None,
        **kwargs,
    ) -> None:
        super().__init__(parent, **kwargs)
        self._state = state
        self._on_open_themes = on_open_themes
        self._on_open_diagnostics = on_open_diagnostics
        self._on_settings_changed = on_settings_changed
        self._on_toast = on_toast
        self._db_path = database_path
        self._config_json_path = config_json_path
        self._ui_settings_json_path = ui_settings_json_path

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build()

    def set_database_path(self, path: str) -> None:
        self._db_path = path
        if hasattr(self, "_db_var"):
            self._db_var.set(path)

    def _copy_path(self, text: str) -> None:
        if not text:
            return
        try:
            r = self.winfo_toplevel()
            r.clipboard_clear()
            r.clipboard_append(text)
            r.update_idletasks()
            if self._on_toast:
                self._on_toast("Path copied to clipboard")
        except tk.TclError:
            pass

    def _build(self) -> None:
        self._section_frames: list[ctk.CTkFrame] = []
        # Scrollable container
        # Avoid "transparent" here: CTkScrollableFrame uses an internal Tk Canvas which can
        # repaint with raw Tk defaults (white) on hover/scroll unless we give it a real color.
        scroll = ctk.CTkScrollableFrame(self, fg_color=("#F6F7F9", "#0f131c"))
        self._scroll = scroll
        scroll.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        scroll.grid_columnconfigure(0, weight=1)

        # Header
        self._build_header(scroll)

        # Two-column layout
        content = ctk.CTkFrame(scroll, fg_color="transparent")
        content.grid(row=1, column=0, sticky="ew", pady=(20, 0))
        content.grid_columnconfigure(0, weight=1)
        content.grid_columnconfigure(1, weight=1)

        # Left column
        left = ctk.CTkFrame(content, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        left.grid_columnconfigure(0, weight=1)

        self._build_appearance_section(left)
        self._build_behavior_section(left)

        # Right column
        right = ctk.CTkFrame(content, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        right.grid_columnconfigure(0, weight=1)

        self._build_data_section(right)
        self._build_view_section(right)

    def _build_header(self, parent: ctk.CTkFrame) -> None:
        header = ctk.CTkFrame(parent, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew")

        ctk.CTkLabel(
            header,
            text="Settings",
            font=ctk.CTkFont(size=28, weight="bold"),
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            header,
            text="Customize appearance, behavior, and data preferences.",
            font=ctk.CTkFont(size=12),
            text_color=("gray40", "gray70"),
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

    def _build_appearance_section(self, parent: ctk.CTkFrame) -> None:
        section = ctk.CTkFrame(parent, fg_color=("gray95", "gray15"))
        self._section_frames.append(section)
        section.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        section.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            section,
            text="Appearance",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(12, 12))

        # UI Density
        row = ctk.CTkFrame(section, fg_color="transparent")
        row.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 8))
        ctk.CTkLabel(row, text="Density").pack(side="left")
        self._density_var = ctk.StringVar(value=self._state.settings.density)
        ctk.CTkOptionMenu(
            row,
            values=["comfortable", "cozy", "compact"],
            variable=self._density_var,
            width=140,
            command=self._on_density_changed,
        ).pack(side="right")

        # Reduced Motion
        row2 = ctk.CTkFrame(section, fg_color="transparent")
        row2.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 8))
        self._motion_var = ctk.BooleanVar(value=self._state.settings.reduced_motion)
        ctk.CTkSwitch(
            row2,
            text="Reduced motion",
            variable=self._motion_var,
            command=self._on_motion_changed,
        ).pack(side="left")

        # High Contrast
        row3 = ctk.CTkFrame(section, fg_color="transparent")
        row3.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 12))
        self._contrast_var = ctk.BooleanVar(value=self._state.settings.high_contrast)
        ctk.CTkSwitch(
            row3,
            text="High contrast",
            variable=self._contrast_var,
            command=self._on_contrast_changed,
        ).pack(side="left")

        # Open Themes button
        btn_row = ctk.CTkFrame(section, fg_color="transparent")
        btn_row.grid(row=4, column=0, sticky="ew", padx=16, pady=(0, 12))
        self._themes_btn = ctk.CTkButton(
            btn_row,
            text="Open Themes…",
            command=self._on_open_themes,
        )
        self._themes_btn.pack(side="left")

    def _build_behavior_section(self, parent: ctk.CTkFrame) -> None:
        section = ctk.CTkFrame(parent, fg_color=("gray95", "gray15"))
        self._section_frames.append(section)
        section.grid(row=1, column=0, sticky="ew")
        section.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            section,
            text="Behavior",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(12, 12))

        # Advanced Mode
        row = ctk.CTkFrame(section, fg_color="transparent")
        row.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 8))
        self._advanced_var = ctk.BooleanVar(value=self._state.settings.advanced_mode)
        ctk.CTkSwitch(
            row,
            text="Advanced mode",
            variable=self._advanced_var,
            command=self._on_advanced_changed,
        ).pack(side="left")

        # Reduced Gradients
        row2 = ctk.CTkFrame(section, fg_color="transparent")
        row2.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 12))
        self._gradients_var = ctk.BooleanVar(value=self._state.settings.reduced_gradients)
        ctk.CTkSwitch(
            row2,
            text="Reduced gradients",
            variable=self._gradients_var,
            command=self._on_gradients_changed,
        ).pack(side="left")

    def _build_data_section(self, parent: ctk.CTkFrame) -> None:
        section = ctk.CTkFrame(parent, fg_color=("gray95", "gray15"))
        self._section_frames.append(section)
        section.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        section.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            section,
            text="Data",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(12, 12))

        ctk.CTkLabel(
            section,
            text="Local paths for scan history, engine defaults, and UI preferences. Copy when reporting issues.",
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray70"),
            wraplength=520,
            justify="left",
        ).grid(row=1, column=0, sticky="w", padx=16, pady=(0, 8))

        self._db_var = ctk.StringVar(value=self._db_path)
        self._cfg_var = ctk.StringVar(value=self._config_json_path)
        self._ui_settings_var = ctk.StringVar(value=self._ui_settings_json_path)

        row = 2
        for title, var in (
            ("Scan history database", self._db_var),
            ("Engine defaults (config.json)", self._cfg_var),
            ("UI preferences (ui_settings.json)", self._ui_settings_var),
        ):
            ctk.CTkLabel(section, text=title, text_color=("gray40", "gray70")).grid(
                row=row, column=0, sticky="w", padx=16, pady=(4, 0)
            )
            row_inner = ctk.CTkFrame(section, fg_color="transparent")
            row_inner.grid(row=row + 1, column=0, sticky="ew", padx=16, pady=(0, 6))
            row_inner.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(
                row_inner,
                textvariable=var,
                font=ctk.CTkFont(size=11),
                wraplength=420,
                anchor="w",
                justify="left",
            ).grid(row=0, column=0, sticky="ew")
            ctk.CTkButton(
                row_inner,
                text="Copy",
                width=72,
                command=lambda v=var: self._copy_path(v.get()),
            ).grid(row=0, column=1, padx=(8, 0))
            row += 2

        btn_row = ctk.CTkFrame(section, fg_color="transparent")
        btn_row.grid(row=row, column=0, sticky="ew", padx=16, pady=(4, 12))
        self._diag_btn = ctk.CTkButton(
            btn_row,
            text="Open Diagnostics…",
            fg_color=("gray35", "gray50"),
            command=self._on_open_diagnostics,
        )
        self._diag_btn.pack(side="left")

    def _build_view_section(self, parent: ctk.CTkFrame) -> None:
        section = ctk.CTkFrame(parent, fg_color=("gray95", "gray15"))
        self._section_frames.append(section)
        section.grid(row=1, column=0, sticky="ew")
        section.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            section,
            text="View Options",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(12, 12))

        # Mission capabilities
        row = ctk.CTkFrame(section, fg_color="transparent")
        row.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 8))
        self._mission_cap_var = ctk.BooleanVar(value=self._state.settings.mission_show_capabilities)
        ctk.CTkSwitch(
            row,
            text="Show capabilities on Mission",
            variable=self._mission_cap_var,
            command=self._on_mission_cap_changed,
        ).pack(side="left")

        # Review thumbnails
        row2 = ctk.CTkFrame(section, fg_color="transparent")
        row2.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 12))
        self._review_thumb_var = ctk.BooleanVar(value=self._state.settings.review_show_thumbnails)
        ctk.CTkSwitch(
            row2,
            text="Show thumbnails in Review",
            variable=self._review_thumb_var,
            command=self._on_review_thumb_changed,
        ).pack(side="left")

    # --- Callbacks ---

    def _on_density_changed(self, value: str) -> None:
        self._state.settings.density = value
        self._save_and_notify()

    def _on_motion_changed(self) -> None:
        self._state.settings.reduced_motion = self._motion_var.get()
        self._save_and_notify()

    def _on_contrast_changed(self) -> None:
        self._state.settings.high_contrast = self._contrast_var.get()
        self._save_and_notify()

    def _on_advanced_changed(self) -> None:
        self._state.settings.advanced_mode = self._advanced_var.get()
        self._save_and_notify()

    def _on_gradients_changed(self) -> None:
        self._state.settings.reduced_gradients = self._gradients_var.get()
        self._save_and_notify()

    def _on_mission_cap_changed(self) -> None:
        self._state.settings.mission_show_capabilities = self._mission_cap_var.get()
        self._save_and_notify()

    def _on_review_thumb_changed(self) -> None:
        self._state.settings.review_show_thumbnails = self._review_thumb_var.get()
        self._save_and_notify()

    def _save_and_notify(self) -> None:
        self._state.save()
        if self._on_settings_changed:
            try:
                self._on_settings_changed()
            except Exception:
                pass
        if self._on_toast:
            try:
                self._on_toast("Settings saved")
            except Exception:
                pass

    def apply_theme_tokens(self, tokens: dict) -> None:
        panel = str(tokens.get("bg_panel", "#161b22"))
        elev = str(tokens.get("bg_elevated", "#21262d"))
        acc = str(tokens.get("accent_primary", "#3B8ED0"))
        for f in self._section_frames:
            f.configure(fg_color=panel)
        if hasattr(self, "_scroll"):
            bg = str(tokens.get("bg_base", "#0f131c"))
            self._scroll.configure(fg_color=("#F6F7F9", bg))
        if hasattr(self, "_themes_btn"):
            self._themes_btn.configure(fg_color=acc)
        if hasattr(self, "_diag_btn"):
            self._diag_btn.configure(fg_color=elev)

    def on_show(self) -> None:
        """Called when page becomes visible - refresh from state."""
        self._density_var.set(self._state.settings.density)
        self._motion_var.set(self._state.settings.reduced_motion)
        self._contrast_var.set(self._state.settings.high_contrast)
        self._advanced_var.set(self._state.settings.advanced_mode)
        self._gradients_var.set(self._state.settings.reduced_gradients)
        self._mission_cap_var.set(self._state.settings.mission_show_capabilities)
        self._review_thumb_var.set(self._state.settings.review_show_thumbnails)
        self._db_var.set(self._db_path)
        if hasattr(self, "_cfg_var"):
            self._cfg_var.set(self._config_json_path)
        if hasattr(self, "_ui_settings_var"):
            self._ui_settings_var.set(self._ui_settings_json_path)
