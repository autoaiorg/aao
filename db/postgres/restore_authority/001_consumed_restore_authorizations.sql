-- Apply only to a dedicated restore-authority PostgreSQL database, never the
-- database being restored. Run as the authority database owner.
BEGIN;
CREATE SCHEMA IF NOT EXISTS restore_authority;
CREATE TABLE IF NOT EXISTS restore_authority.consumed_authorizations (
    nonce text PRIMARY KEY CHECK (nonce ~ '^[A-Za-z0-9_-]{1,200}$'),
    action text NOT NULL CHECK (action = 'database.destructive_restore'),
    authority_id text NOT NULL CHECK (length(authority_id) > 0),
    backup_sha256 text NOT NULL CHECK (backup_sha256 ~ '^[0-9a-f]{64}$'),
    target_database text NOT NULL CHECK (length(target_database) > 0),
    consumed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    metadata jsonb NOT NULL
);
REVOKE ALL ON SCHEMA restore_authority FROM PUBLIC;
REVOKE ALL ON TABLE restore_authority.consumed_authorizations FROM PUBLIC;
COMMIT;
