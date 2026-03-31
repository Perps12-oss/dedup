-- Migration 009: Add indexes for inventory_files lookups
-- Fixes O(n) table scan on every phase query; enables O(log n) range/lookup.

CREATE INDEX IF NOT EXISTS idx_inv_session_path ON inventory_files(session_id, path);
CREATE INDEX IF NOT EXISTS idx_inv_session_size ON inventory_files(session_id, size_bytes);
