CREATE TABLE IF NOT EXISTS deletion_verifications (
    plan_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL,
    summary_json TEXT NOT NULL,
    detail_json TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES scan_sessions(session_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_deletion_verifications_session
ON deletion_verifications(session_id);
