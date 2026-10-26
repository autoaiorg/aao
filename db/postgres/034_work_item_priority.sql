-- CEO-controlled scheduling priority for unfinished work; no grant or role inference.
BEGIN;

ALTER TABLE work_items
  ADD COLUMN IF NOT EXISTS priority TEXT NOT NULL DEFAULT 'NORMAL'
  CHECK (priority IN ('NORMAL', 'HIGH'));

INSERT INTO schema_migrations(version)
VALUES ('034_work_item_priority') ON CONFLICT DO NOTHING;

COMMIT;
