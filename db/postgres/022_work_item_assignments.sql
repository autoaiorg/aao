-- CEO-declared child-work routing; references existing identity and never grants authority.
BEGIN;
CREATE TABLE work_item_assignments (
    project_id uuid NOT NULL,
    work_id uuid PRIMARY KEY,
    principal_id text NOT NULL REFERENCES principal_credentials(principal_id) ON DELETE RESTRICT,
    assigned_by text NOT NULL,
    assigned_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    FOREIGN KEY(project_id,work_id) REFERENCES work_items(project_id,id) ON DELETE CASCADE
);
CREATE INDEX ix_work_item_assignments_principal_project
    ON work_item_assignments(project_id,principal_id);
INSERT INTO schema_migrations(version) VALUES ('022_work_item_assignments')
ON CONFLICT DO NOTHING;
COMMIT;
