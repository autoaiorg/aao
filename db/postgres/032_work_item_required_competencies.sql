-- Persist explicit skill requirements so PM routing can be checked against CEO profiles.
BEGIN;

ALTER TABLE work_items
  ADD COLUMN IF NOT EXISTS required_competencies TEXT[] NOT NULL DEFAULT '{}',
  ADD CONSTRAINT work_items_required_competencies_count
    CHECK (cardinality(required_competencies) <= 20);

INSERT INTO schema_migrations(version)
VALUES ('032_work_item_required_competencies') ON CONFLICT DO NOTHING;
COMMIT;
