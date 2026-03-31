"""
CustomTkinter Settings page — full CEREBRO settings panel.

Sections:
- Appearance: theme, density, motion, contrast
- Behavior: advanced mode, view options
- Data: database path, shortcuts

REFACTORED: Visual redesign with modern aesthetics while preserving all APIs.
- Clean card-based sections with consistent borders
- Enhanced toggle switches and controls
- Improved visual hierarchy and spacing
- Better path display with monospace font
"""

from __future__ import annotations

import tkinter as tk
from typing import Callable, Optional

import customtkinter as ctk

from ..utils.ui_state import UIState
from .design_tokens import get_theme_colors, resolve_border_token
from .ui_utils import safe_callback


class SettingsPageCTK(ctk.CTkFrame):
    """Full settings page with appearance, behavior, and data sections."""

    # ══════════════════════════════════════════════════════════════════════════
    # PUBLIC API - UNCHANGED
    # ══════════════════════════════════════════════════════════════════════════

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

        # Store references - UNCHANGED
        self._state = state
        self._on_open_themes = on_open_themes
        self._on_open_diagnostics = on_open_diagnostics
        self._on_settings_changed = on_settings_changed
        self._on_toast = on_toast
        self._db_path = database_path
        self._config_json_path = config_json_path
        self._ui_settings_json_path = ui_settings_json_path

        # Layout
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Design tokens — same source as other CTK pages (pairs for light/dark appearance).
        self._tokens = get_theme_colors()

        self._build()

    def set_database_path(self, path: str) -> None:
        """Set database path. API UNCHANGED."""
        self._db_path = path
        if hasattr(self, "_db_var"):
            self._db_var.set(path)

    def apply_theme_tokens(self, tokens: dict) -> None:
        """Apply theme tokens to styled components. API UNCHANGED."""
        panel = str(tokens.get("bg_panel", "#1C2128"))
        elev = str(tokens.get("bg_elevated", "#161B22"))
        self.configure(fg_color=panel)
        if hasattr(self, "_scroll"):
            self._scroll.configure(fg_color="transparent", label_fg_color="transparent")
        acc = str(tokens.get("accent_primary", "#22D3EE"))
        border = resolve_border_token(tokens)

        for f in self._section_frames:
            f.configure(fg_color=elev, border_color=border)

        if hasattr(self, "_themes_btn"):
            self._themes_btn.configure(fg_color=acc)
        if hasattr(self, "_diag_btn"):
            self._diag_btn.configure(fg_color=elev, border_color=border)

        # Update all text labels with live token colors
        self._update_label_colors(self, tokens)

    def _update_label_colors(self, widget, tokens: dict) -> None:
        from ..utils.theme_utils import apply_label_colors

        apply_label_colors(widget, tokens)

    def on_show(self) -> None:
        """Called when page becomes visible - refresh from state. API UNCHANGED."""
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
        self._sync_advanced_section_visibility()

    # ══════════════════════════════════════════════════════════════════════════
    # PRIVATE IMPLEMENTATION - VISUAL REFACTOR
    # ══════════════════════════════════════════════════════════════════════════

    def _copy_path(self, text: str) -> None:
        """Copy path to clipboard. Logic UNCHANGED."""
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
        """Build settings page with enhanced visuals."""
        self._section_frames: list[ctk.CTkFrame] = []

        # Scrollable container
        self._scroll = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            corner_radius=0,
        )
        self._scroll.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        self._scroll.grid_columnconfigure(0, weight=1)

        # Header
        self._build_header(self._scroll)

        # Two-column layout
        content = ctk.CTkFrame(self._scroll, fg_color="transparent")
        content.grid(row=1, column=0, sticky="ew", padx=24, pady=(24, 24))
        content.grid_columnconfigure(0, weight=1)
        content.grid_columnconfigure(1, weight=1)

        # Left column
        left = ctk.CTkFrame(content, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        left.grid_columnconfigure(0, weight=1)

        self._build_appearance_section(left)
        self._build_behavior_section(left)

        # Right column
        right = ctk.CTkFrame(content, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew", padx=(12, 0))
        right.grid_columnconfigure(0, weight=1)

        self._build_data_section(right)
        self._build_view_section(right)

        self._build_advanced_section(self._scroll)
        self._sync_advanced_section_visibility()

    def _build_header(self, parent: ctk.CTkFrame) -> None:
        """Build page header."""
        header = ctk.CTkFrame(parent, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=24, pady=(24, 0))

        # Icon and title row
        title_row = ctk.CTkFrame(header, fg_color="transparent")
        title_row.pack(fill="x")

        ctk.CTkLabel(
            title_row,
            text="⚙️",
            font=ctk.CTkFont(size=28),
        ).pack(side="left", padx=(0, 12))

        ctk.CTkLabel(
            title_row,
            text="Settings",
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color=self._tokens["text_primary"],
        ).pack(side="left")

        ctk.CTkLabel(
            header,
            text="Customize appearance, behavior, and data preferences.",
            font=ctk.CTkFont(size=14),
            text_color=self._tokens["text_secondary"],
        ).pack(anchor="w", pady=(8, 0))

    def _build_section_header(self, parent: ctk.CTkFrame, icon: str, title: str) -> None:
        """Build a section header with icon."""
        header = ctk.CTkFrame(parent, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(20, 16))

        ctk.CTkLabel(
            header,
            text=f"{icon}  {title}",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=self._tokens["text_primary"],
        ).pack(side="left")

    def _build_setting_row(
        self,
        parent: ctk.CTkFrame,
        label: str,
        description: str | None = None,
    ) -> ctk.CTkFrame:
        """Create a setting row container."""
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=(0, 12))

        label_frame = ctk.CTkFrame(row, fg_color="transparent")
        label_frame.pack(side="left", fill="x", expand=True)

        ctk.CTkLabel(
            label_frame,
            text=label,
            font=ctk.CTkFont(size=14),
            text_color=self._tokens["text_primary"],
        ).pack(anchor="w")

        if description:
            ctk.CTkLabel(
                label_frame,
                text=description,
                font=ctk.CTkFont(size=12),
                text_color=self._tokens["text_muted"],
            ).pack(anchor="w")

        return row

    def _build_appearance_section(self, parent: ctk.CTkFrame) -> None:
        """Build appearance settings section."""
        section = ctk.CTkFrame(
            parent,
            corner_radius=16,
            fg_color=self._tokens["bg_elevated"],
            border_width=1,
            border_color=self._tokens["border_subtle"],
        )
        self._section_frames.append(section)
        section.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        section.grid_columnconfigure(0, weight=1)

        self._build_section_header(section, "🎨", "Appearance")

        # UI Density dropdown
        row = self._build_setting_row(section, "UI Density", "Adjust spacing and component sizes")
        self._density_var = ctk.StringVar(value=self._state.settings.density)
        ctk.CTkOptionMenu(
            row,
            values=["comfortable", "cozy", "compact"],
            variable=self._density_var,
            width=150,
            height=36,
            corner_radius=10,
            fg_color=self._tokens["bg_elevated"],
            button_color=self._tokens["bg_elevated"],
            button_hover_color=self._tokens["accent_secondary"],
            dropdown_fg_color=self._tokens["bg_panel"],
            command=self._on_density_changed,
        ).pack(side="right")

        # Reduced Motion toggle
        row2 = self._build_setting_row(section, "Reduced Motion", "Minimize animations and transitions")
        self._motion_var = ctk.BooleanVar(value=self._state.settings.reduced_motion)
        self._motion_switch = ctk.CTkSwitch(
            row2,
            text="",
            variable=self._motion_var,
            width=50,
            progress_color=self._tokens["accent_primary"],
            button_color=("#FFFFFF", "#FFFFFF"),
            command=self._on_motion_changed,
        )
        self._motion_switch.pack(side="right")

        # High Contrast toggle
        row3 = self._build_setting_row(section, "High Contrast", "Increase visual contrast for accessibility")
        self._contrast_var = ctk.BooleanVar(value=self._state.settings.high_contrast)
        self._contrast_switch = ctk.CTkSwitch(
            row3,
            text="",
            variable=self._contrast_var,
            width=50,
            progress_color=self._tokens["accent_primary"],
            button_color=("#FFFFFF", "#FFFFFF"),
            command=self._on_contrast_changed,
        )
        self._contrast_switch.pack(side="right")

        ctk.CTkFrame(section, height=8, fg_color="transparent").pack()

    def _build_behavior_section(self, parent: ctk.CTkFrame) -> None:
        """Build behavior settings section."""
        section = ctk.CTkFrame(
            parent,
            corner_radius=16,
            fg_color=self._tokens["bg_elevated"],
            border_width=1,
            border_color=self._tokens["border_subtle"],
        )
        self._section_frames.append(section)
        section.grid(row=1, column=0, sticky="ew")
        section.grid_columnconfigure(0, weight=1)

        self._build_section_header(section, "🔧", "Behavior")

        # Advanced Mode toggle
        row = self._build_setting_row(section, "Advanced Mode", "Show additional controls and options")
        self._advanced_var = ctk.BooleanVar(value=self._state.settings.advanced_mode)
        self._advanced_switch = ctk.CTkSwitch(
            row,
            text="",
            variable=self._advanced_var,
            width=50,
            progress_color=self._tokens["accent_primary"],
            button_color=("#FFFFFF", "#FFFFFF"),
            command=self._on_advanced_changed,
        )
        self._advanced_switch.pack(side="right")

        # Reduced Gradients toggle
        row2 = self._build_setting_row(section, "Reduced Gradients", "Use solid colors instead of gradients")
        self._gradients_var = ctk.BooleanVar(value=self._state.settings.reduced_gradients)
        self._gradients_switch = ctk.CTkSwitch(
            row2,
            text="",
            variable=self._gradients_var,
            width=50,
            progress_color=self._tokens["accent_primary"],
            button_color=("#FFFFFF", "#FFFFFF"),
            command=self._on_gradients_changed,
        )
        self._gradients_switch.pack(side="right")

        # Bottom padding
        ctk.CTkFrame(section, height=8, fg_color="transparent").pack()

    def _build_data_section(self, parent: ctk.CTkFrame) -> None:
        """Build data paths section."""
        section = ctk.CTkFrame(
            parent,
            corner_radius=16,
            fg_color=self._tokens["bg_elevated"],
            border_width=1,
            border_color=self._tokens["border_subtle"],
        )
        self._section_frames.append(section)
        section.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        section.grid_columnconfigure(0, weight=1)

        self._build_section_header(section, "📁", "Data")

        ctk.CTkLabel(
            section,
            text="Local paths for scan history, engine defaults, and UI preferences.\nCopy these when reporting issues.",
            font=ctk.CTkFont(size=12),
            text_color=self._tokens["text_muted"],
            justify="left",
        ).pack(anchor="w", padx=20, pady=(0, 16))

        # Path variables
        self._db_var = ctk.StringVar(value=self._db_path)
        self._cfg_var = ctk.StringVar(value=self._config_json_path)
        self._ui_settings_var = ctk.StringVar(value=self._ui_settings_json_path)

        paths = [
            ("Scan history database", self._db_var),
            ("Engine defaults (config.json)", self._cfg_var),
            ("UI preferences (ui_settings.json)", self._ui_settings_var),
        ]

        for title, var in paths:
            self._build_path_row(section, title, var)

        ctk.CTkFrame(section, height=8, fg_color="transparent").pack()

    def _build_advanced_section(self, parent: ctk.CTkFrame) -> None:
        """Themes + Diagnostics — shown only when Advanced Mode is enabled."""
        section = ctk.CTkFrame(
            parent,
            corner_radius=16,
            fg_color=self._tokens["bg_elevated"],
            border_width=1,
            border_color=self._tokens["border_subtle"],
        )
        self._section_frames.append(section)
        self._advanced_section = section
        section.grid(row=2, column=0, sticky="ew", padx=24, pady=(0, 24))

        self._build_section_header(section, "🔧", "Advanced tools")

        ctk.CTkLabel(
            section,
            text="Theme customization and technical diagnostics. Enable “Advanced Mode” in Behavior to show this section.",
            font=ctk.CTkFont(size=12),
            text_color=self._tokens["text_muted"],
            wraplength=720,
            justify="left",
        ).pack(anchor="w", padx=20, pady=(0, 12))

        btn_row = ctk.CTkFrame(section, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(0, 20))

        self._themes_btn = ctk.CTkButton(
            btn_row,
            text="🎭  Open Themes…",
            width=170,
            height=40,
            corner_radius=10,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=self._tokens["accent_primary"],
            text_color=("#FFFFFF", "#0A0E14"),
            command=self._on_open_themes,
        )
        self._themes_btn.pack(side="left", padx=(0, 12))

        self._diag_btn = ctk.CTkButton(
            btn_row,
            text="🔬  Open Diagnostics…",
            width=190,
            height=40,
            corner_radius=10,
            font=ctk.CTkFont(size=14),
            fg_color=self._tokens["bg_elevated"],
            text_color=self._tokens["text_secondary"],
            border_width=1,
            border_color=self._tokens["border_subtle"],
            command=self._on_open_diagnostics,
        )
        self._diag_btn.pack(side="left")

    def _sync_advanced_section_visibility(self) -> None:
        if hasattr(self, "_advanced_section"):
            if self._state.settings.advanced_mode:
                self._advanced_section.grid()
            else:
                self._advanced_section.grid_remove()

    def _build_path_row(self, parent: ctk.CTkFrame, title: str, var: ctk.StringVar) -> None:
        """Build a path display row with copy button."""
        container = ctk.CTkFrame(parent, fg_color="transparent")
        container.pack(fill="x", padx=20, pady=(0, 12))

        ctk.CTkLabel(
            container,
            text=title,
            font=ctk.CTkFont(size=12),
            text_color=self._tokens["text_muted"],
        ).pack(anchor="w")

        row = ctk.CTkFrame(container, fg_color="transparent")
        row.pack(fill="x", pady=(4, 0))
        row.grid_columnconfigure(0, weight=1)

        # Path display with monospace font
        path_label = ctk.CTkLabel(
            row,
            textvariable=var,
            font=ctk.CTkFont(family="SF Mono", size=11),
            text_color=self._tokens["text_secondary"],
            wraplength=380,
            anchor="w",
            justify="left",
        )
        path_label.grid(row=0, column=0, sticky="ew")

        # Copy button
        ctk.CTkButton(
            row,
            text="📋",
            width=40,
            height=32,
            corner_radius=8,
            font=ctk.CTkFont(size=14),
            fg_color=self._tokens["bg_elevated"],
            text_color=self._tokens["text_muted"],
            border_width=1,
            border_color=self._tokens["border_subtle"],
            command=lambda v=var: self._copy_path(v.get()),
        ).grid(row=0, column=1, padx=(12, 0))

    def _build_view_section(self, parent: ctk.CTkFrame) -> None:
        """Build view options section."""
        section = ctk.CTkFrame(
            parent,
            corner_radius=16,
            fg_color=self._tokens["bg_elevated"],
            border_width=1,
            border_color=self._tokens["border_subtle"],
        )
        self._section_frames.append(section)
        section.grid(row=1, column=0, sticky="ew")
        section.grid_columnconfigure(0, weight=1)

        self._build_section_header(section, "👁️", "View Options")

        # Mission capabilities toggle
        row = self._build_setting_row(section, "Show Capabilities on Mission", "Display system capabilities overview")
        self._mission_cap_var = ctk.BooleanVar(value=self._state.settings.mission_show_capabilities)
        self._mission_cap_switch = ctk.CTkSwitch(
            row,
            text="",
            variable=self._mission_cap_var,
            width=50,
            progress_color=self._tokens["accent_primary"],
            button_color=("#FFFFFF", "#FFFFFF"),
            command=self._on_mission_cap_changed,
        )
        self._mission_cap_switch.pack(side="right")

        # Review thumbnails toggle
        row2 = self._build_setting_row(section, "Show Thumbnails in Review", "Display image previews in results")
        self._review_thumb_var = ctk.BooleanVar(value=self._state.settings.review_show_thumbnails)
        self._review_thumb_switch = ctk.CTkSwitch(
            row2,
            text="",
            variable=self._review_thumb_var,
            width=50,
            progress_color=self._tokens["accent_primary"],
            button_color=("#FFFFFF", "#FFFFFF"),
            command=self._on_review_thumb_changed,
        )
        self._review_thumb_switch.pack(side="right")

        # Bottom padding
        ctk.CTkFrame(section, height=8, fg_color="transparent").pack()

    # ── Callbacks - Logic UNCHANGED ─────────────────────────────────────────

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
        self._sync_advanced_section_visibility()
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
        """Save settings and notify listeners. Logic UNCHANGED."""
        self._state.save()
        safe_callback(self._on_settings_changed, context="on_settings_changed")
        safe_callback(self._on_toast, "Settings saved", context="on_toast (settings saved)")
