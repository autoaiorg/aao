-- Retire a revoked Self Development cycle implementer's host binding.
-- aao_runtime deliberately has no UPDATE on host_worker_bindings (UPDATE of
-- status could unfence a host). This owner-run function performs only the
-- ACTIVE -> FENCED transition after proving the supplied worker/project pair
-- is an issued cycle implementer: exact grant set, matching two-hour maximum
-- credential/grant expiry, Self Development project, and disabled AGENT.
-- It never changes fence_epoch.
BEGIN;
CREATE OR REPLACE FUNCTION retire_selfdev_cycle_host_binding(
    p_worker_id text,
    p_project_id uuid
)
RETURNS integer
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
    WITH retired AS (
        UPDATE public.host_worker_bindings b
        SET status = 'FENCED', fenced_at = clock_timestamp()
        WHERE b.worker_id = p_worker_id
          AND b.status = 'ACTIVE'
          AND p_worker_id ~ '^aao-selfdev-impl-[0-9a-f]{32}$'
          AND EXISTS (
              SELECT 1
              FROM public.principal_credentials c
              JOIN public.projects p ON p.id = p_project_id
              WHERE c.principal_id = p_worker_id
                AND c.kind = 'AGENT'
                AND NOT c.enabled
                AND p.name = 'AAO — Self Development'
                AND c.expires_at IS NOT NULL
                AND c.expires_at >= c.created_at
                AND c.expires_at <= c.created_at + interval '2 hours'
                AND (
                    SELECT count(*)
                    FROM public.project_grants g
                    WHERE g.principal_id = p_worker_id
                      AND g.project_id = p_project_id
                      AND g.capability = ANY(ARRAY[
                          'project.read', 'work.create', 'work.admit',
                          'work.progress', 'execution.claim', 'code.propose',
                          'evidence.submit'
                      ])
                      AND g.expires_at = c.expires_at
                ) = 7
                AND NOT EXISTS (
                    SELECT 1
                    FROM public.project_grants g
                    WHERE g.principal_id = p_worker_id
                      AND (g.project_id <> p_project_id OR NOT (g.capability = ANY(ARRAY[
                          'project.read', 'work.create', 'work.admit',
                          'work.progress', 'execution.claim', 'code.propose',
                          'evidence.submit'
                      ])))
                )
          )
        RETURNING 1
    )
    SELECT count(*)::integer FROM retired
$$;
-- No implicit PUBLIC execution; aao_runtime receives EXECUTE explicitly in
-- scripts/bootstrap/apply_api_grants.sql.
REVOKE ALL ON FUNCTION retire_selfdev_cycle_host_binding(text, uuid) FROM PUBLIC;
INSERT INTO schema_migrations(version)
VALUES ('041_selfdev_cycle_host_binding_retirement') ON CONFLICT DO NOTHING;
COMMIT;
