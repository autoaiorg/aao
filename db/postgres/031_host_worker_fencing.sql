-- Make the host fencing registry part of the single versioned schema.
-- Existing ad-hoc registries are retained; duplicate active worker bindings make
-- this migration fail rather than silently choosing one host.
BEGIN;
CREATE TABLE IF NOT EXISTS host_worker_bindings (
    host_id text NOT NULL CHECK (length(host_id) > 0),
    worker_id text NOT NULL CHECK (length(worker_id) > 0),
    status text NOT NULL CHECK (status IN ('ACTIVE', 'FENCED', 'STANDBY')),
    fence_epoch bigint NOT NULL DEFAULT 1 CHECK (fence_epoch > 0),
    fenced_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (host_id, worker_id)
);
ALTER TABLE host_worker_bindings
    ADD COLUMN IF NOT EXISTS fence_epoch bigint NOT NULL DEFAULT 1;
ALTER TABLE host_worker_bindings ALTER COLUMN host_id SET NOT NULL;
ALTER TABLE host_worker_bindings ALTER COLUMN worker_id SET NOT NULL;
ALTER TABLE host_worker_bindings ALTER COLUMN status SET NOT NULL;
ALTER TABLE host_worker_bindings ALTER COLUMN fence_epoch SET NOT NULL;
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.host_worker_bindings'::regclass
          AND conname = 'host_worker_bindings_fence_epoch_positive'
    ) THEN
        ALTER TABLE host_worker_bindings
            ADD CONSTRAINT host_worker_bindings_fence_epoch_positive CHECK (fence_epoch > 0);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.host_worker_bindings'::regclass
          AND conname = 'host_worker_bindings_identity_nonempty'
    ) THEN
        ALTER TABLE host_worker_bindings
            ADD CONSTRAINT host_worker_bindings_identity_nonempty
            CHECK (length(host_id) > 0 AND length(worker_id) > 0);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.host_worker_bindings'::regclass
          AND conname = 'host_worker_bindings_status_valid'
    ) THEN
        ALTER TABLE host_worker_bindings
            ADD CONSTRAINT host_worker_bindings_status_valid
            CHECK (status IN ('ACTIVE', 'FENCED', 'STANDBY'));
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS ix_host_worker_bindings_host
    ON host_worker_bindings(host_id, status);
CREATE INDEX IF NOT EXISTS ix_host_worker_bindings_worker
    ON host_worker_bindings(worker_id, status);
CREATE UNIQUE INDEX IF NOT EXISTS ux_host_worker_bindings_one_active_worker
    ON host_worker_bindings(worker_id) WHERE status = 'ACTIVE';
ALTER TABLE execution_queue
    ADD COLUMN IF NOT EXISTS claim_fence_epoch bigint;
INSERT INTO schema_migrations(version)
    VALUES ('031_host_worker_fencing') ON CONFLICT DO NOTHING;
COMMIT;
