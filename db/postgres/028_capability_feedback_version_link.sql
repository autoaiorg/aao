-- Link an accepted CEO correction to an explicitly registered immutable version.
BEGIN;

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
