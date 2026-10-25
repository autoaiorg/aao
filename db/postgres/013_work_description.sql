-- Work-item descriptions are part of the trusted task instructions for W1.
BEGIN;
ALTER TABLE work_items ADD COLUMN IF NOT EXISTS description text NOT NULL DEFAULT '';
INSERT INTO schema_migrations(version) VALUES ('013_work_description') ON CONFLICT DO NOTHING;
COMMIT;
