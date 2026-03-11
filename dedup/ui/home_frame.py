"""
DEDUP Home Frame - Scan setup screen.

Simple interface for selecting a folder and starting a scan.
Drop zone is click-to-browse (native Windows drag-drop removed to avoid ctypes crashes).
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from typing import Callable, Optional

try:
    from tkinterdnd2 import DND_FILES  # type: ignore
except Exception:
    DND_FILES = None


class HomeFrame(ttk.Frame):
    """
    Home screen for starting new scans.
    
    Features:
    - Folder selection (browse or drag-drop)
    - Recent folders list
    - Basic scan options
    - Start scan button
    """
    
    def __init__(
        self,
        parent,
        on_start_scan: Callable[[Path, dict], None],
        recent_folders: Optional[list] = None
    ):
        super().__init__(parent, padding="20")
        
        self.on_start_scan = on_start_scan
        self.recent_folders = recent_folders or []
        self.selected_path: Optional[Path] = None
        
        self._build_ui()
    
    def _build_ui(self):
        """Build the UI components."""
        # Configure grid
        self.columnconfigure(0, weight=1)
        
        # Title
        title = ttk.Label(
            self,
            text="Find Duplicate Files",
            font=("TkDefaultFont", 18, "bold")
        )
        title.grid(row=0, column=0, sticky="w", pady=(0, 20))
        
        # Description
        desc = ttk.Label(
            self,
            text="Select a folder to scan for duplicate files. "
                 "The scan will compare file contents to find exact duplicates.",
            wraplength=500
        )
        desc.grid(row=1, column=0, sticky="w", pady=(0, 20))
        
        # Folder selection
        folder_frame = ttk.LabelFrame(self, text="Folder to Scan", padding="10")
        folder_frame.grid(row=2, column=0, sticky="ew", pady=(0, 20))
        folder_frame.columnconfigure(0, weight=1)

        # Drop zone (drag-and-drop target)
        drop_frame = ttk.Frame(folder_frame)
        drop_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        drop_frame.columnconfigure(0, weight=1)
        self.drop_label = ttk.Label(
            drop_frame,
            text="Click here to choose folder (or use Browse)",
            relief="solid",
            padding=12,
            anchor="center",
        )
        self.drop_label.grid(row=0, column=0, sticky="ew")
        self.drop_label.bind("<Button-1>", lambda e: self._on_browse())
        self._enable_drag_drop()

        # Path entry and browse button (drop zone is click-to-browse only)
        path_frame = ttk.Frame(folder_frame)
        path_frame.grid(row=1, column=0, sticky="ew")
        path_frame.columnconfigure(0, weight=1)

        self.path_var = tk.StringVar()
        path_entry = ttk.Entry(path_frame, textvariable=self.path_var)
        path_entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))

        browse_btn = ttk.Button(
            path_frame,
            text="Browse...",
            command=self._on_browse
        )
        browse_btn.grid(row=0, column=1)

        # Recent folders
        if self.recent_folders:
            recent_frame = ttk.Frame(folder_frame)
            recent_frame.grid(row=2, column=0, sticky="w", pady=(10, 0))
            
            ttk.Label(recent_frame, text="Recent:").pack(side=tk.LEFT)
            
            for folder in self.recent_folders[:5]:
                btn = ttk.Button(
                    recent_frame,
                    text=Path(folder).name,
                    command=lambda f=folder: self._set_path(f)
                )
                btn.pack(side=tk.LEFT, padx=(5, 0))
        
        # Options
        options_frame = ttk.LabelFrame(self, text="Options", padding="10")
        options_frame.grid(row=3, column=0, sticky="ew", pady=(0, 20))

        # Scan subfolders (recurse into subfolders)
        self.scan_subfolders_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            options_frame,
            text="Scan subfolders (include all files in subfolders)",
            variable=self.scan_subfolders_var,
        ).grid(row=0, column=0, sticky="w")

        # Min size option
        self.min_size_var = tk.IntVar(value=1)
        ttk.Checkbutton(
            options_frame,
            text="Skip files smaller than 1 KB",
            variable=self.min_size_var,
            onvalue=1024,
            offvalue=1
        ).grid(row=1, column=0, sticky="w")

        # Include hidden
        self.hidden_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            options_frame,
            text="Include hidden files",
            variable=self.hidden_var
        ).grid(row=2, column=0, sticky="w")
        
        # Start button
        start_btn = ttk.Button(
            self,
            text="Start Scan",
            command=self._on_start,
            style="Accent.TButton"
        )
        start_btn.grid(row=4, column=0, pady=(20, 0))
        
        # Configure accent style if possible
        try:
            style = ttk.Style()
            style.configure("Accent.TButton", font=("TkDefaultFont", 12, "bold"))
        except Exception:
            pass
    
    def _on_browse(self):
        """Open folder browser dialog."""
        path = filedialog.askdirectory(title="Select Folder to Scan")
        if path:
            self._set_path(path)
    
    def _set_path(self, path: str):
        """Set the selected path (always store absolute path)."""
        path = str(Path(path).resolve())
        self.path_var.set(path)
        self.selected_path = Path(path)

    def _enable_drag_drop(self):
        """Enable drag-and-drop when tkinterdnd2 is available."""
        if DND_FILES is None:
            return
        try:
            self.drop_label.drop_target_register(DND_FILES)
            self.drop_label.dnd_bind("<<Drop>>", self._on_drop)
            self.drop_label.configure(text="Drop folder here (or click to browse)")
        except Exception:
            # Keep click-to-browse behavior if DnD cannot initialize
            pass

    def _on_drop(self, event):
        """Handle dropped path(s), selecting the first valid directory."""
        data = (event.data or "").strip()
        if not data:
            return
        # Handle Tcl list format with braces around paths containing spaces.
        # Example: {C:\My Folder} C:\Other
        paths = self.tk.splitlist(data)
        for p in paths:
            candidate = p.strip("{}").strip()
            if candidate:
                path_obj = Path(candidate)
                if path_obj.exists() and path_obj.is_dir():
                    self._set_path(str(path_obj))
                    break
    
    def _on_start(self):
        """Handle start scan button."""
        path_str = self.path_var.get().strip()
        
        if not path_str:
            messagebox.showerror("Error", "Please select a folder to scan")
            return
        
        path = Path(path_str).resolve()
        
        if not path.exists():
            messagebox.showerror("Error", f"Path does not exist: {path}")
            return
        
        if not path.is_dir():
            messagebox.showerror("Error", f"Not a directory: {path}")
            return
        
        self.path_var.set(str(path))
        
        # Build options
        options = {
            "min_size": self.min_size_var.get(),
            "include_hidden": self.hidden_var.get(),
            "scan_subfolders": self.scan_subfolders_var.get(),
        }

        self.on_start_scan(path, options)
    
    def on_show(self):
        """Called when frame is shown."""
        pass
