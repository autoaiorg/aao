-- Durable project-scoped conversation transcript. Messages are records only;
-- this schema does not invoke a model or authorize work execution.
BEGIN;
CREATE TABLE IF NOT EXISTS project_conversations (
    id uuid PRIMARY KEY,
    project_id uuid NOT NULL REFERENCES projects(id),
    title text NOT NULL CHECK(length(title) BETWEEN 1 AND 200),
    created_by text NOT NULL CHECK(created_by='ceo'),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_project_conversations_project_updated
    ON project_conversations(project_id, updated_at DESC, id);

CREATE TABLE IF NOT EXISTS project_conversation_messages (
    id uuid PRIMARY KEY,
    conversation_id uuid NOT NULL REFERENCES project_conversations(id) ON DELETE CASCADE,
    sender text NOT NULL CHECK(sender IN ('CEO','AAO')),
    body text NOT NULL CHECK(length(body) BETWEEN 1 AND 10000),
    related_work_id uuid REFERENCES work_items(id),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_conversation_messages_order
    ON project_conversation_messages(conversation_id, created_at, id);
INSERT INTO schema_migrations(version) VALUES ('016_project_conversations')
ON CONFLICT DO NOTHING;
COMMIT;
