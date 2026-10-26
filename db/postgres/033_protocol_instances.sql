-- Pin the protocol/version and request identity without adding workflow state.
BEGIN;

CREATE TABLE protocol_instances (
  id UUID PRIMARY KEY,
  protocol_id TEXT NOT NULL CHECK (protocol_id IN (
    'intake-classification',
    'planning-assignment',
    'implementation',
    'review-acceptance',
    'blockage-escalation'
  )),
  protocol_version TEXT NOT NULL CHECK (length(btrim(protocol_version)) BETWEEN 1 AND 64),
  subject_type TEXT NOT NULL CHECK (subject_type IN ('work_item', 'work_group', 'execution')),
  subject_id UUID NOT NULL,
  idempotency_key TEXT NOT NULL CHECK (length(btrim(idempotency_key)) BETWEEN 1 AND 255),
  request_sha256 TEXT NOT NULL CHECK (request_sha256 ~ '^[0-9a-f]{64}$'),
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  started_by TEXT NOT NULL CHECK (length(btrim(started_by)) BETWEEN 1 AND 200),
  UNIQUE (protocol_id, subject_type, subject_id, idempotency_key)
);

-- No implicit PUBLIC access. The runtime role must be provisioned separately and
-- receive SELECT/INSERT only; it must not own this table or have elevated role flags.
REVOKE ALL ON TABLE protocol_instances FROM PUBLIC;

INSERT INTO schema_migrations(version)
VALUES ('033_protocol_instances') ON CONFLICT DO NOTHING;

COMMIT;
