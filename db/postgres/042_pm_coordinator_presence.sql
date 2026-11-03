-- Persist the PM coordinator's actual loop state for the office projection.
BEGIN;
CREATE TABLE pm_coordinator_presence (
    principal_id text PRIMARY KEY REFERENCES principal_credentials(principal_id),
    project_id uuid NOT NULL REFERENCES projects(id),
    state text NOT NULL CHECK (state IN ('COORDINATING','WAITING')),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
REVOKE ALL ON TABLE pm_coordinator_presence FROM PUBLIC;
INSERT INTO schema_migrations(version)
VALUES ('042_pm_coordinator_presence') ON CONFLICT DO NOTHING;
COMMIT;
