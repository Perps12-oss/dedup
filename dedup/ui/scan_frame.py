"""
DEDUP Scan Frame - Live scan monitoring.

Shows real-time progress of an active scan with truthful metrics.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from typing import Callable, Optional

from ..orchestration.coordinator import ScanCoordinator
from ..engine.models import ScanProgress, ScanResult


class ScanFrame(ttk.Frame):
    """
    Live scan monitoring screen.
    
    Displays:
    - Current phase
    - Files found/processed
    - Duplicate groups found
    - Elapsed time
    - Current file being processed
    - Cancel button
    
    All metrics are truthful - no fake progress bars or estimates.
    """
    
    def __init__(
        self,
        parent,
        coordinator: ScanCoordinator,
        on_complete: Callable[[ScanResult], None],
        on_cancel: Callable[[], None]
    ):
        super().__init__(parent, padding="20")
        
        self.coordinator = coordinator
        self.on_complete = on_complete
        self.on_cancel = on_cancel
        
        self.is_scanning = False
        self.start_time = 0
        self.after_id: Optional[str] = None
        
        self._build_ui()
    
    def _build_ui(self):
        """Build the UI components."""
        self.columnconfigure(0, weight=1)
        
        # Title
        self.title_label = ttk.Label(
            self,
            text="Scanning...",
            font=("TkDefaultFont", 16, "bold")
        )
        self.title_label.grid(row=0, column=0, sticky="w", pady=(0, 20))
        
        # Progress info frame
        info_frame = ttk.LabelFrame(self, text="Progress", padding="15")
        info_frame.grid(row=1, column=0, sticky="ew", pady=(0, 20))
        info_frame.columnconfigure(1, weight=1)
        
        # Phase
        ttk.Label(info_frame, text="Phase:").grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.phase_var = tk.StringVar(value="Starting...")
        ttk.Label(info_frame, textvariable=self.phase_var, font=("TkDefaultFont", 10, "bold")).grid(
            row=0, column=1, sticky="w"
        )
        
        # Files found
        ttk.Label(info_frame, text="Files found:").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=(10, 0))
        self.files_var = tk.StringVar(value="0")
        ttk.Label(info_frame, textvariable=self.files_var).grid(row=1, column=1, sticky="w", pady=(10, 0))
        
        # Duplicate groups
        ttk.Label(info_frame, text="Duplicate groups:").grid(row=2, column=0, sticky="w", padx=(0, 10), pady=(5, 0))
        self.groups_var = tk.StringVar(value="0")
        ttk.Label(info_frame, textvariable=self.groups_var).grid(row=2, column=1, sticky="w", pady=(5, 0))
        
        # Elapsed time
        ttk.Label(info_frame, text="Elapsed:").grid(row=3, column=0, sticky="w", padx=(0, 10), pady=(5, 0))
        self.elapsed_var = tk.StringVar(value="0s")
        ttk.Label(info_frame, textvariable=self.elapsed_var).grid(row=3, column=1, sticky="w", pady=(5, 0))

        # Throughput
        ttk.Label(info_frame, text="Throughput:").grid(row=4, column=0, sticky="w", padx=(0, 10), pady=(5, 0))
        self.throughput_var = tk.StringVar(value="—")
        ttk.Label(info_frame, textvariable=self.throughput_var).grid(row=4, column=1, sticky="w", pady=(5, 0))

        # ETA (truthful only; otherwise "Estimating...")
        ttk.Label(info_frame, text="ETA:").grid(row=5, column=0, sticky="w", padx=(0, 10), pady=(5, 0))
        self.eta_var = tk.StringVar(value="Estimating...")
        ttk.Label(info_frame, textvariable=self.eta_var).grid(row=5, column=1, sticky="w", pady=(5, 0))
        
        # Current file
        ttk.Label(info_frame, text="Current file:").grid(row=6, column=0, sticky="w", padx=(0, 10), pady=(10, 0))
        self.current_file_var = tk.StringVar(value="")
        self.current_file_label = ttk.Label(
            info_frame,
            textvariable=self.current_file_var,
            wraplength=400
        )
        self.current_file_label.grid(row=6, column=1, sticky="w", pady=(10, 0))
        
        # Progress bar (indeterminate - we don't fake progress percentages)
        self.progress = ttk.Progressbar(
            self,
            mode="indeterminate",
            length=400
        )
        self.progress.grid(row=2, column=0, pady=(20, 0))
        
        # Cancel button
        self.cancel_btn = ttk.Button(
            self,
            text="Cancel Scan",
            command=self._on_cancel
        )
        self.cancel_btn.grid(row=3, column=0, pady=(20, 0))
    
    def start_scan(self, path: Path, options: dict):
        """Start a new scan."""
        self.is_scanning = True
        self.title_label.config(text=f"Scanning: {path.name}")
        self._set_progress_mode(indeterminate=True)
        
        # Reset display
        self.phase_var.set("Starting...")
        self.files_var.set("0")
        self.groups_var.set("0")
        self.elapsed_var.set("0s")
        self.throughput_var.set("—")
        self.eta_var.set("Estimating...")
        self.current_file_var.set("")
        
        # Start the scan
        import time
        self.start_time = time.time()
        
        self.coordinator.start_scan(
            roots=[path],
            on_progress=self._on_progress,
            on_complete=self._on_complete,
            on_error=self._on_error,
            **options
        )
        
        # Start elapsed time updates
        self._update_elapsed()

    def start_resume(self, scan_id: str):
        """Resume a scan from checkpoint (no folder selection)."""
        self.is_scanning = True
        self.title_label.config(text="Resuming scan...")
        self._set_progress_mode(indeterminate=True)
        self.phase_var.set("Resuming...")
        self.files_var.set("0")
        self.groups_var.set("0")
        self.elapsed_var.set("0s")
        self.throughput_var.set("—")
        self.eta_var.set("Estimating...")
        self.current_file_var.set("")
        import time
        self.start_time = time.time()
        self.coordinator.start_scan(
            roots=[],
            resume_scan_id=scan_id,
            on_progress=self._on_progress,
            on_complete=self._on_complete,
            on_error=self._on_error,
        )
        self._update_elapsed()
    
    def _on_progress(self, progress: ScanProgress):
        """Handle progress update."""
        # Update UI (thread-safe via tkinter's thread safety)
        self.after(0, lambda: self._update_display(progress))
    
    def _update_display(self, progress: ScanProgress):
        """Update the display with progress info."""
        if not self.is_scanning:
            return
        
        self.phase_var.set(progress.phase_description or progress.phase)
        self.files_var.set(f"{progress.files_found:,}")
        self.groups_var.set(f"{progress.groups_found:,}")

        # Throughput: real measured value when available; fallback to observed ratio.
        files_per_sec = progress.files_per_second
        if files_per_sec is None and progress.elapsed_seconds > 0 and progress.files_found > 0:
            files_per_sec = progress.files_found / progress.elapsed_seconds
        if files_per_sec and files_per_sec > 0:
            self.throughput_var.set(f"{files_per_sec:,.1f} files/s")
        else:
            self.throughput_var.set("—")

        # ETA: show only when denominator + stable throughput are available.
        eta_seconds = progress.estimated_remaining_seconds
        if eta_seconds is None and progress.files_total and files_per_sec and files_per_sec > 0:
            remaining = max(progress.files_total - progress.files_found, 0)
            # only show ETA after at least 1 second of measurements
            if progress.elapsed_seconds >= 1.0 and progress.files_found > 0:
                eta_seconds = remaining / files_per_sec
        if eta_seconds is not None:
            eta_s = int(max(eta_seconds, 0))
            if eta_s < 60:
                self.eta_var.set(f"{eta_s}s")
            elif eta_s < 3600:
                self.eta_var.set(f"{eta_s // 60}m {eta_s % 60}s")
            else:
                self.eta_var.set(f"{eta_s // 3600}h {(eta_s % 3600) // 60}m")
        else:
            self.eta_var.set("Estimating...")

        # Determinate progress only when the denominator is real.
        if progress.percent_complete is not None:
            self._set_progress_mode(indeterminate=False)
            self.progress["value"] = progress.percent_complete
        else:
            self._set_progress_mode(indeterminate=True)
        
        if progress.current_file:
            # Truncate long paths
            path = progress.current_file
            if len(path) > 60:
                path = "..." + path[-57:]
            self.current_file_var.set(path)
    
    def _update_elapsed(self):
        """Update elapsed time display."""
        if not self.is_scanning:
            return
        
        import time
        elapsed = int(time.time() - self.start_time)
        
        if elapsed < 60:
            self.elapsed_var.set(f"{elapsed}s")
        elif elapsed < 3600:
            minutes = elapsed // 60
            seconds = elapsed % 60
            self.elapsed_var.set(f"{minutes}m {seconds}s")
        else:
            hours = elapsed // 3600
            minutes = (elapsed % 3600) // 60
            self.elapsed_var.set(f"{hours}h {minutes}m")
        
        # Schedule next update
        self.after_id = self.after(1000, self._update_elapsed)

    def _set_progress_mode(self, indeterminate: bool):
        """Switch progress mode safely without fake precision."""
        current_mode = str(self.progress.cget("mode"))
        target_mode = "indeterminate" if indeterminate else "determinate"
        if current_mode == target_mode:
            if indeterminate:
                self.progress.start(10)
            return
        self.progress.stop()
        self.progress.configure(mode=target_mode)
        if indeterminate:
            self.progress.start(10)
    
    def _on_complete(self, result: ScanResult):
        """Handle scan completion."""
        self.is_scanning = False
        self.progress.stop()
        
        if self.after_id:
            self.after_cancel(self.after_id)
        
        self.after(0, lambda: self.on_complete(result))
    
    def _on_error(self, error: str):
        """Handle scan error."""
        self.is_scanning = False
        self.progress.stop()
        
        if self.after_id:
            self.after_cancel(self.after_id)
        
        self.after(0, lambda: messagebox.showerror("Scan Error", f"Scan failed: {error}"))
        self.after(0, self.on_cancel)
    
    def _on_cancel(self):
        """Handle cancel button."""
        if self.is_scanning:
            if messagebox.askyesno("Cancel Scan", "Are you sure you want to cancel the scan?"):
                self.coordinator.cancel_scan()
                self.is_scanning = False
                self.progress.stop()
                
                if self.after_id:
                    self.after_cancel(self.after_id)
                
                self.on_cancel()
    
    def on_show(self):
        """Called when frame is shown."""
        pass
