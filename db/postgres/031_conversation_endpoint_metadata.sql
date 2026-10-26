-- Record safe endpoint provenance for every provider-backed conversation turn.
BEGIN;
ALTER TABLE project_conversation_turns ADD COLUMN IF NOT EXISTS endpoint text NOT NULL DEFAULT 'unknown';
ALTER TABLE project_conversation_messages ADD COLUMN IF NOT EXISTS endpoint text;
INSERT INTO schema_migrations(version) VALUES ('031_conversation_endpoint_metadata')
ON CONFLICT DO NOTHING;
COMMIT;
