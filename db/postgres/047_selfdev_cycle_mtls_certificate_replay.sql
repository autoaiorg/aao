-- Persist only public certificate chains and expose them only to the exact
-- currently authenticated workload identity. No signer/CA material is stored.
BEGIN;
ALTER TABLE public.workload_identity_bindings
    ADD COLUMN IF NOT EXISTS certificate_chain_pem text;
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_constraint
         WHERE conrelid='public.workload_identity_bindings'::regclass
           AND conname='workload_identity_bindings_public_chain_check'
    ) THEN
        ALTER TABLE public.workload_identity_bindings
          ADD CONSTRAINT workload_identity_bindings_public_chain_check
          CHECK (certificate_chain_pem IS NULL OR (
            octet_length(certificate_chain_pem) BETWEEN 1 AND 131072
            AND certificate_chain_pem LIKE '%-----BEGIN CERTIFICATE-----%'
            AND certificate_chain_pem NOT LIKE '%PRIVATE KEY%'
          ));
    END IF;
END $$;

-- The previous API-side completion function had no chain argument. Remove it
-- so no caller can create a completed binding through the legacy contract.
REVOKE ALL ON FUNCTION public.complete_selfdev_cycle_mtls_binding(uuid,text,text) FROM PUBLIC;
DROP FUNCTION IF EXISTS public.complete_selfdev_cycle_mtls_binding(uuid,text,text);

CREATE OR REPLACE FUNCTION public.complete_selfdev_cycle_mtls_binding(
    p_intent_id uuid, p_fingerprint text, p_csr_sha256 text, p_chain text
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
    v_chain text;
BEGIN
    IF p_fingerprint !~ '^[0-9a-f]{64}$' OR p_csr_sha256 !~ '^[0-9a-f]{64}$'
       OR p_chain IS NULL OR octet_length(p_chain) NOT BETWEEN 1 AND 131072
       OR p_chain NOT LIKE '%-----BEGIN CERTIFICATE-----%'
       OR p_chain LIKE '%PRIVATE KEY%' THEN
        RAISE EXCEPTION 'invalid public certificate binding' USING ERRCODE='22023';
    END IF;
    SELECT * INTO v_intent FROM public.selfdev_cycle_mtls_intents
     WHERE intent_id=p_intent_id FOR UPDATE;
    IF NOT FOUND THEN RETURN 'NOT_FOUND'; END IF;
    IF v_intent.state='COMPLETED' THEN
        SELECT certificate_sha256, csr_sha256, certificate_chain_pem
          INTO v_cert,v_csr,v_chain
          FROM public.workload_identity_bindings WHERE intent_id=p_intent_id;
        IF v_cert=p_fingerprint AND v_csr=p_csr_sha256 AND v_chain=p_chain THEN RETURN 'COMPLETED'; END IF;
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
      (certificate_sha256,principal_id,enabled,issued_at,expires_at,intent_id,csr_sha256,certificate_chain_pem)
    VALUES (p_fingerprint,v_intent.principal_id,true,clock_timestamp(),v_intent.not_after,p_intent_id,p_csr_sha256,p_chain);
    UPDATE public.selfdev_cycle_mtls_intents
       SET state='COMPLETED',completed_at=clock_timestamp() WHERE intent_id=p_intent_id;
    UPDATE public.principal_credentials SET enabled=true WHERE principal_id=v_intent.principal_id;
    RETURN 'COMPLETED';
END;
$$;

CREATE OR REPLACE FUNCTION public.get_selfdev_cycle_mtls_certificate(
    p_principal_id text, p_token_digest text, p_kind text, p_fingerprint text
) RETURNS TABLE(certificate_chain_pem text, certificate_sha256 text, expires_at timestamptz)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
    SELECT b.certificate_chain_pem, b.certificate_sha256, b.expires_at
      FROM public.principal_credentials c
      JOIN public.selfdev_cycle_mtls_intents i
        ON i.principal_id=c.principal_id AND i.kind=c.kind
      JOIN public.workload_identity_bindings b
        ON b.intent_id=i.intent_id AND b.principal_id=c.principal_id
     WHERE c.principal_id=p_principal_id
       AND c.token_digest=p_token_digest
       AND c.kind=p_kind AND p_kind IN ('AGENT','AUDITOR')
       -- principal_credentials has no revoked_at column: CEO revocation is
       -- represented by enabled=false. Do not invent a second revocation flag.
       AND c.enabled=true
       AND b.enabled=true AND b.revoked_at IS NULL
       AND b.certificate_sha256=p_fingerprint
       AND b.certificate_chain_pem IS NOT NULL
       AND i.state='COMPLETED'
       AND i.not_before<=clock_timestamp() AND i.not_after>clock_timestamp()
       AND b.expires_at>clock_timestamp()
     LIMIT 1
$$;
REVOKE ALL ON FUNCTION public.complete_selfdev_cycle_mtls_binding(uuid,text,text,text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.get_selfdev_cycle_mtls_certificate(text,text,text,text) FROM PUBLIC;
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname='aao_runtime') THEN
    GRANT EXECUTE ON FUNCTION public.get_selfdev_cycle_mtls_certificate(text,text,text,text) TO aao_runtime;
  END IF;
END $$;
INSERT INTO schema_migrations(version) VALUES ('047_selfdev_cycle_mtls_certificate_replay') ON CONFLICT DO NOTHING;
COMMIT;
