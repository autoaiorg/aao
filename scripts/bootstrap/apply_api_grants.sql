-- Application API SQL permissions. This credential is readable only by aao-api.
-- It is deliberately distinct from the migration owner and recovery role.
-- Run only after migrations, as the schema owner.
BEGIN;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM aao_runtime, PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM aao_runtime, PUBLIC;
GRANT CONNECT ON DATABASE aao_prod TO aao_runtime;
GRANT USAGE ON SCHEMA public TO aao_runtime;

GRANT SELECT ON TABLE schema_migrations TO aao_runtime;
GRANT SELECT, INSERT ON TABLE
  events, execution_journal, patch_proposals, patch_proposal_validations,
  work_item_dependencies, work_group_partial_reports, protocol_instances,
  routine_occurrences
TO aao_runtime;
GRANT SELECT, INSERT ON TABLE
  reviews, evidence_artifacts, capability_versions, work_groups,
  work_group_consolidations
TO aao_runtime;
GRANT UPDATE (created_at) ON TABLE
  reviews, evidence_artifacts, capability_versions, work_groups,
  work_group_consolidations
TO aao_runtime;
GRANT SELECT, INSERT, UPDATE ON TABLE
  mandates, projects, work_items, execution_queue, external_effects,
  principal_credentials, organization_units, organization_profiles,
  project_conversations, project_conversation_messages,
  project_conversation_turns, work_item_assignments,
  capability_feedback_proposals, project_routines, work_publication_effects
TO aao_runtime;
GRANT SELECT, INSERT ON TABLE host_worker_bindings TO aao_runtime;
-- Narrow ACTIVE->FENCED retirement for revoked Self Development cycle implementers (041).
GRANT EXECUTE ON FUNCTION retire_selfdev_cycle_host_binding(text, uuid) TO aao_runtime;
GRANT SELECT, INSERT, DELETE ON TABLE project_grants TO aao_runtime;
GRANT UPDATE (expires_at) ON TABLE project_grants TO aao_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE ceo_browser_sessions TO aao_runtime;
COMMIT;
