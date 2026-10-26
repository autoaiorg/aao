-- CEO-reviewed capability feedback is a proposal only; it never mutates a capability version.
BEGIN;

CREATE TABLE capability_feedback_proposals (
  id uuid PRIMARY KEY,
  project_id uuid NOT NULL REFERENCES projects(id),
  capability_id text NOT NULL,
  version text NOT NULL,
  work_id uuid,
  correction text NOT NULL CHECK (length(btrim(correction)) BETWEEN 1 AND 4000),
  evidence jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(evidence) = 'array'),
  status text NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed','accepted','rejected')),
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  FOREIGN KEY(project_id, capability_id, version)
    REFERENCES capability_versions(project_id, capability_id, version),
  FOREIGN KEY(project_id, work_id) REFERENCES work_items(project_id, id),
  CHECK (work_id IS NOT NULL OR jsonb_array_length(evidence) > 0)
);

CREATE INDEX ix_capability_feedback_project_created
  ON capability_feedback_proposals(project_id, created_at DESC, id);

INSERT INTO schema_migrations(version)
VALUES ('026_capability_feedback_proposals') ON CONFLICT DO NOTHING;
COMMIT;
