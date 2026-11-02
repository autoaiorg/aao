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
GRANT UPDATE ON TABLE execution_queue, project_conversations,
  project_conversation_turns, host_worker_bindings TO aao_recovery;
COMMIT;
