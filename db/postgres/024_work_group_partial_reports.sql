-- CEO-authored, non-final observations bound to durable work-group snapshots.
BEGIN;
CREATE TABLE work_group_partial_reports (
    id uuid PRIMARY KEY,
    project_id uuid NOT NULL REFERENCES projects(id),
    work_group_id uuid NOT NULL REFERENCES work_groups(id) ON DELETE CASCADE,
    parent_work_id uuid NOT NULL REFERENCES work_items(id) ON DELETE CASCADE,
    report_kind text NOT NULL CHECK(report_kind IN ('PARTIAL','CONFLICT_REVIEW')),
    summary text NOT NULL CHECK(length(trim(summary)) > 0),
    source_sha256 text NOT NULL CHECK(source_sha256 ~ '^[0-9a-f]{64}$'),
    source_snapshot jsonb NOT NULL CHECK(jsonb_typeof(source_snapshot)='object'),
    idempotency_key uuid NOT NULL,
    request_sha256 text NOT NULL CHECK(request_sha256 ~ '^[0-9a-f]{64}$'),
    created_by text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE(project_id,idempotency_key)
);
CREATE INDEX work_group_partial_reports_group_created
    ON work_group_partial_reports(work_group_id,created_at,id);
INSERT INTO schema_migrations(version) VALUES ('024_work_group_partial_reports')
ON CONFLICT DO NOTHING;
COMMIT;
