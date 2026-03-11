"""
DEDUP Results Frame - Review and delete duplicates.

Shows duplicate groups and allows selection of files to delete.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from typing import Callable, Optional, List

from ..orchestration.coordinator import ScanCoordinator
from ..engine.models import ScanResult, DuplicateGroup, FileMetadata, DeletionPlan, DeletionResult
from ..engine.thumbnails import generate_thumbnails_async, get_cache_dir
from ..engine.media_types import is_image_extension
from ..infrastructure.utils import format_bytes


class ResultsFrame(ttk.Frame):
    """
    Results review screen.
    
    Displays:
    - Summary of duplicates found
    - List of duplicate groups
    - Selection of files to keep/delete
    - Preview of deletion impact
    - Execute deletion with confirmation
    """
    
    def __init__(
        self,
        parent,
        coordinator: ScanCoordinator,
        on_delete_complete: Callable[[DeletionResult], None]
    ):
        super().__init__(parent, padding="20")
        
        self.coordinator = coordinator
        self.on_delete_complete = on_delete_complete
        
        self.current_result: Optional[ScanResult] = None
        self.selected_groups: dict = {}  # group_id -> keep_path
        
        self._build_ui()
    
    def _build_ui(self):
        """Build the UI components."""
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        
        # Title
        self.title_label = ttk.Label(
            self,
            text="No Results",
            font=("TkDefaultFont", 16, "bold")
        )
        self.title_label.grid(row=0, column=0, sticky="w", pady=(0, 10))
        
        # Summary frame
        self.summary_frame = ttk.LabelFrame(self, text="Summary", padding="10")
        self.summary_frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        
        self.summary_var = tk.StringVar(value="No scan results to display")
        ttk.Label(self.summary_frame, textvariable=self.summary_var).pack(anchor="w")
        
        # Groups list with scrollbar
        list_frame = ttk.Frame(self)
        list_frame.grid(row=2, column=0, sticky="nsew", pady=(0, 10))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        
        # Treeview for groups
        columns = ("size", "count", "reclaimable")
        self.tree = ttk.Treeview(
            list_frame,
            columns=columns,
            show="tree headings",
            selectmode="browse"
        )
        
        self.tree.heading("#0", text="Duplicate Group")
        self.tree.heading("size", text="File Size")
        self.tree.heading("count", text="Files")
        self.tree.heading("reclaimable", text="Reclaimable")
        
        self.tree.column("#0", width=300)
        self.tree.column("size", width=100, anchor="e")
        self.tree.column("count", width=60, anchor="center")
        self.tree.column("reclaimable", width=100, anchor="e")
        
        # Scrollbars
        vsb = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(list_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        
        # Bind selection
        self.tree.bind("<<TreeviewSelect>>", self._on_select_group)
        
        # Details frame
        self.details_frame = ttk.LabelFrame(self, text="Files in Group", padding="10")
        self.details_frame.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        self.details_frame.columnconfigure(0, weight=1)
        
        self._selected_group_id: Optional[str] = None
        self._selected_group: Optional[DuplicateGroup] = None
        self._thumbnail_refs: list = []  # Keep PhotoImage refs for GC

        # Thumbnail strip for image groups (only populated when Pillow available)
        self.thumbnail_frame = ttk.Frame(self.details_frame)
        self.thumbnail_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 5))
        self.thumbnail_frame.columnconfigure(0, weight=1)

        self.files_list = tk.Listbox(self.details_frame, height=5)
        self.files_list.grid(row=1, column=0, sticky="ew")
        
        files_scroll = ttk.Scrollbar(self.details_frame, orient="vertical", command=self.files_list.yview)
        files_scroll.grid(row=1, column=1, sticky="ns")
        self.files_list.configure(yscrollcommand=files_scroll.set)
        
        keep_btn_frame = ttk.Frame(self.details_frame)
        keep_btn_frame.grid(row=2, column=0, columnspan=2, sticky="w", pady=(5, 0))
        ttk.Button(
            keep_btn_frame,
            text="Keep this file",
            command=self._on_keep_this_file,
        ).pack(side=tk.LEFT)
        
        # Actions frame
        actions_frame = ttk.Frame(self)
        actions_frame.grid(row=4, column=0, sticky="ew")
        
        self.delete_btn = ttk.Button(
            actions_frame,
            text="Delete Duplicates...",
            command=self._on_delete,
            state="disabled"
        )
        self.delete_btn.pack(side=tk.RIGHT)
        
        self.preview_btn = ttk.Button(
            actions_frame,
            text="Preview Deletion",
            command=self._on_preview,
            state="disabled"
        )
        self.preview_btn.pack(side=tk.RIGHT, padx=(0, 10))
    
    def load_result(self, result: ScanResult):
        """Load a scan result for display."""
        self.current_result = result
        self.selected_groups = {}
        
        # Update title
        group_count = len(result.duplicate_groups)
        self.title_label.config(
            text=f"{group_count} Duplicate Group{'s' if group_count != 1 else ''} Found"
        )
        
        # Update summary
        total_dupes = sum(len(g.files) - 1 for g in result.duplicate_groups)
        reclaimable = sum(g.reclaimable_size for g in result.duplicate_groups)
        
        self.summary_var.set(
            f"Files scanned: {result.files_scanned:,} | "
            f"Duplicate files: {total_dupes:,} | "
            f"Space reclaimable: {format_bytes(reclaimable)}"
        )
        
        # Populate tree
        self._populate_tree()
        
        # Enable buttons if there are duplicates
        if result.duplicate_groups:
            self.delete_btn.config(state="normal")
            self.preview_btn.config(state="normal")
        else:
            self.delete_btn.config(state="disabled")
            self.preview_btn.config(state="disabled")
    
    def _populate_tree(self):
        """Populate the tree with duplicate groups."""
        # Clear existing
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        if not self.current_result:
            return
        
        # Add groups
        for group in self.current_result.duplicate_groups:
            if not group.files:
                continue
            
            # Use first file's name as group name
            first_file = group.files[0]
            group_name = first_file.filename
            
            # Insert group
            group_id = self.tree.insert(
                "",
                "end",
                text=group_name,
                values=(
                    format_bytes(first_file.size),
                    len(group.files),
                    format_bytes(group.reclaimable_size)
                ),
                tags=(group.group_id,)
            )
            
            # Store default keep selection (first file)
            self.selected_groups[group.group_id] = first_file.path
    
    def _on_select_group(self, event):
        """Handle group selection."""
        selection = self.tree.selection()
        if not selection:
            return
        
        # Get selected group
        item = selection[0]
        group_id = self.tree.item(item, "tags")[0] if self.tree.item(item, "tags") else None
        
        if not group_id or not self.current_result:
            return
        
        # Find group
        group = None
        for g in self.current_result.duplicate_groups:
            if g.group_id == group_id:
                group = g
                break
        
        if not group:
            return
        
        self._selected_group_id = group_id
        self._selected_group = group

        # Clear and repopulate thumbnail strip for image groups
        self._thumbnail_refs.clear()
        for w in self.thumbnail_frame.winfo_children():
            w.destroy()
        paths = [f.path for f in group.files]
        if any(is_image_extension(Path(f.path).suffix) for f in group.files):
            def on_thumb(file_path: str, thumb_path: Optional[Path]):
                def update():
                    if thumb_path is not None and thumb_path.exists():
                        try:
                            from tkinter import PhotoImage
                            img = PhotoImage(file=str(thumb_path))
                            self._thumbnail_refs.append(img)
                            lbl = ttk.Label(self.thumbnail_frame, image=img)
                            lbl.image = img
                            lbl.pack(side=tk.LEFT, padx=2)
                        except Exception:
                            pass
                self.after(0, update)
            generate_thumbnails_async(paths, on_thumb, cache_dir=get_cache_dir())
        
        # Update files list
        self.files_list.delete(0, tk.END)
        
        for file in group.files:
            keep_marker = " [KEEP]" if file.path == self.selected_groups.get(group_id) else ""
            self.files_list.insert(tk.END, f"{file.filename}{keep_marker}")
            self.files_list.insert(tk.END, f"  {file.path}")
    
    def _on_keep_this_file(self):
        """Set the selected file in the list as the one to keep for this group."""
        if not self._selected_group_id or not self._selected_group:
            return
        selection = self.files_list.curselection()
        if not selection:
            return
        # List has 2 lines per file: filename, then path. Index 0,1 = file 0; 2,3 = file 1; etc.
        idx = selection[0] // 2
        if idx < 0 or idx >= len(self._selected_group.files):
            return
        keep_path = self._selected_group.files[idx].path
        self.selected_groups[self._selected_group_id] = keep_path
        # Refresh files list to show updated [KEEP] marker
        self.files_list.delete(0, tk.END)
        for file in self._selected_group.files:
            keep_marker = " [KEEP]" if file.path == self.selected_groups.get(self._selected_group_id) else ""
            self.files_list.insert(tk.END, f"{file.filename}{keep_marker}")
            self.files_list.insert(tk.END, f"  {file.path}")
    
    def _on_preview(self):
        """Preview deletion impact."""
        if not self.current_result:
            return
        
        plan = self._create_deletion_plan()
        if not plan or not plan.groups:
            messagebox.showinfo("Preview", "No files selected for deletion")
            return
        
        from ..engine.deletion import preview_deletion
        preview = preview_deletion(plan)
        
        message = (
            f"Deletion Preview:\n\n"
            f"Groups: {preview['total_groups']}\n"
            f"Files to delete: {preview['total_files']}\n"
            f"Space to reclaim: {preview['human_readable_size']}\n\n"
            f"Policy: {preview['policy']}"
        )
        
        messagebox.showinfo("Deletion Preview", message)
    
    def _on_delete(self):
        """Handle delete button."""
        if not self.current_result:
            return
        
        plan = self._create_deletion_plan()
        if not plan or not plan.groups:
            messagebox.showinfo("Delete", "No files selected for deletion")
            return
        
        # Confirm deletion
        from ..engine.deletion import preview_deletion
        preview = preview_deletion(plan)
        
        confirm = messagebox.askyesno(
            "Confirm Deletion",
            f"Delete {preview['total_files']} duplicate files?\n\n"
            f"This will reclaim {preview['human_readable_size']} of space.\n\n"
            f"Files will be moved to trash (not permanently deleted).\n\n"
            f"Do you want to proceed?"
        )
        
        if not confirm:
            return
        
        # Execute deletion
        self.delete_btn.config(state="disabled", text="Deleting...")
        self.update()
        
        result = self.coordinator.execute_deletion(plan)
        
        self.delete_btn.config(state="normal", text="Delete Duplicates...")
        
        # Show result
        if result.failed_files:
            messagebox.showwarning(
                "Deletion Complete",
                f"Deleted: {len(result.deleted_files)} files\n"
                f"Failed: {len(result.failed_files)} files\n\n"
                f"See logs for details on failed deletions."
            )
        else:
            messagebox.showinfo(
                "Deletion Complete",
                f"Successfully deleted {len(result.deleted_files)} files."
            )
        
        self.on_delete_complete(result)

        # Update result: remove successfully deleted files from groups so UI reflects reality
        if result.deleted_files:
            deleted_set = set(result.deleted_files)
            new_groups = []
            for group in self.current_result.duplicate_groups:
                remaining = [f for f in group.files if f.path not in deleted_set]
                if len(remaining) >= 2:
                    new_group = DuplicateGroup(
                        group_id=group.group_id,
                        group_hash=group.group_hash,
                        files=remaining,
                    )
                    new_groups.append(new_group)
                elif len(remaining) == 1:
                    # Only "keep" left - no longer a duplicate group
                    pass
            self.current_result.duplicate_groups = new_groups
            self.current_result.total_duplicates = sum(len(g.files) - 1 for g in new_groups)
            self.current_result.total_reclaimable_bytes = sum(g.reclaimable_size for g in new_groups)

        # Refresh display
        self.load_result(self.current_result)
    
    def _create_deletion_plan(self) -> Optional[DeletionPlan]:
        """Create a deletion plan from current selections (respects user's Keep choices)."""
        if not self.current_result:
            return None
        
        return self.coordinator.create_deletion_plan(
            self.current_result,
            keep_strategy="first",
            group_keep_paths=self.selected_groups if self.selected_groups else None,
        )
    
    def on_show(self):
        """Called when frame is shown."""
        pass
