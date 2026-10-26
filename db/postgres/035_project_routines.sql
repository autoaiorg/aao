-- Durable CEO-authorized schedules. Occurrences point to canonical work, never to a second queue.
BEGIN;
CREATE TABLE IF NOT EXISTS project_routines (
  id UUID PRIMARY KEY,
  project_id UUID NOT NULL REFERENCES projects(id),
  idempotency_key UUID NOT NULL,
  request_sha256 TEXT NOT NULL CHECK (request_sha256 ~ '^[0-9a-f]{64}$'),
  task_template JSONB NOT NULL CHECK (jsonb_typeof(task_template) = 'object'),
  interval_seconds INTEGER NOT NULL CHECK (interval_seconds BETWEEN 60 AND 31536000),
  next_run_at TIMESTAMPTZ NOT NULL,
  enabled BOOLEAN NOT NULL DEFAULT TRUE,
  authorized_by TEXT NOT NULL CHECK (authorized_by = 'ceo'),
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (project_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS project_routines_due ON project_routines(project_id,next_run_at) WHERE enabled;
CREATE TABLE IF NOT EXISTS routine_occurrences (
  routine_id UUID NOT NULL REFERENCES project_routines(id),
  scheduled_for TIMESTAMPTZ NOT NULL,
  work_id UUID NOT NULL UNIQUE REFERENCES work_items(id),
  materialized_by TEXT NOT NULL,
  materialized_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (routine_id, scheduled_for)
);
REVOKE ALL ON project_routines,routine_occurrences FROM PUBLIC;
INSERT INTO schema_migrations(version) VALUES ('035_project_routines') ON CONFLICT DO NOTHING;
COMMIT;
