-- Durable, idempotent execution journal for approved organizational plans.
BEGIN;

ALTER TABLE organization_proposals
  ADD COLUMN IF NOT EXISTS operation text,
  ADD COLUMN IF NOT EXISTS project_id uuid REFERENCES projects(id) ON DELETE RESTRICT,
  ADD COLUMN IF NOT EXISTS operation_parameters_json jsonb NOT NULL DEFAULT '{}'::jsonb
    CHECK (jsonb_typeof(operation_parameters_json) = 'object'),
  ADD COLUMN IF NOT EXISTS budget_ceiling_usd numeric(14,2) NOT NULL DEFAULT 0
    CHECK (budget_ceiling_usd >= 0),
  ADD COLUMN IF NOT EXISTS approved_version integer,
  ADD COLUMN IF NOT EXISTS approved_plan_sha256 text,
  ADD COLUMN IF NOT EXISTS approved_by_principal_id text,
  ADD COLUMN IF NOT EXISTS approved_at timestamptz;

UPDATE organization_proposals
SET operation = authority_classification_json->>'operation'
WHERE operation IS NULL AND jsonb_typeof(authority_classification_json) = 'object';

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'organization_proposals_operation_check'
      AND conrelid = 'organization_proposals'::regclass
  ) THEN
    ALTER TABLE organization_proposals ADD CONSTRAINT organization_proposals_operation_check
      CHECK (operation IS NULL OR operation IN (
        'organization.squad.create_temporary','organization.squad.dissolve',
        'organization.slot.assign','organization.unit.create_permanent',
        'organization.unit.merge','organization.unit.split'
      ));
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS organization_executions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  proposal_id text NOT NULL REFERENCES organization_proposals(id) ON DELETE RESTRICT,
  proposal_version integer NOT NULL CHECK (proposal_version >= 1),
  project_id uuid NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
  plan_sha256 text NOT NULL CHECK (plan_sha256 ~ '^[0-9a-f]{64}$'),
  plan_json jsonb NOT NULL CHECK (jsonb_typeof(plan_json) = 'object'),
  idempotency_key text NOT NULL CHECK (length(idempotency_key) BETWEEN 1 AND 200),
  state text NOT NULL CHECK (state IN (
    'PLANNED','AWAITING_AUTHORIZATION','AUTHORIZED','EXECUTING','EXECUTED',
    'FAILED','RECONCILIATION_REQUIRED','COMPENSATING','COMPENSATED','CANCELLED')),
  actor_principal_id text NOT NULL,
  authority_capability text NOT NULL,
  result_json jsonb,
  error_code text,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (proposal_id, proposal_version),
  UNIQUE (project_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS organization_execution_events (
  id bigserial PRIMARY KEY,
  execution_id uuid NOT NULL REFERENCES organization_executions(id) ON DELETE RESTRICT,
  from_state text CHECK (from_state IS NULL OR from_state IN (
    'PLANNED','AWAITING_AUTHORIZATION','AUTHORIZED','EXECUTING','EXECUTED',
    'FAILED','RECONCILIATION_REQUIRED','COMPENSATING','COMPENSATED','CANCELLED')),
  to_state text NOT NULL CHECK (to_state IN (
    'PLANNED','AWAITING_AUTHORIZATION','AUTHORIZED','EXECUTING','EXECUTED',
    'FAILED','RECONCILIATION_REQUIRED','COMPENSATING','COMPENSATED','CANCELLED')),
  actor_principal_id text NOT NULL,
  event_type text NOT NULL,
  details_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  occurred_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX IF NOT EXISTS ix_organization_executions_state
  ON organization_executions(state, updated_at);
REVOKE ALL ON TABLE organization_executions FROM PUBLIC;
REVOKE ALL ON TABLE organization_execution_events FROM PUBLIC;
INSERT INTO schema_migrations(version) VALUES ('045_organization_execution') ON CONFLICT DO NOTHING;
COMMIT;
