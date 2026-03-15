CREATE TABLE IF NOT EXISTS discovery_dir_mtimes (
    session_id TEXT NOT NULL,
    dir_path TEXT NOT NULL,
    dir_mtime_ns INTEGER NOT NULL,
    PRIMARY KEY (session_id, dir_path),
    FOREIGN KEY (session_id) REFERENCES scan_sessions(session_id) ON DELETE CASCADE
);
