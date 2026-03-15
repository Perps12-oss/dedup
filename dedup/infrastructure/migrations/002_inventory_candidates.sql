CREATE TABLE IF NOT EXISTS inventory_files (
    session_id TEXT NOT NULL,
    file_id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    mtime_ns INTEGER NOT NULL,
    inode TEXT,
    device TEXT,
    extension TEXT,
    media_kind TEXT,
    discovery_status TEXT NOT NULL DEFAULT 'discovered',
    UNIQUE(session_id, path),
    FOREIGN KEY (session_id) REFERENCES scan_sessions(session_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_inventory_session_size
ON inventory_files(session_id, size_bytes);

CREATE INDEX IF NOT EXISTS idx_inventory_session_status
ON inventory_files(session_id, discovery_status);

CREATE TABLE IF NOT EXISTS size_candidates (
    session_id TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    file_id INTEGER NOT NULL,
    PRIMARY KEY (session_id, size_bytes, file_id),
    FOREIGN KEY (session_id) REFERENCES scan_sessions(session_id) ON DELETE CASCADE,
    FOREIGN KEY (file_id) REFERENCES inventory_files(file_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_size_candidates_lookup
ON size_candidates(session_id, size_bytes);

CREATE TABLE IF NOT EXISTS partial_hashes (
    session_id TEXT NOT NULL,
    file_id INTEGER NOT NULL,
    algorithm TEXT NOT NULL,
    strategy_version TEXT NOT NULL,
    sample_spec_json TEXT NOT NULL,
    partial_hash TEXT NOT NULL,
    computed_at TEXT NOT NULL,
    PRIMARY KEY (session_id, file_id, strategy_version),
    FOREIGN KEY (session_id) REFERENCES scan_sessions(session_id) ON DELETE CASCADE,
    FOREIGN KEY (file_id) REFERENCES inventory_files(file_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_partial_hash_groups
ON partial_hashes(session_id, partial_hash);

CREATE TABLE IF NOT EXISTS partial_candidates (
    session_id TEXT NOT NULL,
    partial_hash TEXT NOT NULL,
    file_id INTEGER NOT NULL,
    PRIMARY KEY (session_id, partial_hash, file_id),
    FOREIGN KEY (session_id) REFERENCES scan_sessions(session_id) ON DELETE CASCADE,
    FOREIGN KEY (file_id) REFERENCES inventory_files(file_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_partial_candidates_lookup
ON partial_candidates(session_id, partial_hash);
