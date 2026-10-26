-- Record an explicit CEO decision without applying the correction to an active capability.
BEGIN;

ALTER TABLE capability_feedback_proposals
  ADD COLUMN reviewed_by text,
  ADD COLUMN reviewed_at timestamptz;

ALTER TABLE capability_feedback_proposals
  ADD CONSTRAINT capability_feedback_review_metadata_consistent
  CHECK ((status = 'proposed' AND reviewed_by IS NULL AND reviewed_at IS NULL)
      OR (status IN ('accepted', 'rejected') AND reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL));

INSERT INTO schema_migrations(version)
VALUES ('027_capability_feedback_review') ON CONFLICT DO NOTHING;
COMMIT;
