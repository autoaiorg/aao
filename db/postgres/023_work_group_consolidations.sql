-- CEO-confirmed, evidence-bound consolidation of completed work-group children.
BEGIN;
CREATE TABLE work_group_consolidations (
    id uuid PRIMARY KEY,
    project_id uuid NOT NULL REFERENCES projects(id),
    work_group_id uuid NOT NULL UNIQUE REFERENCES work_groups(id) ON DELETE CASCADE,
    parent_work_id uuid NOT NULL UNIQUE REFERENCES work_items(id) ON DELETE CASCADE,
    summary text NOT NULL CHECK(length(trim(summary)) > 0),
    source_sha256 text NOT NULL CHECK(source_sha256 ~ '^[0-9a-f]{64}$'),
    source_snapshot jsonb NOT NULL CHECK(jsonb_typeof(source_snapshot)='object'),
    idempotency_key uuid NOT NULL,
    request_sha256 text NOT NULL CHECK(request_sha256 ~ '^[0-9a-f]{64}$'),
    created_by text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE(project_id,idempotency_key)
);
INSERT INTO schema_migrations(version) VALUES ('023_work_group_consolidations')
ON CONFLICT DO NOTHING;
COMMIT;
