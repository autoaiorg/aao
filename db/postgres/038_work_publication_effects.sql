-- Durable state for GitHub effects, whose remote APIs cannot join a PostgreSQL transaction.
BEGIN;
CREATE TABLE IF NOT EXISTS work_publication_effects (
    id uuid PRIMARY KEY,
    work_id uuid NOT NULL REFERENCES work_items(id),
    candidate_sha text NOT NULL CHECK(candidate_sha ~ '^[0-9a-f]{40}$'),
    operation text NOT NULL CHECK(operation IN ('PUSH_CANDIDATE','OPEN_PULL_REQUEST')),
    effect_key text NOT NULL UNIQUE CHECK(length(effect_key) BETWEEN 1 AND 200),
    status text NOT NULL CHECK(status IN ('PENDING','IN_PROGRESS','UNCERTAIN','COMPLETED')),
    attempt_id uuid,
    attempts integer NOT NULL DEFAULT 0 CHECK(attempts >= 0),
    lease_expires_at timestamptz,
    result jsonb NOT NULL DEFAULT '{}'::jsonb CHECK(jsonb_typeof(result)='object'),
    error_class text,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE(work_id,candidate_sha,operation),
    CHECK((status='IN_PROGRESS') = (attempt_id IS NOT NULL AND lease_expires_at IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS ix_work_publication_effects_recovery
    ON work_publication_effects(status,lease_expires_at) WHERE status IN ('IN_PROGRESS','UNCERTAIN');
INSERT INTO schema_migrations(version)
VALUES ('038_work_publication_effects') ON CONFLICT DO NOTHING;
COMMIT;
