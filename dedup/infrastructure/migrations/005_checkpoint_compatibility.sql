-- Phase checkpoint compatibility fields for authoritative resume.
-- Existing rows keep using metadata_json; new checkpoints can set these columns.

ALTER TABLE phase_checkpoints ADD COLUMN schema_version INTEGER;
ALTER TABLE phase_checkpoints ADD COLUMN phase_version TEXT;
ALTER TABLE phase_checkpoints ADD COLUMN config_hash TEXT;
ALTER TABLE phase_checkpoints ADD COLUMN input_artifact_fingerprint TEXT;
ALTER TABLE phase_checkpoints ADD COLUMN output_artifact_fingerprint TEXT;
ALTER TABLE phase_checkpoints ADD COLUMN is_finalized INTEGER NOT NULL DEFAULT 0;
ALTER TABLE phase_checkpoints ADD COLUMN resume_policy TEXT DEFAULT 'safe';
