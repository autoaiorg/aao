-- Durable, typed intents for Self Development mTLS issuance.
-- Contains public identifiers/digests only; never private keys or bearer tokens.
BEGIN;
CREATE TABLE IF NOT EXISTS selfdev_cycle_mtls_intents (
    intent_id uuid PRIMARY KEY,
    project_id uuid NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
    cycle_id text NOT NULL CHECK (cycle_id ~ '^[0-9a-f]{32}$'),
    principal_id text NOT NULL REFERENCES principal_credentials(principal_id) ON DELETE RESTRICT,
    kind text NOT NULL CHECK (kind IN ('AGENT','AUDITOR')),
    not_before timestamptz NOT NULL,
    not_after timestamptz NOT NULL,
    state text NOT NULL DEFAULT 'PENDING' CHECK (state IN ('PENDING','COMPLETED','REVOKED','EXPIRED')),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    completed_at timestamptz,
    revoked_at timestamptz,
    UNIQUE (project_id, cycle_id, kind),
    CHECK (not_after > not_before AND not_after <= not_before + interval '2 hours'),
    CHECK (state <> 'COMPLETED' OR completed_at IS NOT NULL),
    CHECK (completed_at IS NULL OR state IN ('COMPLETED','REVOKED')),
    CHECK ((state = 'REVOKED') = (revoked_at IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS ix_selfdev_cycle_mtls_intents_pending
    ON selfdev_cycle_mtls_intents(not_after) WHERE state='PENDING';
ALTER TABLE workload_identity_bindings
    ADD COLUMN IF NOT EXISTS intent_id uuid REFERENCES selfdev_cycle_mtls_intents(intent_id) ON DELETE RESTRICT,
    ADD COLUMN IF NOT EXISTS csr_sha256 text CHECK (csr_sha256 IS NULL OR csr_sha256 ~ '^[0-9a-f]{64}$');
CREATE UNIQUE INDEX IF NOT EXISTS uq_workload_identity_binding_intent
    ON workload_identity_bindings(intent_id) WHERE intent_id IS NOT NULL;
REVOKE ALL ON TABLE selfdev_cycle_mtls_intents FROM PUBLIC;
REVOKE ALL ON TABLE workload_identity_bindings FROM PUBLIC;
INSERT INTO schema_migrations(version)
VALUES ('045_selfdev_cycle_mtls_intents') ON CONFLICT DO NOTHING;
COMMIT;
