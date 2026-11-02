-- Least-privilege direct SQL grants for the opt-in conversation recovery worker.
-- Run only after migrations, as the schema owner. The API uses aao_runtime.
BEGIN;
REVOKE CREATE, TEMPORARY ON DATABASE aao_prod FROM PUBLIC;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM aao_recovery, PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM aao_recovery, PUBLIC;
GRANT CONNECT ON DATABASE aao_prod TO aao_recovery;
GRANT USAGE ON SCHEMA public TO aao_recovery;

GRANT SELECT ON TABLE schema_migrations, projects, work_items, work_groups,
  work_item_assignments, execution_queue, reviews, patch_proposal_validations,
  patch_proposals, events, project_conversations, project_conversation_messages,
  project_conversation_turns, host_worker_bindings
TO aao_recovery;
GRANT INSERT ON TABLE events, project_conversation_messages TO aao_recovery;
-- The recovery worker only reads execution_queue. Never let its credential
-- rewrite execution results or worker fencing state.
GRANT UPDATE (updated_at) ON TABLE project_conversations TO aao_recovery;
GRANT UPDATE (state, assistant_message_id, error_code, lease_owner, lease_host_id,
  lease_fence_epoch, lease_expires_at, updated_at)
ON TABLE project_conversation_turns TO aao_recovery;

-- PostgreSQL requires UPDATE on at least one column for SELECT ... FOR SHARE.
-- Grant only a no-op-able column and reject any actual change by aao_recovery.
GRANT UPDATE (created_at) ON TABLE host_worker_bindings TO aao_recovery;
CREATE OR REPLACE FUNCTION reject_recovery_host_binding_mutation()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $$
BEGIN
  IF current_user = 'aao_recovery' AND NEW.created_at IS DISTINCT FROM OLD.created_at THEN
    RAISE EXCEPTION 'aao_recovery cannot modify host_worker_bindings';
  END IF;
  RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS host_worker_bindings_recovery_immutable ON host_worker_bindings;
CREATE TRIGGER host_worker_bindings_recovery_immutable
BEFORE UPDATE ON host_worker_bindings
FOR EACH ROW EXECUTE FUNCTION reject_recovery_host_binding_mutation();
COMMIT;
