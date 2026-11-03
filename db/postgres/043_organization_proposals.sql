-- Persistent storage for Autonomous Organization Manager proposals and lifecycle tracking.
BEGIN;

CREATE TABLE IF NOT EXISTS organization_proposals (
  id TEXT PRIMARY KEY CHECK (id ~ '^[a-zA-Z0-9_-]{1,128}$'),
  version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
  title TEXT NOT NULL CHECK (length(title) BETWEEN 1 AND 250),
  scope_description TEXT NOT NULL CHECK (length(scope_description) BETWEEN 1 AND 5000),
  target_unit_id TEXT CHECK (target_unit_id IS NULL OR target_unit_id ~ '^[a-zA-Z0-9_-]{1,128}$'),
  target_unit_code TEXT CHECK (target_unit_code IS NULL OR length(target_unit_code) BETWEEN 1 AND 64),
  target_unit_name TEXT CHECK (target_unit_name IS NULL OR length(target_unit_name) BETWEEN 1 AND 200),
  parent_unit_id TEXT CHECK (parent_unit_id IS NULL OR parent_unit_id ~ '^[a-zA-Z0-9_-]{1,128}$'),
  lead_principal_id TEXT CHECK (lead_principal_id IS NULL OR length(lead_principal_id) BETWEEN 1 AND 128),
  proposed_role_title TEXT CHECK (proposed_role_title IS NULL OR length(proposed_role_title) BETWEEN 1 AND 200),
  impact TEXT NOT NULL CHECK (impact IN ('CONSTITUTIONAL', 'CRITICAL', 'ORDINARY_STRUCTURE', 'OPERATIONAL_TEAM', 'SLOT_ASSIGNMENT', 'UNKNOWN')),
  state TEXT NOT NULL CHECK (state IN ('DRAFT', 'ANALYZED', 'EVALUATED', 'REQUIRES_CEO_APPROVAL', 'AUTONOMOUS_APPROVED', 'REJECTED', 'EXECUTED', 'DISSOLVED')),
  demand_summary TEXT NOT NULL CHECK (length(demand_summary) BETWEEN 1 AND 5000),
  criteria_json JSONB NOT NULL,
  alternatives_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  chosen_alternative TEXT CHECK (chosen_alternative IS NULL OR chosen_alternative IN ('REUSE_EXISTING_CAPACITY', 'REASSIGN_AVAILABLE_AGENTS', 'CREATE_TEMPORARY_SQUAD', 'EXPAND_EXISTING_UNIT', 'CREATE_PERMANENT_UNIT')),
  authority_classification_json JSONB NOT NULL,
  author_principal_id TEXT NOT NULL CHECK (length(author_principal_id) BETWEEN 1 AND 128),
  delegation_authority_id TEXT,
  rejection_reason TEXT,
  stability_review_due_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX IF NOT EXISTS ix_organization_proposals_state ON organization_proposals(state);
CREATE INDEX IF NOT EXISTS ix_organization_proposals_created ON organization_proposals(created_at DESC);

INSERT INTO schema_migrations(version) VALUES ('043_organization_proposals') ON CONFLICT DO NOTHING;
COMMIT;
