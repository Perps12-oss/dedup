"""
Deletion safety: plan matches selection; keep file never deleted.
"""

from __future__ import annotations

import pytest
from pathlib import Path

from dedup.engine.models import (
    FileMetadata, DuplicateGroup, DeletionPlan, DeletionResult,
    DeletionPolicy,
)
from dedup.engine.deletion import DeletionEngine, DeletionVerifier, preview_deletion


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
