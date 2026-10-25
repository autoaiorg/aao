-- Record provider provenance for generated conversation responses.
BEGIN;
ALTER TABLE project_conversation_messages
    ADD COLUMN IF NOT EXISTS provider text,
    ADD COLUMN IF NOT EXISTS model text;
INSERT INTO schema_migrations(version) VALUES ('018_conversation_provider_metadata')
ON CONFLICT DO NOTHING;
COMMIT;
