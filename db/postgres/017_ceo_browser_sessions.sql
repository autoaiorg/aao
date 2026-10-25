-- Opaque, revocable sessions issued only by the development/test CEO bearer exchange.
BEGIN;
CREATE TABLE IF NOT EXISTS ceo_browser_sessions (
    id uuid PRIMARY KEY,
    session_digest text NOT NULL UNIQUE CHECK (session_digest ~ '^[0-9a-f]{64}$'),
    csrf_digest text NOT NULL CHECK (csrf_digest ~ '^[0-9a-f]{64}$'),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz,
    CHECK (expires_at > created_at)
);
CREATE INDEX IF NOT EXISTS ix_ceo_browser_sessions_live_expiry
    ON ceo_browser_sessions(expires_at) WHERE revoked_at IS NULL;
INSERT INTO schema_migrations(version) VALUES ('017_ceo_browser_sessions')
ON CONFLICT DO NOTHING;
COMMIT;
