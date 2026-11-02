-- Optional expiry for narrowly scoped, short-lived role credentials.
-- NULL preserves the legacy no-expiry behavior for every existing credential.
BEGIN;
ALTER TABLE principal_credentials
    ADD COLUMN IF NOT EXISTS expires_at timestamptz;
INSERT INTO schema_migrations(version)
VALUES ('040_principal_credential_expiry') ON CONFLICT DO NOTHING;
COMMIT;
