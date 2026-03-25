#!/usr/bin/env python3
"""
CEREBRO Dedup - Duplicate file finder and operations shell.

Production-grade engine and seven-destination UI (Mission, Scan, Review, History, Diagnostics, Themes, Settings).
Capable of handling 1,000,000+ files with store- and controller-driven architecture.

Usage:
    python -m dedup                    # Launch GUI
    python -m dedup /path/to/scan      # Quick CLI scan
"""

from __future__ import annotations

import argparse
import os
import sys
import traceback
from pathlib import Path

from dedup import __version__


def run_gui(ui_backend: str = "ctk"):
    """Run the graphical interface (default: CustomTkinter primary shell)."""
    if ui_backend == "ctk":
        try:
            from dedup.ui.ctk_app import CerebroCTKApp
        except ImportError:
            print("Error: CustomTkinter backend requested but dependency is missing.")
            print("Install with: pip install customtkinter")
            sys.exit(1)
        try:
            app = CerebroCTKApp()
            app.run()
        except Exception as ex:
            print("CTK backend failed during startup/runtime.")
            print(f"{type(ex).__name__}: {ex}")
            print(traceback.format_exc())
            raise
        return

    # Legacy ttkbootstrap shell (non-default).
    from dedup.ui.app import DedupApp

    app = DedupApp()
    app.run()


def run_cli_scan(path: Path, min_size: int = 1, verbose: bool = False):
    """Run a quick CLI scan."""
    from dedup.engine import ScanConfig, ScanPipeline
    from dedup.infrastructure.utils import format_bytes

    print(f"Scanning: {path}")
    print("-" * 50)

    config = ScanConfig(roots=[path], min_size_bytes=min_size)
    pipeline = ScanPipeline(config)

    def on_progress(progress):
        if verbose:
            print(f"\r{progress.phase}: {progress.files_found:,} files", end="", flush=True)

    result = pipeline.run(progress_cb=on_progress if verbose else None)

    print()  # New line after progress
    print("-" * 50)
    print(f"Scan complete in {result.duration_seconds:.1f}s")
    print(f"Files scanned: {result.files_scanned:,}")
    print(f"Duplicate groups: {len(result.duplicate_groups)}")
    print(f"Duplicate files: {result.total_duplicates}")
    print(f"Reclaimable space: {format_bytes(result.total_reclaimable_bytes)}")

    if result.duplicate_groups:
        print("\nDuplicate groups:")
        for i, group in enumerate(result.duplicate_groups[:10], 1):
            print(f"\n  Group {i}: {group.files[0].filename}")
            print(f"    Size: {format_bytes(group.files[0].size)}")
            print(f"    Files: {len(group.files)}")
            for file in group.files:
                print(f"      - {file.path}")

        if len(result.duplicate_groups) > 10:
            print(f"\n  ... and {len(result.duplicate_groups) - 10} more groups")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="DEDUP - Find and remove duplicate files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                    Launch GUI
  %(prog)s /data              Quick scan of /data
  %(prog)s /data --min-size 1M  Skip files smaller than 1MB
  %(prog)s /data -v           Verbose scan output
        """,
    )

    parser.add_argument("path", nargs="?", type=Path, help="Path to scan (if not provided, launches GUI)")

    parser.add_argument("--min-size", type=str, default="1", help="Minimum file size to consider (e.g., 1K, 1M, 1G)")

    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")

    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--ui-backend",
        choices=["ttk", "ctk"],
        default=os.environ.get("DEDUP_UI_BACKEND", "ctk"),
        help="GUI backend: ctk (primary) or ttk (legacy ttkbootstrap shell)",
    )

    args = parser.parse_args()

    # Parse min size
    min_size = 1
    if args.min_size:
        size_str = args.min_size.upper()
        try:
            if size_str.endswith("K"):
                min_size = int(size_str[:-1]) * 1024
            elif size_str.endswith("M"):
                min_size = int(size_str[:-1]) * 1024 * 1024
            elif size_str.endswith("G"):
                min_size = int(size_str[:-1]) * 1024 * 1024 * 1024
            else:
                min_size = int(size_str)
        except ValueError:
            print(f"Error: Invalid size format: {args.min_size}")
            sys.exit(1)

    # Run appropriate mode
    if args.path:
        run_cli_scan(args.path, min_size, args.verbose)
    else:
        run_gui(ui_backend=args.ui_backend)


if __name__ == "__main__":
    main()
