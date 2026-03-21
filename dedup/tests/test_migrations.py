"""
Migration tests: durable schema is created and repository-backed tables exist.
"""

from __future__ import annotations

from dedup.infrastructure.persistence import Persistence


def test_durable_schema_migrations_create_expected_tables(temp_dir):
    persistence = Persistence(db_path=temp_dir / "durable.db")
    try:
        conn = persistence._get_connection()
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        names = {row["name"] for row in rows}
        assert "scan_sessions" in names
        assert "phase_checkpoints" in names
        assert "inventory_files" in names
        assert "partial_hashes" in names
        assert "full_hashes" in names
        assert "deletion_plans" in names
        assert "discovery_dir_mtimes" in names
        assert "deletion_verifications" in names
        assert persistence.schema_version >= 8
    finally:
        persistence.close()
