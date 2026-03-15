CREATE TABLE IF NOT EXISTS hash_cache_v2 (
    path TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    mtime_ns INTEGER NOT NULL,
    algorithm TEXT NOT NULL,
    strategy_version TEXT NOT NULL,
    hash_kind TEXT NOT NULL,
    hash_value TEXT NOT NULL,
    computed_at TEXT NOT NULL,
    PRIMARY KEY (path, size_bytes, mtime_ns, algorithm, strategy_version, hash_kind)
);

CREATE INDEX IF NOT EXISTS idx_hash_cache_v2_path
ON hash_cache_v2(path);

CREATE TABLE IF NOT EXISTS deletion_plans (
    plan_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL,
    policy_json TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES scan_sessions(session_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS deletion_plan_items (
    plan_id TEXT NOT NULL,
    file_id INTEGER NOT NULL,
    expected_size_bytes INTEGER NOT NULL,
    expected_mtime_ns INTEGER NOT NULL,
    expected_full_hash TEXT NOT NULL,
    action TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    failure_reason TEXT,
    PRIMARY KEY (plan_id, file_id),
    FOREIGN KEY (plan_id) REFERENCES deletion_plans(plan_id) ON DELETE CASCADE,
    FOREIGN KEY (file_id) REFERENCES inventory_files(file_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS deletion_audit (
    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id TEXT NOT NULL,
    file_id INTEGER,
    action TEXT NOT NULL,
    outcome TEXT NOT NULL,
    executed_at TEXT NOT NULL,
    detail_json TEXT,
    FOREIGN KEY (plan_id) REFERENCES deletion_plans(plan_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_deletion_audit_plan
ON deletion_audit(plan_id);
