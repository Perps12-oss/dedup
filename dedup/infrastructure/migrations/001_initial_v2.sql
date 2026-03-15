CREATE TABLE IF NOT EXISTS scan_sessions (
    session_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    status TEXT NOT NULL,
    current_phase TEXT NOT NULL,
    config_json TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    root_fingerprint TEXT,
    started_at TEXT,
    completed_at TEXT,
    failure_reason TEXT,
    metrics_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_scan_sessions_status
ON scan_sessions(status);

CREATE TABLE IF NOT EXISTS scan_roots (
    session_id TEXT NOT NULL,
    root_path TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    PRIMARY KEY (session_id, root_path),
    FOREIGN KEY (session_id) REFERENCES scan_sessions(session_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS phase_checkpoints (
    session_id TEXT NOT NULL,
    phase_name TEXT NOT NULL,
    chunk_cursor TEXT,
    completed_units INTEGER NOT NULL DEFAULT 0,
    total_units INTEGER,
    status TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    metadata_json TEXT,
    PRIMARY KEY (session_id, phase_name),
    FOREIGN KEY (session_id) REFERENCES scan_sessions(session_id) ON DELETE CASCADE
);
