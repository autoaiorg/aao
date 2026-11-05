-- Durable visual motion routes, isolated from organizational and work evidence.
BEGIN;

CREATE TABLE IF NOT EXISTS office_world_routes (
  actor_id text PRIMARY KEY,
  actor_kind text NOT NULL CHECK (actor_kind IN ('AGENT','NPC')),
  map_revision text NOT NULL CHECK (length(map_revision) BETWEEN 1 AND 128),
  route_json jsonb NOT NULL CHECK (
    jsonb_typeof(route_json) = 'array' AND jsonb_array_length(route_json) BETWEEN 2 AND 128
  ),
  speed double precision NOT NULL CHECK (speed >= 0.05 AND speed <= 2.0),
  started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CHECK ((actor_kind = 'NPC' AND actor_id LIKE 'npc:%') OR
         (actor_kind = 'AGENT' AND actor_id NOT LIKE 'npc:%'))
);

CREATE INDEX IF NOT EXISTS ix_office_world_routes_map_revision
  ON office_world_routes(map_revision);
REVOKE ALL ON TABLE office_world_routes FROM PUBLIC;
INSERT INTO schema_migrations(version)
VALUES ('047_office_world_motion') ON CONFLICT DO NOTHING;
COMMIT;
