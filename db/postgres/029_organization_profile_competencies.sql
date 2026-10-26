-- CEO-declared areas of expertise used only to inform reviewed task routing.
BEGIN;

ALTER TABLE organization_profiles
  ADD COLUMN IF NOT EXISTS competencies TEXT[] NOT NULL DEFAULT '{}',
  ADD CONSTRAINT organization_profiles_competencies_count
    CHECK (cardinality(competencies) <= 50);

INSERT INTO schema_migrations(version)
VALUES ('029_organization_profile_competencies') ON CONFLICT DO NOTHING;
COMMIT;
