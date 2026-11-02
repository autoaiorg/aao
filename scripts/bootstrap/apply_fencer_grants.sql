-- Narrow database credential used only by root-run aao-ops fence-host.
-- Run after migrations, as the schema owner.
BEGIN;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM aao_fencer;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM aao_fencer;
GRANT CONNECT ON DATABASE aao_prod TO aao_fencer;
GRANT USAGE ON SCHEMA public TO aao_fencer;

GRANT SELECT (host_id, worker_id, status, fence_epoch),
  UPDATE (status, fence_epoch, fenced_at)
  ON TABLE host_worker_bindings TO aao_fencer;
GRANT SELECT (principal_id, enabled), UPDATE (enabled)
  ON TABLE principal_credentials TO aao_fencer;
GRANT SELECT (worker_id, status, claim_fence_epoch),
  UPDATE (status, result_json, lease_expires_at)
  ON TABLE execution_queue TO aao_fencer;
GRANT SELECT (lease_host_id, state, lease_fence_epoch),
  UPDATE (lease_owner, lease_expires_at, lease_fence_epoch, updated_at)
  ON TABLE project_conversation_turns TO aao_fencer;
GRANT INSERT (id, subject_id, kind, details) ON TABLE events TO aao_fencer;
COMMIT;
