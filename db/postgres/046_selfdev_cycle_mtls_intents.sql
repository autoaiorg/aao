-- Durable, narrowly mutable Self Development cycle mTLS intents.
-- Runtime callers receive EXECUTE on bounded SECURITY DEFINER functions only;
-- direct DML on the intent/binding tables remains revoked.
BEGIN;
CREATE TABLE IF NOT EXISTS selfdev_cycle_mtls_intents (
    intent_id uuid PRIMARY KEY,
    project_id uuid NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
    cycle_id text NOT NULL CHECK (cycle_id ~ '^[0-9a-f]{32}$'),
    principal_id text NOT NULL UNIQUE REFERENCES principal_credentials(principal_id) ON DELETE RESTRICT,
    kind text NOT NULL CHECK (kind IN ('AGENT','AUDITOR')),
    not_before timestamptz NOT NULL,
    not_after timestamptz NOT NULL,
    state text NOT NULL DEFAULT 'PENDING' CHECK (state IN ('PENDING','COMPLETED','REVOKED','EXPIRED')),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    completed_at timestamptz,
    revoked_at timestamptz,
    UNIQUE (project_id, cycle_id, kind),
    CHECK (not_after > not_before AND not_after <= not_before + interval '2 hours'),
    CHECK (state <> 'COMPLETED' OR completed_at IS NOT NULL),
    CHECK (completed_at IS NULL OR state IN ('COMPLETED','REVOKED')),
    CHECK ((state = 'REVOKED') = (revoked_at IS NOT NULL))
);
-- Upgrade deployments that created this table from the earlier 045 draft,
-- which did not enforce principal_id uniqueness.
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_catalog.pg_constraint
     WHERE conrelid='public.selfdev_cycle_mtls_intents'::regclass
       AND conname='selfdev_cycle_mtls_intents_principal_id_key'
  ) THEN
    ALTER TABLE public.selfdev_cycle_mtls_intents
      ADD CONSTRAINT selfdev_cycle_mtls_intents_principal_id_key UNIQUE (principal_id);
  END IF;
END $$;
CREATE INDEX IF NOT EXISTS ix_selfdev_cycle_mtls_intents_pending
    ON selfdev_cycle_mtls_intents(not_after) WHERE state='PENDING';
ALTER TABLE workload_identity_bindings
    ADD COLUMN IF NOT EXISTS intent_id uuid REFERENCES selfdev_cycle_mtls_intents(intent_id) ON DELETE RESTRICT,
    ADD COLUMN IF NOT EXISTS csr_sha256 text CHECK (csr_sha256 IS NULL OR csr_sha256 ~ '^[0-9a-f]{64}$');
CREATE UNIQUE INDEX IF NOT EXISTS uq_workload_identity_binding_intent
    ON workload_identity_bindings(intent_id) WHERE intent_id IS NOT NULL;

-- Do not permit the API runtime to forge certificate-fingerprint bindings.
REVOKE ALL ON TABLE selfdev_cycle_mtls_intents FROM PUBLIC;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON TABLE workload_identity_bindings FROM PUBLIC;

CREATE OR REPLACE FUNCTION create_selfdev_cycle_mtls_intent(
    p_intent_id uuid, p_project_id uuid, p_cycle_id text, p_principal_id text,
    p_kind text, p_not_before timestamptz, p_not_after timestamptz
) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_existing selfdev_cycle_mtls_intents%ROWTYPE;
    v_kind text;
    v_enabled boolean;
    v_expires timestamptz;
    v_project_name text;
BEGIN
    IF p_kind NOT IN ('AGENT','AUDITOR') OR p_cycle_id !~ '^[0-9a-f]{32}$'
       OR p_not_after <= p_not_before
       OR p_not_after > p_not_before + interval '2 hours' THEN
        RAISE EXCEPTION 'invalid cycle intent bounds' USING ERRCODE='22023';
    END IF;
    IF p_principal_id <> (CASE p_kind
        WHEN 'AGENT' THEN 'aao-selfdev-impl-' || p_cycle_id
        WHEN 'AUDITOR' THEN 'aao-selfdev-review-' || p_cycle_id
        ELSE NULL END) THEN
        RAISE EXCEPTION 'principal does not match cycle role' USING ERRCODE='23514';
    END IF;
    SELECT name INTO v_project_name FROM public.projects
      WHERE id=p_project_id AND state='ACTIVE' FOR SHARE;
    IF v_project_name IS DISTINCT FROM 'AAO — Self Development' THEN
        RAISE EXCEPTION 'cycle intent project is not active Self Development' USING ERRCODE='23514';
    END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended(
        'selfdev-cycle-mtls:' || p_project_id::text || ':' || p_cycle_id || ':' || p_kind, 0));
    SELECT * INTO v_existing FROM public.selfdev_cycle_mtls_intents
     WHERE project_id=p_project_id AND cycle_id=p_cycle_id AND kind=p_kind FOR UPDATE;
    IF FOUND THEN
        IF v_existing.intent_id=p_intent_id AND v_existing.principal_id=p_principal_id
           AND v_existing.not_before=p_not_before AND v_existing.not_after=p_not_after
           AND v_existing.state='PENDING' THEN RETURN; END IF;
        RAISE EXCEPTION 'cycle intent already exists' USING ERRCODE='23505';
    END IF;
    SELECT kind, enabled, expires_at INTO v_kind, v_enabled, v_expires
      FROM public.principal_credentials WHERE principal_id=p_principal_id FOR UPDATE;
    IF NOT FOUND OR v_kind <> p_kind OR v_enabled THEN
        RAISE EXCEPTION 'cycle principal is not pending' USING ERRCODE='23514';
    END IF;
    IF v_expires IS NOT NULL AND v_expires <= p_not_after THEN
        RAISE EXCEPTION 'cycle principal expires before its intent' USING ERRCODE='23514';
    END IF;
    INSERT INTO public.selfdev_cycle_mtls_intents
      (intent_id,project_id,cycle_id,principal_id,kind,not_before,not_after)
    VALUES (p_intent_id,p_project_id,p_cycle_id,p_principal_id,p_kind,p_not_before,p_not_after);
END;
$$;

-- Return a state instead of throwing after expiry so EXPIRED commits durably.
CREATE OR REPLACE FUNCTION complete_selfdev_cycle_mtls_binding(
    p_intent_id uuid, p_fingerprint text, p_csr_sha256 text
) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_intent public.selfdev_cycle_mtls_intents%ROWTYPE;
    v_kind text;
    v_enabled boolean;
    v_expires timestamptz;
    v_cert text;
    v_csr text;
BEGIN
    IF p_fingerprint !~ '^[0-9a-f]{64}$' OR p_csr_sha256 !~ '^[0-9a-f]{64}$' THEN
        RAISE EXCEPTION 'invalid public identity digest' USING ERRCODE='22023';
    END IF;
    SELECT * INTO v_intent FROM public.selfdev_cycle_mtls_intents
     WHERE intent_id=p_intent_id FOR UPDATE;
    IF NOT FOUND THEN RETURN 'NOT_FOUND'; END IF;
    IF v_intent.state='COMPLETED' THEN
        SELECT certificate_sha256, csr_sha256 INTO v_cert,v_csr
          FROM public.workload_identity_bindings WHERE intent_id=p_intent_id;
        IF v_cert=p_fingerprint AND v_csr=p_csr_sha256 THEN RETURN 'COMPLETED'; END IF;
        RETURN 'CONFLICT';
    END IF;
    IF v_intent.state <> 'PENDING' THEN RETURN v_intent.state; END IF;
    IF v_intent.not_after <= clock_timestamp() THEN
        UPDATE public.selfdev_cycle_mtls_intents SET state='EXPIRED' WHERE intent_id=p_intent_id;
        RETURN 'EXPIRED';
    END IF;
    IF v_intent.not_before > clock_timestamp() THEN RETURN 'NOT_YET_VALID'; END IF;
    SELECT kind, enabled, expires_at INTO v_kind,v_enabled,v_expires
      FROM public.principal_credentials WHERE principal_id=v_intent.principal_id FOR UPDATE;
    IF NOT FOUND OR v_kind <> v_intent.kind OR v_enabled
       OR (v_expires IS NOT NULL AND v_expires <= v_intent.not_after) THEN
        RETURN 'PRINCIPAL_NOT_PENDING';
    END IF;
    INSERT INTO public.workload_identity_bindings
      (certificate_sha256,principal_id,enabled,issued_at,expires_at,intent_id,csr_sha256)
    VALUES (p_fingerprint,v_intent.principal_id,true,clock_timestamp(),v_intent.not_after,p_intent_id,p_csr_sha256);
    UPDATE public.selfdev_cycle_mtls_intents
       SET state='COMPLETED',completed_at=clock_timestamp() WHERE intent_id=p_intent_id;
    UPDATE public.principal_credentials SET enabled=true WHERE principal_id=v_intent.principal_id;
    RETURN 'COMPLETED';
END;
$$;

CREATE OR REPLACE FUNCTION expire_selfdev_cycle_mtls_intent(p_intent_id uuid)
RETURNS boolean
LANGUAGE sql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
    UPDATE public.selfdev_cycle_mtls_intents
       SET state='EXPIRED'
     WHERE intent_id=p_intent_id AND state='PENDING'
       AND not_after <= clock_timestamp()
    RETURNING true
$$;

CREATE OR REPLACE FUNCTION revoke_selfdev_cycle_mtls_intent(p_intent_id uuid)
RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE v_intent public.selfdev_cycle_mtls_intents%ROWTYPE;
BEGIN
    SELECT * INTO v_intent FROM public.selfdev_cycle_mtls_intents
     WHERE intent_id=p_intent_id FOR UPDATE;
    IF NOT FOUND THEN RETURN false; END IF;
    UPDATE public.workload_identity_bindings SET enabled=false,
      revoked_at=COALESCE(revoked_at,clock_timestamp())
     WHERE intent_id=p_intent_id AND enabled=true;
    UPDATE public.principal_credentials SET enabled=false
     WHERE principal_id=v_intent.principal_id;
    UPDATE public.selfdev_cycle_mtls_intents SET state='REVOKED',
      revoked_at=COALESCE(revoked_at,clock_timestamp())
     WHERE intent_id=p_intent_id AND state<>'REVOKED';
    RETURN true;
END;
$$;
REVOKE ALL ON FUNCTION create_selfdev_cycle_mtls_intent(uuid,uuid,text,text,text,timestamptz,timestamptz) FROM PUBLIC;
REVOKE ALL ON FUNCTION complete_selfdev_cycle_mtls_binding(uuid,text,text) FROM PUBLIC;
REVOKE ALL ON FUNCTION expire_selfdev_cycle_mtls_intent(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION revoke_selfdev_cycle_mtls_intent(uuid) FROM PUBLIC;
-- Some CI/test databases do not yet provision the runtime role. Do not create
-- identities here; grant bounded access only where bootstrap already created it.
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname='aao_runtime') THEN
    REVOKE ALL ON TABLE selfdev_cycle_mtls_intents FROM aao_runtime;
    REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON TABLE workload_identity_bindings FROM aao_runtime;
    -- REVOKE table-level UPDATE does not clear older column-level grants.
    REVOKE UPDATE (enabled, revoked_at) ON TABLE workload_identity_bindings FROM aao_runtime;
    GRANT SELECT ON TABLE selfdev_cycle_mtls_intents TO aao_runtime;
    GRANT EXECUTE ON FUNCTION create_selfdev_cycle_mtls_intent(uuid,uuid,text,text,text,timestamptz,timestamptz) TO aao_runtime;
    -- Completion is reserved for a future isolated certificate verifier.
    GRANT EXECUTE ON FUNCTION expire_selfdev_cycle_mtls_intent(uuid) TO aao_runtime;
    GRANT EXECUTE ON FUNCTION revoke_selfdev_cycle_mtls_intent(uuid) TO aao_runtime;
  END IF;
  -- Clear legacy grants even when the service role is absent in test/bootstrap DBs.
  REVOKE UPDATE (enabled, revoked_at) ON TABLE workload_identity_bindings FROM PUBLIC;
END $$;
INSERT INTO schema_migrations(version)
VALUES ('046_selfdev_cycle_mtls_intents') ON CONFLICT DO NOTHING;
COMMIT;
