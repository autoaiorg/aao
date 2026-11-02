-- Two-phase AGENT self-rotation: a pending digest with a short TTL that only the
-- confirm endpoint accepts. Normal authentication still matches token_digest only.
BEGIN;
ALTER TABLE principal_credentials
    ADD COLUMN IF NOT EXISTS pending_token_digest text,
    ADD COLUMN IF NOT EXISTS pending_expires_at timestamptz;
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.principal_credentials'::regclass
          AND conname = 'principal_credentials_pending_pair'
    ) THEN
        ALTER TABLE principal_credentials
            ADD CONSTRAINT principal_credentials_pending_pair CHECK (
                (pending_token_digest IS NULL) = (pending_expires_at IS NULL)
                AND pending_token_digest IS DISTINCT FROM token_digest
            );
    END IF;
END $$;
CREATE UNIQUE INDEX IF NOT EXISTS ux_principal_credentials_pending_digest
    ON principal_credentials(pending_token_digest) WHERE pending_token_digest IS NOT NULL;
INSERT INTO schema_migrations(version)
VALUES ('039_principal_pending_rotation') ON CONFLICT DO NOTHING;
COMMIT;
