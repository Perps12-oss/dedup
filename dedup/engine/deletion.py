"""
DEDUP Deletion Engine - Safe file deletion with audit trail.

Safety features:
- Dry-run mode for testing
- Trash/recycle bin support (not permanent deletion by default)
- Audit logging of all operations
- Confirmation requirements
- Error handling with detailed reporting
"""

from __future__ import annotations

import os
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable
import platform

from .models import (
    DeletionPlan,
    DeletionPolicy,
    DeletionResult,
    DeletionVerificationGroup,
    DeletionVerificationGroupStatus,
    DeletionVerificationResult,
    DeletionVerificationTarget,
    DeletionVerificationTargetStatus,
    FileMetadata,
)


class TrashStrategy:
    """Deletion strategy that prefers moving files to a recoverable trash."""

    def __init__(self, engine: "DeletionEngine"):
        self.engine = engine

    def delete(self, path: Path) -> tuple[bool, Optional[str]]:
        return self.engine._move_to_trash(path)


class PermanentDeleteStrategy:
    """Deletion strategy for irreversible deletes."""

    def __init__(self, engine: "DeletionEngine"):
        self.engine = engine

    def delete(self, path: Path) -> tuple[bool, Optional[str]]:
        return self.engine._delete_permanently(path)


@dataclass
class DeletionVerifier:
    """Revalidate delete targets before destructive operations."""

    def verify_target(self, target: Dict[str, Any]) -> Optional[str]:
        path = Path(target["path"])
        if not path.exists():
            return "File does not exist"

        try:
            st = path.stat()
        except (OSError, ValueError) as exc:
            return str(exc)

        expected_size = target.get("expected_size")
        if expected_size is not None and st.st_size != expected_size:
            return "File size changed"

        expected_mtime_ns = target.get("expected_mtime_ns")
        current_mtime_ns = getattr(st, "st_mtime_ns", int(st.st_mtime * 1_000_000_000))
        if expected_mtime_ns is not None and current_mtime_ns != expected_mtime_ns:
            return "File mtime changed"

        return None


@dataclass
class DeletionPlanner:
    """Build immutable deletion plans from duplicate groups."""

    engine: "DeletionEngine"

    def create_plan_from_groups(
        self,
        scan_id: str,
        groups: List[Any],
        policy: DeletionPolicy,
        keep_strategy: str,
        group_keep_paths: Optional[Dict[str, str]] = None,
    ) -> DeletionPlan:
        return self.engine._create_plan_from_groups(
            scan_id=scan_id,
            groups=groups,
            policy=policy,
            keep_strategy=keep_strategy,
            group_keep_paths=group_keep_paths,
        )


@dataclass
class DeletionExecutor:
    """Execute previously planned deletions after revalidation."""

    engine: "DeletionEngine"
    verifier: DeletionVerifier = field(default_factory=DeletionVerifier)

    def execute(
        self,
        plan: DeletionPlan,
        progress_cb: Optional[Callable[[int, int, str], bool]] = None,
    ) -> DeletionResult:
        return self.engine._execute_plan(plan, progress_cb=progress_cb, verifier=self.verifier)


@dataclass
class DeletionOutcomeVerifier:
    """Verify delete outcomes from the plan, not from a fresh scan."""

    engine: "DeletionEngine"

    def verify(self, plan: DeletionPlan, result: DeletionResult) -> DeletionVerificationResult:
        verification = DeletionVerificationResult(
            scan_id=plan.scan_id,
            plan_id=plan.scan_id,
            started_at=datetime.now(),
        )
        deleted_paths = set(result.deleted_files)

        for group in plan.groups:
            group_id = str(group.get("group_id", ""))
            group_statuses: List[DeletionVerificationTargetStatus] = []
            delete_details = group.get("delete_details") or [
                {"path": path}
                for path in group.get("delete", [])
            ]

            for target in delete_details:
                path = str(target.get("path", ""))
                status = DeletionVerificationTargetStatus.VERIFICATION_FAILED
                detail = ""

                if path in deleted_paths:
                    status = DeletionVerificationTargetStatus.DELETED
                else:
                    file_path = Path(path)
                    try:
                        st = file_path.stat()
                        current_mtime_ns = getattr(
                            st, "st_mtime_ns", int(st.st_mtime * 1_000_000_000)
                        )
                        expected_size = target.get("expected_size")
                        expected_mtime_ns = target.get("expected_mtime_ns")
                        if expected_size is None or expected_mtime_ns is None:
                            detail = "Missing expected metadata for verification"
                        elif st.st_size != expected_size or current_mtime_ns != expected_mtime_ns:
                            status = DeletionVerificationTargetStatus.CHANGED_AFTER_PLAN
                            detail = "File changed after plan creation"
                        else:
                            status = DeletionVerificationTargetStatus.STILL_PRESENT
                            detail = "File still present"
                    except FileNotFoundError:
                        status = DeletionVerificationTargetStatus.DELETED
                    except (OSError, ValueError) as exc:
                        detail = str(exc)

                verification.target_results.append(
                    DeletionVerificationTarget(
                        path=path,
                        status=status,
                        group_id=group_id,
                        detail=detail,
                    )
                )
                group_statuses.append(status)

            if any(
                status == DeletionVerificationTargetStatus.VERIFICATION_FAILED
                for status in group_statuses
            ):
                group_status = DeletionVerificationGroupStatus.VERIFICATION_INCOMPLETE
                group_detail = "One or more targets could not be verified"
            elif group_statuses and all(
                status == DeletionVerificationTargetStatus.DELETED
                for status in group_statuses
            ):
                group_status = DeletionVerificationGroupStatus.RESOLVED
                group_detail = "All delete targets are gone"
            elif any(
                status == DeletionVerificationTargetStatus.DELETED
                for status in group_statuses
            ):
                group_status = DeletionVerificationGroupStatus.PARTIALLY_RESOLVED
                group_detail = "Some delete targets still need attention"
            else:
                group_status = DeletionVerificationGroupStatus.UNRESOLVED
                group_detail = "No delete targets were confirmed removed"

            verification.group_results.append(
                DeletionVerificationGroup(
                    group_id=group_id,
                    status=group_status,
                    keep_path=str(group.get("keep", "")),
                    detail=group_detail,
                )
            )

        verification.summary = {
            "deleted": sum(
                1
                for item in verification.target_results
                if item.status == DeletionVerificationTargetStatus.DELETED
            ),
            "still_present": sum(
                1
                for item in verification.target_results
                if item.status == DeletionVerificationTargetStatus.STILL_PRESENT
            ),
            "changed_after_plan": sum(
                1
                for item in verification.target_results
                if item.status == DeletionVerificationTargetStatus.CHANGED_AFTER_PLAN
            ),
            "verification_failed": sum(
                1
                for item in verification.target_results
                if item.status == DeletionVerificationTargetStatus.VERIFICATION_FAILED
            ),
            "resolved_groups": sum(
                1
                for item in verification.group_results
                if item.status == DeletionVerificationGroupStatus.RESOLVED
            ),
            "partially_resolved_groups": sum(
                1
                for item in verification.group_results
                if item.status == DeletionVerificationGroupStatus.PARTIALLY_RESOLVED
            ),
            "unresolved_groups": sum(
                1
                for item in verification.group_results
                if item.status == DeletionVerificationGroupStatus.UNRESOLVED
            ),
            "verification_incomplete_groups": sum(
                1
                for item in verification.group_results
                if item.status == DeletionVerificationGroupStatus.VERIFICATION_INCOMPLETE
            ),
        }
        verification.summary.update(
            {
                "delete_targets_planned": len(verification.target_results),
                "delete_targets_verified_deleted": verification.summary["deleted"],
                "delete_targets_still_present": verification.summary["still_present"],
                "delete_targets_changed_after_plan": verification.summary["changed_after_plan"],
                "delete_groups_resolved": verification.summary["resolved_groups"],
                "delete_groups_partially_resolved": verification.summary["partially_resolved_groups"],
                "delete_groups_unresolved": verification.summary["unresolved_groups"],
            }
        )
        verification.completed_at = datetime.now()

        if self.engine.persistence:
            if self.engine.persistence.session_repo.get(plan.scan_id) is None:
                self.engine.persistence.shadow_write_session(
                    session_id=plan.scan_id,
                    config_json='{"roots":[]}',
                    config_hash="shadow",
                    discovery_config_hash="shadow",
                )
            overall_status = "resolved"
            if verification.summary["verification_failed"] or verification.summary["verification_incomplete_groups"]:
                overall_status = "verification_incomplete"
            elif verification.summary["still_present"] or verification.summary["changed_after_plan"]:
                overall_status = "needs_attention"
            self.engine.persistence.deletion_verification_repo.upsert(
                plan_id=verification.plan_id,
                session_id=plan.scan_id,
                status=overall_status,
                summary=verification.summary,
                detail=verification.to_dict(),
            )

        return verification


@dataclass
class DeletionEngine:
    """
    Safe file deletion engine.
    
    Supports:
    - Trash/recycle bin deletion (default, safer)
    - Permanent deletion (with explicit confirmation)
    - Dry-run mode for testing
    - Audit logging
    """
    
    dry_run: bool = False
    audit_log_path: Optional[Path] = None
    persistence: Optional[Any] = None
    
    def __post_init__(self):
        if self.audit_log_path:
            self.audit_log_path = Path(self.audit_log_path)
            self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
        self._strategies = {
            DeletionPolicy.TRASH: TrashStrategy(self),
            DeletionPolicy.PERMANENT: PermanentDeleteStrategy(self),
        }
    
    def _log_audit(self, operation: str, path: str, success: bool, error: Optional[str] = None):
        """Log deletion operation to audit log."""
        if not self.audit_log_path:
            return
        
        try:
            timestamp = datetime.now().isoformat()
            status = "SUCCESS" if success else "FAILED"
            error_str = f" | error: {error}" if error else ""
            
            with open(self.audit_log_path, 'a', encoding='utf-8') as f:
                f.write(f"[{timestamp}] {status} | {operation} | {path}{error_str}\n")
        except (OSError, IOError) as e:
            import logging
            logging.getLogger(__name__).warning("Audit log write failed: %s", e)
            try:
                from ..infrastructure.diagnostics import get_diagnostics_recorder, CATEGORY_AUDIT_LOG
                get_diagnostics_recorder().record(CATEGORY_AUDIT_LOG, "Audit log write failed", str(e))
            except Exception:
                pass
    
    def _move_to_trash_fallback(self, path: Path) -> tuple[bool, Optional[str]]:
        """Move file to ~/.dedup/trash (always works if we have write access)."""
        try:
            path = path.resolve()
            if not path.exists():
                return False, "File does not exist"
            trash_dir = Path.home() / ".dedup" / "trash"
            trash_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            dest = trash_dir / f"{timestamp}_{path.name}"
            counter = 1
            while dest.exists():
                dest = trash_dir / f"{timestamp}_{counter}_{path.name}"
                counter += 1
            shutil.move(str(path), str(dest))
            return True, None
        except Exception as e:
            return False, str(e)

    def _move_to_trash(self, path: Path) -> tuple[bool, Optional[str]]:
        """
        Move file to trash/recycle bin.
        Verifies the file is actually gone after the operation; if not, uses fallback.
        """
        path = path.resolve()
        if not path.exists():
            return False, "File does not exist"

        def _verified() -> bool:
            """Return True only if the file no longer exists at the original path."""
            try:
                return not path.exists()
            except OSError:
                return False

        try:
            # Try send2trash library (cross-platform)
            try:
                import send2trash
                send2trash.send2trash(str(path))
                if _verified():
                    return True, None
                # Reported success but file still there - try fallback
                return self._move_to_trash_fallback(path)
            except ImportError:
                pass
            except Exception as e:
                # send2trash failed - try fallback
                ok, _ = self._move_to_trash_fallback(path)
                if ok:
                    return True, None
                return False, str(e)

            # Platform-specific trash
            system = platform.system()

            if system == "Darwin":  # macOS
                import subprocess
                result = subprocess.run(
                    ['osascript', '-e', f'tell application "Finder" to delete POSIX file "{path}"'],
                    capture_output=True,
                    text=True
                )
                if result.returncode == 0 and _verified():
                    return True, None
                return self._move_to_trash_fallback(path)

            elif system == "Linux":
                for cmd in [['gio', 'trash', str(path)], ['xdg-trash', str(path)]]:
                    try:
                        import subprocess
                        result = subprocess.run(cmd, capture_output=True)
                        if result.returncode == 0 and _verified():
                            return True, None
                    except FileNotFoundError:
                        continue
                return self._move_to_trash_fallback(path)

            elif system == "Windows":
                try:
                    import winshell
                    winshell.delete_file(str(path))
                    if _verified():
                        return True, None
                except ImportError:
                    pass
                except Exception:
                    pass
                return self._move_to_trash_fallback(path)

            # Fallback: move to ~/.dedup/trash
            return self._move_to_trash_fallback(path)

        except Exception as e:
            return False, str(e)
    
    def _delete_permanently(self, path: Path) -> tuple[bool, Optional[str]]:
        """Permanently delete a file or directory. Verifies file is gone after."""
        path = path.resolve()
        if not path.exists():
            return False, "File does not exist"
        try:
            if path.is_file():
                os.remove(path)
            elif path.is_dir():
                shutil.rmtree(path)
            if path.exists():
                return False, "File still exists after delete"
            return True, None
        except Exception as e:
            return False, str(e)
    
    def delete_file(
        self,
        path: Path | str,
        policy: DeletionPolicy = DeletionPolicy.TRASH
    ) -> tuple[bool, Optional[str]]:
        """
        Delete a single file.
        
        Returns (success, error_message).
        """
        path = Path(path)
        
        if self.dry_run:
            self._log_audit(f"DRY_RUN_{policy.value}", str(path), True)
            return True, None

        success, error = self._strategies[policy].delete(path)
        
        self._log_audit(policy.value, str(path), success, error)
        return success, error
    
    def execute_plan(
        self,
        plan: DeletionPlan,
        progress_cb: Optional[Callable[[int, int, str], bool]] = None
    ) -> DeletionResult:
        return DeletionExecutor(self).execute(plan, progress_cb=progress_cb)

    def verify_plan_result(
        self,
        plan: DeletionPlan,
        result: DeletionResult,
    ) -> DeletionVerificationResult:
        return DeletionOutcomeVerifier(self).verify(plan, result)

    def _execute_plan(
        self,
        plan: DeletionPlan,
        progress_cb: Optional[Callable[[int, int, str], bool]] = None,
        verifier: Optional[DeletionVerifier] = None,
    ) -> DeletionResult:
        """
        Execute a deletion plan.
        
        Args:
            plan: The deletion plan to execute
            progress_cb: Callback(current, total, current_file) -> bool (continue?)
        
        Returns:
            DeletionResult with details of the operation
        """
        result = DeletionResult(
            scan_id=plan.scan_id,
            policy=plan.policy,
            started_at=datetime.now(),
        )
        
        # Count total files to delete
        total_files = plan.total_files_to_delete
        current = 0
        
        for group in plan.groups:
            keep_path = group.get("keep", "")
            delete_paths = group.get("delete", [])
            
            for file_path in delete_paths:
                current += 1
                
                # Report progress
                if progress_cb:
                    try:
                        should_continue = progress_cb(current, total_files, Path(file_path).name)
                        if not should_continue:
                            result.completed_at = datetime.now()
                            return result
                    except Exception:
                        pass
                
                # Safety check: never delete the keep file
                if Path(file_path).resolve() == Path(keep_path).resolve():
                    result.failed_files.append({
                        "path": file_path,
                        "error": "Cannot delete the designated keep file"
                    })
                    continue

                target_meta = next(
                    (
                        item
                        for item in group.get("delete_details", [])
                        if item.get("path") == file_path
                    ),
                    {"path": file_path},
                )
                if verifier:
                    verification_error = verifier.verify_target(target_meta)
                    if verification_error:
                        result.failed_files.append({
                            "path": file_path,
                            "error": verification_error,
                        })
                        if self.persistence:
                            self.persistence.deletion_audit_repo.log(
                                plan_id=plan.scan_id,
                                file_id=self.persistence.inventory_repo.get_file_id(plan.scan_id, file_path),
                                action=plan.policy.value,
                                outcome="skipped",
                                detail={"path": file_path, "error": verification_error},
                            )
                        continue
                
                # Get file size before deletion for bytes_reclaimed (truthful metric)
                try:
                    file_size = Path(file_path).stat().st_size
                except (OSError, ValueError):
                    file_size = 0
                
                # Delete the file
                success, error = self.delete_file(file_path, plan.policy)
                
                if success:
                    result.deleted_files.append(file_path)
                    result.bytes_reclaimed += file_size
                    if self.persistence:
                        self.persistence.deletion_audit_repo.log(
                            plan_id=plan.scan_id,
                            file_id=self.persistence.inventory_repo.get_file_id(plan.scan_id, file_path),
                            action=plan.policy.value,
                            outcome="success",
                            detail={"path": file_path},
                        )
                else:
                    result.failed_files.append({
                        "path": file_path,
                        "error": error or "Unknown error"
                    })
                    if self.persistence:
                        self.persistence.deletion_audit_repo.log(
                            plan_id=plan.scan_id,
                            file_id=self.persistence.inventory_repo.get_file_id(plan.scan_id, file_path),
                            action=plan.policy.value,
                            outcome="failed",
                            detail={"path": file_path, "error": error or "Unknown error"},
                        )
        
        result.completed_at = datetime.now()
        return result
    
    def create_plan_from_groups(
        self,
        scan_id: str,
        groups: List[Any],  # List of DuplicateGroup or dict
        policy: DeletionPolicy = DeletionPolicy.TRASH,
        keep_strategy: str = "first",  # first, oldest, newest, largest, smallest
        group_keep_paths: Optional[Dict[str, str]] = None,  # group_id -> path to keep (overrides strategy)
    ) -> DeletionPlan:
        return DeletionPlanner(self).create_plan_from_groups(
            scan_id=scan_id,
            groups=groups,
            policy=policy,
            keep_strategy=keep_strategy,
            group_keep_paths=group_keep_paths,
        )

    def _create_plan_from_groups(
        self,
        scan_id: str,
        groups: List[Any],
        policy: DeletionPolicy = DeletionPolicy.TRASH,
        keep_strategy: str = "first",
        group_keep_paths: Optional[Dict[str, str]] = None,
    ) -> DeletionPlan:
        """
        Create a deletion plan from duplicate groups.
        
        Args:
            scan_id: The scan ID
            groups: List of duplicate groups
            policy: Deletion policy
            keep_strategy: Which file to keep per group (used if group_keep_paths not set)
            group_keep_paths: Optional dict group_id -> path to keep; overrides keep_strategy when set
        
        Returns:
            DeletionPlan
        """
        plan_groups = []
        group_keep_paths = group_keep_paths or {}
        
        for group in groups:
            # Handle both DuplicateGroup objects and dicts
            if hasattr(group, 'files'):
                files = group.files
                group_id = getattr(group, 'group_id', str(uuid.uuid4())[:8])
            else:
                files = group.get('files', [])
                group_id = group.get('group_id', str(uuid.uuid4())[:8])
            
            if len(files) < 2:
                continue
            
            # Convert to FileMetadata if needed
            file_objects = []
            for f in files:
                if isinstance(f, FileMetadata):
                    file_objects.append(f)
                else:
                    file_objects.append(FileMetadata.from_dict(f) if isinstance(f, dict) else f)
            
            # Select which file to keep: explicit selection overrides strategy
            keep_path = group_keep_paths.get(group_id)
            if keep_path:
                keep_file = next((f for f in file_objects if f.path == keep_path), None)
                if not keep_file:
                    keep_file = file_objects[0]
            elif keep_strategy == "first":
                keep_file = file_objects[0]
            elif keep_strategy == "oldest":
                keep_file = min(file_objects, key=lambda f: f.mtime_ns)
            elif keep_strategy == "newest":
                keep_file = max(file_objects, key=lambda f: f.mtime_ns)
            elif keep_strategy == "largest":
                keep_file = max(file_objects, key=lambda f: f.size)
            elif keep_strategy == "smallest":
                keep_file = min(file_objects, key=lambda f: f.size)
            else:
                keep_file = file_objects[0]
            
            delete_files = [f for f in file_objects if f.path != keep_file.path]
            
            plan_groups.append({
                "group_id": group_id,
                "keep": keep_file.path,
                "delete": [f.path for f in delete_files],
                "delete_details": [
                    {
                        "path": f.path,
                        "expected_size": f.size,
                        "expected_mtime_ns": f.mtime_ns,
                        "expected_full_hash": f.hash_full,
                        "action": policy.value,
                    }
                    for f in delete_files
                ],
            })
        
        plan = DeletionPlan(
            scan_id=scan_id,
            policy=policy,
            groups=plan_groups,
        )
        if self.persistence:
            plan_id = scan_id
            self.persistence.deletion_plan_repo.create(
                plan_id=plan_id,
                session_id=scan_id,
                status="draft",
                policy=plan.to_dict(),
            )
            for group in plan.groups:
                for item in group.get("delete_details", []):
                    file_id = self.persistence.inventory_repo.get_file_id(scan_id, item["path"])
                    if file_id is None:
                        continue
                    self.persistence.deletion_plan_repo.add_item(
                        plan_id=plan_id,
                        file_id=file_id,
                        expected_size_bytes=item["expected_size"],
                        expected_mtime_ns=item["expected_mtime_ns"],
                        expected_full_hash=item.get("expected_full_hash") or "",
                        action=item["action"],
                    )
        return plan


def preview_deletion(plan: DeletionPlan) -> Dict[str, Any]:
    """
    Preview what a deletion plan would do without executing it.
    
    Returns summary information about the plan.
    """
    total_files = plan.total_files_to_delete
    
    # Calculate total size
    total_bytes = 0
    for group in plan.groups:
        for file_path in group.get("delete", []):
            try:
                st = Path(file_path).stat()
                total_bytes += st.st_size
            except (OSError, ValueError):
                pass
    
    return {
        "scan_id": plan.scan_id,
        "policy": plan.policy.value,
        "total_groups": len(plan.groups),
        "total_files": total_files,
        "total_bytes": total_bytes,
        "human_readable_size": _format_bytes(total_bytes),
    }


def _format_bytes(size_bytes: int) -> str:
    """Format bytes as human-readable string."""
    if size_bytes == 0:
        return "0 B"
    
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    size = float(size_bytes)
    unit_index = 0
    
    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1
    
    if unit_index == 0:
        return f"{int(size)} {units[unit_index]}"
    return f"{size:.2f} {units[unit_index]}"
