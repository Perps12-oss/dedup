"""Helpers for applying versioned SQLite migrations."""

from __future__ import annotations

import sqlite3
from pathlib import Path


def get_schema_version(conn: sqlite3.Connection) -> int:
    """Return the current durable schema version."""
    try:
        row = conn.execute(
            "SELECT value FROM schema_meta WHERE key = 'schema_version'"
        ).fetchone()
    except sqlite3.Error:
        return 0

    if not row:
        return 0

    try:
        return int(row[0])
    except (TypeError, ValueError):
        return 0


def set_schema_version(conn: sqlite3.Connection, version: int) -> None:
    """Persist the durable schema version."""
    conn.execute(
        """
        INSERT INTO schema_meta (key, value)
        VALUES ('schema_version', ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (str(version),),
    )


def run_migrations(conn: sqlite3.Connection, migrations_dir: Path) -> int:
    """Apply all SQL migrations in lexical order."""
    migrations = sorted(Path(migrations_dir).glob("*.sql"))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )

    current_version = get_schema_version(conn)
    for migration_path in migrations:
        version = int(migration_path.stem.split("_", 1)[0])
        if version <= current_version:
            continue

        sql = migration_path.read_text(encoding="utf-8")
        conn.executescript(sql)
        set_schema_version(conn, version)

    conn.commit()
    return get_schema_version(conn)
