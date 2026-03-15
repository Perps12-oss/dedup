CREATE TABLE IF NOT EXISTS full_hashes (
    session_id TEXT NOT NULL,
    file_id INTEGER NOT NULL,
    algorithm TEXT NOT NULL,
    full_hash TEXT NOT NULL,
    computed_at TEXT NOT NULL,
    PRIMARY KEY (session_id, file_id, algorithm),
    FOREIGN KEY (session_id) REFERENCES scan_sessions(session_id) ON DELETE CASCADE,
    FOREIGN KEY (file_id) REFERENCES inventory_files(file_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_full_hash_groups
ON full_hashes(session_id, full_hash);

CREATE TABLE IF NOT EXISTS duplicate_groups (
    session_id TEXT NOT NULL,
    group_id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_hash TEXT NOT NULL,
    keeper_file_id INTEGER,
    total_files INTEGER NOT NULL,
    reclaimable_bytes INTEGER NOT NULL,
    FOREIGN KEY (session_id) REFERENCES scan_sessions(session_id) ON DELETE CASCADE,
    FOREIGN KEY (keeper_file_id) REFERENCES inventory_files(file_id)
);

CREATE INDEX IF NOT EXISTS idx_duplicate_groups_session
ON duplicate_groups(session_id);

CREATE TABLE IF NOT EXISTS duplicate_group_members (
    group_id INTEGER NOT NULL,
    file_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    PRIMARY KEY (group_id, file_id),
    FOREIGN KEY (group_id) REFERENCES duplicate_groups(group_id) ON DELETE CASCADE,
    FOREIGN KEY (file_id) REFERENCES inventory_files(file_id) ON DELETE CASCADE
);
