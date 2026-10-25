-- Allow a task to be re-run after a failed execution: keep at most one
-- active (QUEUED/RUNNING/UNCERTAIN) execution per work item instead of one
-- execution per work item forever.
BEGIN;
ALTER TABLE execution_queue DROP CONSTRAINT IF EXISTS execution_queue_work_id_key;
CREATE UNIQUE INDEX IF NOT EXISTS ux_execution_queue_active_work
  ON execution_queue(work_id) WHERE status IN ('QUEUED','RUNNING','UNCERTAIN');
CREATE INDEX IF NOT EXISTS ix_execution_queue_work_created
  ON execution_queue(work_id, created_at);
INSERT INTO schema_migrations(version) VALUES ('014_execution_retry') ON CONFLICT DO NOTHING;
COMMIT;
