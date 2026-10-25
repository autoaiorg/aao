-- Durable lifecycle and idempotency for provider-backed CEO conversation turns.
BEGIN;
CREATE TABLE IF NOT EXISTS project_conversation_turns (
    id uuid PRIMARY KEY,
    conversation_id uuid NOT NULL REFERENCES project_conversations(id) ON DELETE CASCADE,
    idempotency_key uuid NOT NULL,
    request_sha256 text NOT NULL CHECK(length(request_sha256)=64),
    user_message_id uuid NOT NULL UNIQUE REFERENCES project_conversation_messages(id),
    assistant_message_id uuid UNIQUE REFERENCES project_conversation_messages(id),
    state text NOT NULL CHECK(state IN ('PENDING','COMPLETED','FAILED')),
    provider text NOT NULL,
    model text NOT NULL,
    error_code text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(conversation_id, idempotency_key),
    CHECK ((state='COMPLETED') = (assistant_message_id IS NOT NULL)),
    CHECK ((state='FAILED') = (error_code IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS ix_conversation_turns_recent
    ON project_conversation_turns(conversation_id, created_at DESC);
INSERT INTO schema_migrations(version) VALUES ('019_project_conversation_turns')
ON CONFLICT DO NOTHING;
COMMIT;
