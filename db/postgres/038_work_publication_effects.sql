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
-- Like 035/036: effect results carry remote PR URLs and failure classes; no implicit
-- PUBLIC access. This grants nothing; a non-owner runtime role needs an explicit, reviewed grant.
REVOKE ALL ON TABLE work_publication_effects FROM PUBLIC;

-- These tables are row-locked by runtime reads. PostgreSQL requires UPDATE
-- privilege for SELECT ... FOR SHARE/UPDATE; the runtime role receives only
-- column-level UPDATE(created_at), so make that otherwise-unused column
-- immutable even if a future grant accidentally widens the role.
CREATE FUNCTION reject_created_at_rewrite() RETURNS trigger AS $$
BEGIN
    IF NEW.created_at IS DISTINCT FROM OLD.created_at THEN
        RAISE EXCEPTION 'created_at is immutable on %', TG_TABLE_NAME
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER capability_versions_created_at_immutable
    BEFORE UPDATE OF created_at ON capability_versions
    FOR EACH ROW EXECUTE FUNCTION reject_created_at_rewrite();
CREATE TRIGGER work_groups_created_at_immutable
    BEFORE UPDATE OF created_at ON work_groups
    FOR EACH ROW EXECUTE FUNCTION reject_created_at_rewrite();
CREATE TRIGGER work_group_consolidations_created_at_immutable
    BEFORE UPDATE OF created_at ON work_group_consolidations
    FOR EACH ROW EXECUTE FUNCTION reject_created_at_rewrite();

INSERT INTO schema_migrations(version)
VALUES ('038_work_publication_effects') ON CONFLICT DO NOTHING;
COMMIT;
