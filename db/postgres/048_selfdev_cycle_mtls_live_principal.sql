-- Certificate recovery must also honor the principal credential expiry.
BEGIN;
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
       AND c.enabled=true
       AND (c.expires_at IS NULL OR c.expires_at>clock_timestamp())
       AND b.enabled=true AND b.revoked_at IS NULL
       AND b.certificate_sha256=p_fingerprint
       AND b.certificate_chain_pem IS NOT NULL
       AND i.state='COMPLETED'
       AND i.not_before<=clock_timestamp() AND i.not_after>clock_timestamp()
       AND b.expires_at>clock_timestamp()
     LIMIT 1
$$;
REVOKE ALL ON FUNCTION public.get_selfdev_cycle_mtls_certificate(text,text,text,text) FROM PUBLIC;
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname='aao_runtime') THEN
    GRANT EXECUTE ON FUNCTION public.get_selfdev_cycle_mtls_certificate(text,text,text,text) TO aao_runtime;
  END IF;
END $$;
INSERT INTO schema_migrations(version) VALUES ('048_selfdev_cycle_mtls_live_principal') ON CONFLICT DO NOTHING;
COMMIT;
