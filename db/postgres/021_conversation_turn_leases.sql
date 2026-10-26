-- Fenced leases let the CEO retry a turn left pending by a crashed API process.
BEGIN;
ALTER TABLE project_conversation_turns
    ADD COLUMN IF NOT EXISTS lease_owner uuid,
    ADD COLUMN IF NOT EXISTS lease_expires_at timestamptz;
CREATE INDEX IF NOT EXISTS ix_conversation_turns_expired_lease
    ON project_conversation_turns(lease_expires_at)
    WHERE state='PENDING';
INSERT INTO schema_migrations(version) VALUES ('021_conversation_turn_leases')
ON CONFLICT DO NOTHING;
COMMIT;
