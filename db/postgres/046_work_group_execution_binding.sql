-- Bind autonomous execution effects to their durable execution journal.
BEGIN;

ALTER TABLE work_groups
  ADD COLUMN IF NOT EXISTS execution_id uuid
  REFERENCES organization_executions(id) ON DELETE RESTRICT;

CREATE UNIQUE INDEX IF NOT EXISTS uq_work_groups_execution_id
  ON work_groups(execution_id) WHERE execution_id IS NOT NULL;

INSERT INTO schema_migrations(version)
VALUES ('046_work_group_execution_binding') ON CONFLICT DO NOTHING;
COMMIT;
