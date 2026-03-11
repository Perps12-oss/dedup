"""
DEDUP Main Application - Minimal tkinter-based UI.

A clean, no-nonsense interface focused on functionality over aesthetics.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path
from typing import Optional

try:
    from tkinterdnd2 import TkinterDnD  # type: ignore
except Exception:
    TkinterDnD = None

from ..orchestration.coordinator import ScanCoordinator
from ..infrastructure.config import load_config, save_config
from .home_frame import HomeFrame
from .scan_frame import ScanFrame
from .results_frame import ResultsFrame
from .history_frame import HistoryFrame


class DedupApp:
    """
    Main application window.
    
    Provides a simple tabbed interface with four screens:
    - Home: Start a new scan
    - Scan: Monitor active scan
    - Results: Review and delete duplicates
    - History: View past scans
    """
    
    APP_NAME = "DEDUP"
    APP_VERSION = "1.0.0"
    MIN_WIDTH = 900
    MIN_HEIGHT = 600
    
    def __init__(self):
        if TkinterDnD is not None:
            self.root = TkinterDnD.Tk()
        else:
            self.root = tk.Tk()
        self.root.title(f"{self.APP_NAME} v{self.APP_VERSION}")
        self.root.minsize(self.MIN_WIDTH, self.MIN_HEIGHT)
        self.root.geometry(f"{self.MIN_WIDTH}x{self.MIN_HEIGHT}")
        
        # Load config for window position
        self.config = load_config()
        
        # Coordinator
        self.coordinator = ScanCoordinator()
        
        # Current state
        self.current_scan_id: Optional[str] = None
        self.last_result: Optional[any] = None
        
        # Build UI
        self._build_ui()
        
        # Handle window close
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
    
    def _build_ui(self):
        """Build the main UI."""
        # Main container with padding
        self.main_frame = ttk.Frame(self.root, padding="10")
        self.main_frame.grid(row=0, column=0, sticky="nsew")
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        self.main_frame.columnconfigure(0, weight=1)
        self.main_frame.rowconfigure(1, weight=1)
        
        # Header with title and navigation
        self._build_header()
        
        # Content area (notebook for tabs)
        self._build_content()
        
        # Status bar
        self._build_status_bar()
    
    def _build_header(self):
        """Build the header with navigation."""
        header = ttk.Frame(self.main_frame)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        
        # Title
        title = ttk.Label(
            header,
            text=self.APP_NAME,
            font=("TkDefaultFont", 16, "bold")
        )
        title.pack(side=tk.LEFT)
        
        # Navigation buttons
        nav_frame = ttk.Frame(header)
        nav_frame.pack(side=tk.RIGHT)
        
        self.nav_buttons = {}
        
        for label, frame_class in [
            ("Home", "home"),
            ("Scan", "scan"),
            ("Results", "results"),
            ("History", "history"),
        ]:
            btn = ttk.Button(
                nav_frame,
                text=label,
                command=lambda f=frame_class: self._show_frame(f)
            )
            btn.pack(side=tk.LEFT, padx=5)
            self.nav_buttons[frame_class] = btn
        
        # Separator
        ttk.Separator(self.main_frame, orient=tk.HORIZONTAL).grid(
            row=0, column=0, sticky="ew", pady=(40, 0)
        )
    
    def _build_content(self):
        """Build the main content area with frames."""
        # Container for frames
        self.content_frame = ttk.Frame(self.main_frame)
        self.content_frame.grid(row=1, column=0, sticky="nsew")
        self.content_frame.columnconfigure(0, weight=1)
        self.content_frame.rowconfigure(0, weight=1)
        
        # Create frames
        self.frames = {}
        
        self.frames["home"] = HomeFrame(
            self.content_frame,
            on_start_scan=self._on_start_scan,
            recent_folders=self.coordinator.get_recent_folders(),
        )
        
        self.frames["scan"] = ScanFrame(
            self.content_frame,
            coordinator=self.coordinator,
            on_complete=self._on_scan_complete,
            on_cancel=self._on_scan_cancel
        )
        
        self.frames["results"] = ResultsFrame(
            self.content_frame,
            coordinator=self.coordinator,
            on_delete_complete=self._on_delete_complete
        )
        
        self.frames["history"] = HistoryFrame(
            self.content_frame,
            coordinator=self.coordinator,
            on_load_scan=self._on_load_history_scan,
            on_resume_scan=self._on_resume_scan,
        )
        
        # Grid all frames (they will be hidden/shown)
        for frame in self.frames.values():
            frame.grid(row=0, column=0, sticky="nsew")
        
        # Show home by default
        self._show_frame("home")
    
    def _build_status_bar(self):
        """Build the status bar."""
        self.status_var = tk.StringVar(value="Ready")
        
        status_bar = ttk.Frame(self.main_frame)
        status_bar.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        
        ttk.Separator(status_bar, orient=tk.HORIZONTAL).pack(fill=tk.X)
        
        status_label = ttk.Label(status_bar, textvariable=self.status_var)
        status_label.pack(side=tk.LEFT, pady=(5, 0))
    
    def _show_frame(self, name: str):
        """Show a specific frame and hide others."""
        # Hide all frames
        for frame in self.frames.values():
            frame.grid_remove()
        
        # Show requested frame
        if name in self.frames:
            self.frames[name].grid()
            self.frames[name].on_show()
            
            # Update button states
            for nav_name, btn in self.nav_buttons.items():
                if nav_name == name:
                    btn.state(["disabled"])
                else:
                    btn.state(["!disabled"])
    
    def _on_start_scan(self, path: Path, options: dict):
        """Handle start scan request from home frame."""
        try:
            self.coordinator.add_recent_folder(path)
        except Exception:
            pass
        self._show_frame("scan")
        self.frames["scan"].start_scan(path, options)
        self.status_var.set(f"Scanning: {path}")
    
    def _on_scan_complete(self, result):
        """Handle scan completion."""
        self.last_result = result
        self.status_var.set(
            f"Scan complete: {len(result.duplicate_groups)} duplicate groups found"
        )
        
        # Auto-switch to results
        self.frames["results"].load_result(result)
        self._show_frame("results")
    
    def _on_scan_cancel(self):
        """Handle scan cancellation."""
        self.status_var.set("Scan cancelled")
        self._show_frame("home")
    
    def _on_delete_complete(self, result):
        """Handle deletion completion."""
        self.status_var.set(
            f"Deleted {len(result.deleted_files)} files, "
            f"{len(result.failed_files)} failed"
        )
    
    def _on_load_history_scan(self, scan_id: str):
        """Handle loading a scan from history."""
        result = self.coordinator.load_scan(scan_id)
        if result:
            self.last_result = result
            self.frames["results"].load_result(result)
            self._show_frame("results")

    def _on_resume_scan(self, scan_id: str):
        """Handle resume scan from History (continue from checkpoint)."""
        self._show_frame("scan")
        self.frames["scan"].start_resume(scan_id)
        self.status_var.set("Resuming scan...")
    
    def _on_close(self):
        """Handle window close."""
        # Cancel any active scan
        if self.coordinator.is_scanning:
            if messagebox.askyesno(
                "Scan in progress",
                "A scan is in progress. Cancel and exit?"
            ):
                self.coordinator.cancel_scan()
            else:
                return
        
        # Save config
        save_config(self.config)
        
        self.root.destroy()
    
    def run(self):
        """Run the application."""
        self.root.mainloop()


def main():
    """Main entry point."""
    app = DedupApp()
    app.run()


if __name__ == "__main__":
    main()
