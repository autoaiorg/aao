-- Durable CEO-confirmed parent/child work breakdowns. Creation does not admit work.
BEGIN;
ALTER TABLE work_items ADD COLUMN IF NOT EXISTS parent_work_id uuid;
ALTER TABLE work_items ADD CONSTRAINT work_items_project_id_id_unique UNIQUE(project_id,id);
ALTER TABLE work_items ADD CONSTRAINT work_items_parent_same_project_fk
    FOREIGN KEY(project_id,parent_work_id) REFERENCES work_items(project_id,id)
    ON DELETE CASCADE;
ALTER TABLE work_items ADD CONSTRAINT work_items_not_own_parent
    CHECK(parent_work_id IS NULL OR parent_work_id <> id);
ALTER TABLE project_conversations ADD CONSTRAINT project_conversations_project_id_id_unique
    UNIQUE(project_id,id);

CREATE TABLE work_groups (
    id uuid PRIMARY KEY,
    project_id uuid NOT NULL REFERENCES projects(id),
    conversation_id uuid NOT NULL,
    parent_work_id uuid NOT NULL UNIQUE,
    idempotency_key uuid NOT NULL,
    request_sha256 text NOT NULL CHECK(length(request_sha256)=64),
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY(project_id,parent_work_id) REFERENCES work_items(project_id,id),
    FOREIGN KEY(project_id,conversation_id)
        REFERENCES project_conversations(project_id,id) ON DELETE CASCADE,
    UNIQUE(conversation_id,idempotency_key)
);

CREATE TABLE work_item_dependencies (
    project_id uuid NOT NULL,
    work_id uuid NOT NULL,
    depends_on_work_id uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(work_id,depends_on_work_id),
    CHECK(work_id <> depends_on_work_id),
    FOREIGN KEY(project_id,work_id) REFERENCES work_items(project_id,id) ON DELETE CASCADE,
    FOREIGN KEY(project_id,depends_on_work_id) REFERENCES work_items(project_id,id) ON DELETE CASCADE
);
CREATE INDEX ix_work_item_dependencies_prerequisite
    ON work_item_dependencies(project_id,depends_on_work_id);

INSERT INTO schema_migrations(version) VALUES ('020_persistent_work_groups')
ON CONFLICT DO NOTHING;
COMMIT;
