BEGIN;

ALTER TABLE work_items ADD COLUMN IF NOT EXISTS due_date date;

INSERT INTO schema_migrations(version) VALUES ('025_work_item_due_dates')
ON CONFLICT DO NOTHING;

COMMIT;
