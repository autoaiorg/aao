-- Canonical organizational metadata, deliberately separate from credentials/grants.
BEGIN;
CREATE TABLE IF NOT EXISTS organization_units (
  id TEXT PRIMARY KEY CHECK (id ~ '^[a-zA-Z0-9_-]{1,128}$'),
  name TEXT NOT NULL CHECK (length(name) BETWEEN 1 AND 200),
  code TEXT NOT NULL UNIQUE CHECK (length(code) BETWEEN 1 AND 64),
  parent_id TEXT REFERENCES organization_units(id) ON DELETE RESTRICT,
  lead_principal_id TEXT REFERENCES principal_credentials(principal_id) ON DELETE RESTRICT,
  enabled BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  CHECK (parent_id IS NULL OR parent_id <> id)
);
CREATE TABLE IF NOT EXISTS organization_profiles (
  principal_id TEXT PRIMARY KEY REFERENCES principal_credentials(principal_id) ON DELETE RESTRICT,
  display_name TEXT NOT NULL CHECK (length(display_name) BETWEEN 1 AND 200),
  role_title TEXT NOT NULL CHECK (length(role_title) BETWEEN 1 AND 200),
  unit_id TEXT REFERENCES organization_units(id) ON DELETE RESTRICT,
  manager_principal_id TEXT REFERENCES principal_credentials(principal_id) ON DELETE RESTRICT,
  enabled BOOLEAN NOT NULL DEFAULT TRUE,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  CHECK (manager_principal_id IS NULL OR manager_principal_id <> principal_id)
);
CREATE INDEX IF NOT EXISTS ix_organization_profiles_unit ON organization_profiles(unit_id) WHERE enabled;
INSERT INTO schema_migrations(version) VALUES ('015_organization_profiles') ON CONFLICT DO NOTHING;
COMMIT;
