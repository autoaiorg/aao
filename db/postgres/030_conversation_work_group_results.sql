-- Distinguish AAO's durable system result notifications from chat/provider replies.
BEGIN;
ALTER TABLE project_conversation_messages
    ADD COLUMN IF NOT EXISTS message_kind text NOT NULL DEFAULT 'CHAT';
ALTER TABLE project_conversation_messages
    ADD CONSTRAINT project_conversation_messages_kind_check
    CHECK (message_kind IN ('CHAT','WORK_GROUP_RESULT'));
ALTER TABLE project_conversation_messages
    DROP CONSTRAINT IF EXISTS project_conversation_messages_body_check;
ALTER TABLE project_conversation_messages
    ADD CONSTRAINT project_conversation_messages_body_check
    CHECK (length(body) BETWEEN 1 AND 30000);
INSERT INTO schema_migrations(version) VALUES ('030_conversation_work_group_results')
ON CONFLICT DO NOTHING;
COMMIT;
