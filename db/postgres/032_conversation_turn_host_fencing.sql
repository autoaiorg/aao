-- Bind provider-backed conversation leases to the host that owns them so
-- targeted host fencing cannot revive a stale heartbeat or revoke other hosts.
BEGIN;
ALTER TABLE project_conversation_turns
    ADD COLUMN IF NOT EXISTS lease_host_id text;
ALTER TABLE project_conversation_turns
    ADD COLUMN IF NOT EXISTS lease_fence_epoch bigint;
CREATE INDEX IF NOT EXISTS ix_conversation_turns_host_active_lease
    ON project_conversation_turns(lease_host_id, lease_expires_at)
    WHERE state='PENDING';
-- Existing leases predate host attribution. The bootstrap upgrade drains the
-- API/recovery services before migration 032; make those un-attributable
-- leases immediately reclaimable rather than allowing them to outlive cutover.
UPDATE project_conversation_turns
SET lease_owner = NULL,
    lease_expires_at = clock_timestamp() - INTERVAL '1 second',
    lease_fence_epoch = NULL,
    updated_at = clock_timestamp()
WHERE state = 'PENDING' AND lease_host_id IS NULL;
INSERT INTO schema_migrations(version) VALUES ('032_conversation_turn_host_fencing')
ON CONFLICT DO NOTHING;
COMMIT;
