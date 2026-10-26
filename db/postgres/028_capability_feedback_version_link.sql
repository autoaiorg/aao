-- Link an accepted CEO correction to an explicitly registered immutable version.
BEGIN;

-- A CEO session is an independently authenticated principal, not an AGENT credential.
-- Keep the registry's database-level creator check, allowing CEO only for a version
-- whose provenance names an accepted feedback proposal in the same project/capability.
ALTER TABLE capability_versions DROP CONSTRAINT capability_versions_created_by_fkey;

CREATE FUNCTION enforce_capability_version_creator() RETURNS trigger AS $$
BEGIN
  IF NEW.created_by = 'ceo' THEN
    IF NEW.provenance->>'feedback_proposal_id' IS NULL
       OR NOT EXISTS (
         SELECT 1 FROM capability_feedback_proposals f
         WHERE f.id::text = NEW.provenance->>'feedback_proposal_id'
           AND f.project_id = NEW.project_id
           AND f.capability_id = NEW.capability_id
           AND f.version = NEW.provenance->>'source_version'
           AND f.status = 'accepted'
       ) THEN
      RAISE EXCEPTION 'CEO-created capability version must reference accepted feedback'
        USING ERRCODE = 'foreign_key_violation';
    END IF;
  ELSIF NOT EXISTS (
    SELECT 1 FROM principal_credentials p WHERE p.principal_id = NEW.created_by
  ) THEN
    RAISE EXCEPTION 'capability creator must be a registered principal'
      USING ERRCODE = 'foreign_key_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER capability_versions_creator_guard
  BEFORE INSERT OR UPDATE OF created_by, provenance ON capability_versions
  FOR EACH ROW EXECUTE FUNCTION enforce_capability_version_creator();

ALTER TABLE capability_feedback_proposals
  ADD COLUMN applied_capability_version text,
  ADD COLUMN applied_by text,
  ADD COLUMN applied_at timestamptz,
  ADD CONSTRAINT capability_feedback_applied_version_fk
    FOREIGN KEY (project_id, capability_id, applied_capability_version)
    REFERENCES capability_versions(project_id, capability_id, version),
  ADD CONSTRAINT capability_feedback_application_consistent
    CHECK ((applied_capability_version IS NULL AND applied_by IS NULL AND applied_at IS NULL)
        OR (status = 'accepted' AND applied_capability_version IS NOT NULL
            AND applied_by IS NOT NULL AND applied_at IS NOT NULL));

INSERT INTO schema_migrations(version)
VALUES ('028_capability_feedback_version_link') ON CONFLICT DO NOTHING;
COMMIT;
