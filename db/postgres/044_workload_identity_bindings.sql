-- Bind verified mTLS client-certificate fingerprints to existing AAO principals.
-- This table stores public certificate fingerprints only, never private keys.
BEGIN;
CREATE TABLE IF NOT EXISTS workload_identity_bindings (
    certificate_sha256 text PRIMARY KEY
        CHECK (certificate_sha256 ~ '^[0-9a-f]{64}$'),
    principal_id text NOT NULL REFERENCES principal_credentials(principal_id)
        ON DELETE RESTRICT,
    enabled boolean NOT NULL DEFAULT true,
    issued_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz,
    CHECK ((enabled AND revoked_at IS NULL) OR NOT enabled)
);
CREATE INDEX IF NOT EXISTS ix_workload_identity_bindings_principal
    ON workload_identity_bindings(principal_id);
REVOKE ALL ON TABLE workload_identity_bindings FROM PUBLIC;
INSERT INTO schema_migrations(version)
VALUES ('044_workload_identity_bindings') ON CONFLICT DO NOTHING;
COMMIT;
