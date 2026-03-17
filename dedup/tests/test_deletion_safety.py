"""
Deletion safety: plan matches selection; keep file never deleted.

Characterisation tests: preview_deletion, delete_file dry_run, progress_cb stop, audit log.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dedup.engine.models import (
    FileMetadata, DuplicateGroup, DeletionPlan, DeletionResult,
    DeletionPolicy,
    DeletionVerificationGroupStatus,
    DeletionVerificationTargetStatus,
)
from dedup.engine.deletion import DeletionEngine, DeletionVerifier, preview_deletion
from dedup.infrastructure.persistence import Persistence


def test_plan_keep_not_in_delete_list():
    group = DuplicateGroup(
        group_id="g1",
        group_hash="h1",
        files=[
            FileMetadata(path="/keep/this", size=100, mtime_ns=0),
            FileMetadata(path="/delete/1", size=100, mtime_ns=0),
            FileMetadata(path="/delete/2", size=100, mtime_ns=0),
        ],
    )
    engine = DeletionEngine()
    plan = engine.create_plan_from_groups(
        scan_id="s1",
        groups=[group],
        policy=DeletionPolicy.TRASH,
        keep_strategy="first",
    )
    assert len(plan.groups) == 1
    keep = plan.groups[0]["keep"]
    delete_list = plan.groups[0]["delete"]
    assert keep == "/keep/this"
    assert "/keep/this" not in delete_list
    assert len(delete_list) == 2


def test_plan_respects_group_keep_paths():
    group = DuplicateGroup(
        group_id="g1",
        group_hash="h1",
        files=[
            FileMetadata(path="/first", size=100, mtime_ns=0),
            FileMetadata(path="/second", size=100, mtime_ns=0),
            FileMetadata(path="/third", size=100, mtime_ns=0),
        ],
    )
    engine = DeletionEngine()
    plan = engine.create_plan_from_groups(
        scan_id="s1",
        groups=[group],
        policy=DeletionPolicy.TRASH,
        keep_strategy="first",
        group_keep_paths={"g1": "/third"},
    )
    assert plan.groups[0]["keep"] == "/third"
    assert "/third" not in plan.groups[0]["delete"]
    assert "/first" in plan.groups[0]["delete"]
    assert "/second" in plan.groups[0]["delete"]


def test_execute_plan_never_deletes_keep(temp_dir):
    keep_file = temp_dir / "keep.txt"
    del_file = temp_dir / "del.txt"
    keep_file.write_text("keep")
    del_file.write_text("del")
    plan = DeletionPlan(
        scan_id="s1",
        policy=DeletionPolicy.TRASH,
        groups=[{
            "group_id": "g1",
            "keep": str(keep_file.resolve()),
            "delete": [str(del_file.resolve())],
        }],
    )
    engine = DeletionEngine(dry_run=True)
    result = engine.execute_plan(plan)
    assert keep_file.exists()
    assert result.success_count <= 1
    # In dry run we don't actually delete; keep_file must not be in failed with "Cannot delete keep"
    for fail in result.failed_files:
        assert "keep" not in fail.get("error", "").lower() or "designated keep" in fail.get("error", "")


def test_plan_records_delete_target_metadata():
    group = DuplicateGroup(
        group_id="g2",
        group_hash="h2",
        files=[
            FileMetadata(path="/keep", size=10, mtime_ns=1, hash_full="full-1"),
            FileMetadata(path="/delete", size=10, mtime_ns=2, hash_full="full-1"),
        ],
    )
    engine = DeletionEngine()
    plan = engine.create_plan_from_groups("s2", [group])
    details = plan.groups[0]["delete_details"]
    assert details[0]["path"] == "/delete"
    assert details[0]["expected_size"] == 10
    assert details[0]["expected_mtime_ns"] == 2


def test_verifier_rejects_changed_file(temp_dir):
    path = temp_dir / "file.txt"
    path.write_text("old")
    expected_size = path.stat().st_size
    expected_mtime_ns = path.stat().st_mtime_ns
    path.write_text("new content")

    verifier = DeletionVerifier()
    error = verifier.verify_target(
        {
            "path": str(path),
            "expected_size": expected_size,
            "expected_mtime_ns": expected_mtime_ns,
        }
    )
    assert error in {"File size changed", "File mtime changed"}


def test_verifier_rejects_non_file_target(temp_dir):
    verifier = DeletionVerifier()
    error = verifier.verify_target({"path": str(temp_dir)})
    assert error == "Delete target must be a file"


def test_execute_plan_rejects_paths_outside_allowed_roots(temp_dir):
    inside = temp_dir / "inside.txt"
    outside = temp_dir.parent / "outside.txt"
    inside.write_text("inside")
    outside.write_text("outside")
    try:
        plan = DeletionPlan(
            scan_id="safe-1",
            policy=DeletionPolicy.TRASH,
            groups=[{
                "group_id": "g1",
                "keep": str(inside.resolve()),
                "delete": [str(outside.resolve())],
                "allowed_roots": [str(temp_dir.resolve())],
            }],
        )
        result = DeletionEngine(dry_run=True).execute_plan(plan)
        assert result.success_count == 0
        assert result.failure_count == 1
        assert "outside allowed scan roots" in result.failed_files[0]["error"]
    finally:
        if outside.exists():
            outside.unlink()


def test_post_delete_verification_marks_deleted_targets(temp_dir):
    deleted_path = temp_dir / "deleted.txt"
    deleted_path.write_text("x")
    plan = DeletionPlan(
        scan_id="scan-verify-1",
        policy=DeletionPolicy.TRASH,
        groups=[{
            "group_id": "g1",
            "keep": str(temp_dir / "keep.txt"),
            "delete": [str(deleted_path)],
            "delete_details": [{
                "path": str(deleted_path),
                "expected_size": deleted_path.stat().st_size,
                "expected_mtime_ns": deleted_path.stat().st_mtime_ns,
            }],
        }],
    )
    result = DeletionResult(
        scan_id=plan.scan_id,
        policy=plan.policy,
        deleted_files=[str(deleted_path)],
    )

    verification = DeletionEngine().verify_plan_result(plan, result)
    assert verification.summary["deleted"] == 1
    assert verification.summary["delete_targets_verified_deleted"] == 1
    assert verification.summary["delete_groups_resolved"] == 1
    assert verification.target_results[0].status == DeletionVerificationTargetStatus.DELETED
    assert verification.group_results[0].status == DeletionVerificationGroupStatus.RESOLVED


def test_post_delete_verification_marks_changed_after_plan(temp_dir):
    changed_path = temp_dir / "changed.txt"
    changed_path.write_text("before")
    expected_size = changed_path.stat().st_size
    expected_mtime_ns = changed_path.stat().st_mtime_ns
    changed_path.write_text("after and longer")

    plan = DeletionPlan(
        scan_id="scan-verify-2",
        policy=DeletionPolicy.TRASH,
        groups=[{
            "group_id": "g1",
            "keep": str(temp_dir / "keep.txt"),
            "delete": [str(changed_path)],
            "delete_details": [{
                "path": str(changed_path),
                "expected_size": expected_size,
                "expected_mtime_ns": expected_mtime_ns,
            }],
        }],
    )

    verification = DeletionEngine().verify_plan_result(
        plan,
        DeletionResult(scan_id=plan.scan_id, policy=plan.policy),
    )
    assert verification.summary["changed_after_plan"] == 1
    assert verification.target_results[0].status == DeletionVerificationTargetStatus.CHANGED_AFTER_PLAN
    assert verification.group_results[0].status == DeletionVerificationGroupStatus.UNRESOLVED


def test_post_delete_verification_persists_summary(temp_dir):
    persistence = Persistence(db_path=temp_dir / "delete-verify.db")
    try:
        target = temp_dir / "target.txt"
        target.write_text("x")
        plan = DeletionPlan(
            scan_id="scan-verify-3",
            policy=DeletionPolicy.TRASH,
            groups=[{
                "group_id": "g1",
                "keep": str(temp_dir / "keep.txt"),
                "delete": [str(target)],
                "delete_details": [{
                    "path": str(target),
                    "expected_size": target.stat().st_size,
                    "expected_mtime_ns": target.stat().st_mtime_ns,
                }],
            }],
        )
        verification = DeletionEngine(persistence=persistence).verify_plan_result(
            plan,
            DeletionResult(scan_id=plan.scan_id, policy=plan.policy),
        )
        stored = persistence.deletion_verification_repo.get_latest_for_session(plan.scan_id)
        assert stored is not None
        assert stored["summary_json"] == verification.summary
    finally:
        persistence.close()


def test_preview_deletion_returns_summary(temp_dir):
    """preview_deletion returns dict with scan_id, policy, total_files, total_bytes."""
    f1 = temp_dir / "a.txt"
    f2 = temp_dir / "b.txt"
    f1.write_text("x" * 100)
    f2.write_text("y" * 200)
    plan = DeletionPlan(
        scan_id="preview-1",
        policy=DeletionPolicy.TRASH,
        groups=[{
            "group_id": "g1",
            "keep": str(f1.resolve()),
            "delete": [str(f2.resolve())],
        }],
    )
    out = preview_deletion(plan)
    assert out["scan_id"] == "preview-1"
    assert out["policy"] == "trash"
    assert out["total_files"] == 1
    assert out["total_groups"] == 1
    assert "total_bytes" in out
    assert "human_readable_size" in out


def test_delete_file_dry_run_returns_success(temp_dir):
    """delete_file in dry_run mode returns (True, None) without deleting."""
    path = temp_dir / "dry.txt"
    path.write_text("content")
    engine = DeletionEngine(dry_run=True)
    success, err = engine.delete_file(path, DeletionPolicy.PERMANENT)
    assert success is True
    assert err is None
    assert path.exists()


def test_execute_plan_stops_when_progress_cb_returns_false(temp_dir):
    """execute_plan stops early when progress_cb returns False."""
    keep_f = temp_dir / "keep.txt"
    del_f = temp_dir / "del1.txt"
    del_f2 = temp_dir / "del2.txt"
    keep_f.write_text("k")
    del_f.write_text("a")
    del_f2.write_text("b")
    plan = DeletionPlan(
        scan_id="stop-1",
        policy=DeletionPolicy.TRASH,
        groups=[{
            "group_id": "g1",
            "keep": str(keep_f.resolve()),
            "delete": [str(del_f.resolve()), str(del_f2.resolve())],
            "allowed_roots": [str(temp_dir.resolve())],
        }],
    )
    call_count = 0

    def stop_after_first(_cur, _total, _name):
        nonlocal call_count
        call_count += 1
        return call_count < 2

    engine = DeletionEngine(dry_run=True)
    result = engine.execute_plan(plan, progress_cb=stop_after_first)
    assert result.completed_at is not None
    assert call_count >= 1
    assert len(result.deleted_files) <= 1
