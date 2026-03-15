"""Repositories for candidate, hash, result, and deletion artifacts."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Dict, Iterable, List, Optional


class SizeCandidateRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def replace_group(self, session_id: str, size_bytes: int, file_ids: Iterable[int]) -> int:
        file_ids = list(file_ids)
        self.conn.execute(
            "DELETE FROM size_candidates WHERE session_id = ? AND size_bytes = ?",
            (session_id, size_bytes),
        )
        if not file_ids:
            self.conn.commit()
            return 0
        self.conn.executemany(
            "INSERT INTO size_candidates (session_id, size_bytes, file_id) VALUES (?, ?, ?)",
            [(session_id, size_bytes, file_id) for file_id in file_ids],
        )
        self.conn.commit()
        return len(file_ids)

    def iter_groups(self, session_id: str) -> Dict[int, List[int]]:
        rows = self.conn.execute(
            """
            SELECT size_bytes, file_id
            FROM size_candidates
            WHERE session_id = ?
            ORDER BY size_bytes ASC, file_id ASC
            """,
            (session_id,),
        ).fetchall()
        groups: Dict[int, List[int]] = {}
        for row in rows:
            groups.setdefault(row["size_bytes"], []).append(row["file_id"])
        return groups


class PartialHashRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def upsert(
        self,
        session_id: str,
        file_id: int,
        algorithm: str,
        strategy_version: str,
        sample_spec: Dict[str, object],
        partial_hash: str,
    ) -> None:
        self.conn.execute(
            """
            INSERT OR REPLACE INTO partial_hashes (
                session_id, file_id, algorithm, strategy_version,
                sample_spec_json, partial_hash, computed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                file_id,
                algorithm,
                strategy_version,
                json.dumps(sample_spec),
                partial_hash,
                datetime.now().isoformat(),
            ),
        )
        self.conn.commit()


class PartialCandidateRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def replace_group(self, session_id: str, partial_hash: str, file_ids: Iterable[int]) -> int:
        file_ids = list(file_ids)
        self.conn.execute(
            "DELETE FROM partial_candidates WHERE session_id = ? AND partial_hash = ?",
            (session_id, partial_hash),
        )
        if not file_ids:
            self.conn.commit()
            return 0
        self.conn.executemany(
            "INSERT INTO partial_candidates (session_id, partial_hash, file_id) VALUES (?, ?, ?)",
            [(session_id, partial_hash, file_id) for file_id in file_ids],
        )
        self.conn.commit()
        return len(file_ids)

    def iter_groups(self, session_id: str) -> Dict[str, List[int]]:
        rows = self.conn.execute(
            """
            SELECT partial_hash, file_id
            FROM partial_candidates
            WHERE session_id = ?
            ORDER BY partial_hash ASC, file_id ASC
            """,
            (session_id,),
        ).fetchall()
        groups: Dict[str, List[int]] = {}
        for row in rows:
            groups.setdefault(row["partial_hash"], []).append(row["file_id"])
        return groups


class FullHashRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def upsert(self, session_id: str, file_id: int, algorithm: str, full_hash: str) -> None:
        self.conn.execute(
            """
            INSERT OR REPLACE INTO full_hashes (
                session_id, file_id, algorithm, full_hash, computed_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, file_id, algorithm, full_hash, datetime.now().isoformat()),
        )
        self.conn.commit()


class DuplicateGroupRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def clear_session(self, session_id: str) -> None:
        group_rows = self.conn.execute(
            "SELECT group_id FROM duplicate_groups WHERE session_id = ?",
            (session_id,),
        ).fetchall()
        group_ids = [row["group_id"] for row in group_rows]
        if group_ids:
            self.conn.executemany(
                "DELETE FROM duplicate_group_members WHERE group_id = ?",
                [(group_id,) for group_id in group_ids],
            )
        self.conn.execute(
            "DELETE FROM duplicate_groups WHERE session_id = ?",
            (session_id,),
        )
        self.conn.commit()

    def create_group(
        self,
        session_id: str,
        full_hash: str,
        keeper_file_id: Optional[int],
        total_files: int,
        reclaimable_bytes: int,
        members: Iterable[tuple[int, str]],
    ) -> int:
        cursor = self.conn.execute(
            """
            INSERT INTO duplicate_groups (
                session_id, full_hash, keeper_file_id, total_files, reclaimable_bytes
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, full_hash, keeper_file_id, total_files, reclaimable_bytes),
        )
        group_id = int(cursor.lastrowid)
        self.conn.executemany(
            """
            INSERT INTO duplicate_group_members (group_id, file_id, role)
            VALUES (?, ?, ?)
            """,
            [(group_id, file_id, role) for file_id, role in members],
        )
        self.conn.commit()
        return group_id


class HashCacheRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def upsert(
        self,
        path: str,
        size_bytes: int,
        mtime_ns: int,
        algorithm: str,
        strategy_version: str,
        hash_kind: str,
        hash_value: str,
    ) -> None:
        self.conn.execute(
            """
            INSERT OR REPLACE INTO hash_cache_v2 (
                path, size_bytes, mtime_ns, algorithm, strategy_version,
                hash_kind, hash_value, computed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                path,
                size_bytes,
                mtime_ns,
                algorithm,
                strategy_version,
                hash_kind,
                hash_value,
                datetime.now().isoformat(),
            ),
        )
        self.conn.commit()

    def get(
        self,
        path: str,
        size_bytes: int,
        mtime_ns: int,
        algorithm: str,
        strategy_version: str,
        hash_kind: str,
    ) -> Optional[Dict[str, object]]:
        row = self.conn.execute(
            """
            SELECT * FROM hash_cache_v2
            WHERE path = ? AND size_bytes = ? AND mtime_ns = ?
              AND algorithm = ? AND strategy_version = ? AND hash_kind = ?
            """,
            (path, size_bytes, mtime_ns, algorithm, strategy_version, hash_kind),
        ).fetchone()
        return dict(row) if row else None


class DeletionPlanRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(self, plan_id: str, session_id: str, status: str, policy: Dict[str, object]) -> None:
        self.conn.execute(
            """
            INSERT OR REPLACE INTO deletion_plans (
                plan_id, session_id, created_at, status, policy_json
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (plan_id, session_id, datetime.now().isoformat(), status, json.dumps(policy)),
        )
        self.conn.commit()

    def add_item(
        self,
        plan_id: str,
        file_id: int,
        expected_size_bytes: int,
        expected_mtime_ns: int,
        expected_full_hash: str,
        action: str,
        status: str = "pending",
        failure_reason: Optional[str] = None,
    ) -> None:
        self.conn.execute(
            """
            INSERT OR REPLACE INTO deletion_plan_items (
                plan_id, file_id, expected_size_bytes, expected_mtime_ns,
                expected_full_hash, action, status, failure_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                plan_id,
                file_id,
                expected_size_bytes,
                expected_mtime_ns,
                expected_full_hash,
                action,
                status,
                failure_reason,
            ),
        )
        self.conn.commit()

    def update_item_status(self, plan_id: str, file_id: int, status: str, failure_reason: Optional[str] = None) -> None:
        self.conn.execute(
            """
            UPDATE deletion_plan_items
            SET status = ?, failure_reason = ?
            WHERE plan_id = ? AND file_id = ?
            """,
            (status, failure_reason, plan_id, file_id),
        )
        self.conn.commit()


class DeletionAuditRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def log(
        self,
        plan_id: str,
        action: str,
        outcome: str,
        detail: Dict[str, object],
        file_id: Optional[int] = None,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO deletion_audit (
                plan_id, file_id, action, outcome, executed_at, detail_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                plan_id,
                file_id,
                action,
                outcome,
                datetime.now().isoformat(),
                json.dumps(detail),
            ),
        )
        self.conn.commit()
