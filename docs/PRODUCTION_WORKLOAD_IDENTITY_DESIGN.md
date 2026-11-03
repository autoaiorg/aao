# Production workload identity for AAO service principals

**Status: design proposal; not deployed or approved.** This document proposes a
production authentication path for non-human `AGENT` and `AUDITOR` workloads.
It does not authorize provider activation, external effects, integrator/R2
activation, or CEO actions. The development/test bearer-token gate must remain
unchanged until the production mechanism is independently accepted.

## Problem and constraints

`src/aao/principal_credentials.py` intentionally rejects `X-Agent-Token` and
`X-Auditor-Token` outside `AAO_ENV=development|test`. That is correct: those
values are bearer secrets, not evidence of a production workload identity. The
Self Development worker unit proposed in PR #356 sets `AAO_ENV=production`, so
it cannot authenticate against the production-mode API today. Do not work
around this by changing the environment or adding a shared token.

Required invariants:

1. The API derives the principal from a cryptographically authenticated
   workload identity; request bodies and headers cannot name a principal.
2. Every protected operation still checks principal kind, enabled state,
   expiry, and exact project grants. For mutating or queue operations these
   checks must be transactionally serialized with the operation so a revocation
   cannot race past authorization.
3. `AGENT` and `AUDITOR` identities cannot call CEO-only endpoints or stand in
   for human identity/signature.
4. Unknown, malformed, expired, revoked, misbound, or unverifiable identity
   fails closed. Outages fail unavailable, not open.
5. No identity secret or private key appears in argv, logs, general environment
   dumps, or API responses. Rotation and recovery are observable without
   exposing credentials.

## Candidate mechanisms

| Mechanism | Fit | Main risk/cost | Decision |
|---|---|---|---|
| OIDC workload tokens | Strong federation and short-lived tokens if a trusted issuer and workload attestation are already operated. | No issuer/attestation service is evidenced for this single-host deployment; adding one adds an external trust and availability dependency. | Do not assume availability. Revisit if AAO adopts a managed workload issuer. |
| Direct mTLS to the API | Strong channel binding; API can require a client certificate and map a verified certificate identity to a principal. | Must prove the ASGI server exposes the verified peer certificate safely, enforce TLS on every API listener, and keep CA issuance/revocation under controlled custody. | Viable candidate for a prototype, not yet selected for production. |
| Local Unix socket + peer credentials | On one Linux host, kernel-authenticated UID can bind a service account to a principal without a bearer secret. | Requires all workload API traffic to use the socket; browser/other clients need a separate listener. The current ASGI/API stack has no demonstrated peer-credential adapter. | Viable for a same-host prototype; avoid trusting spoofable forwarded headers. |
| Shared bearer or caller-supplied identity header | Easy to deploy. | A stolen/shared value is replayable and does not prove which workload sent a request. Headers can be forged if the network boundary is wrong. | Rejected. |

No production mechanism is selected in this proposal. The first implementation
slice should compare direct mTLS and Unix-socket peer credentials on the actual
host topology, then select one based on a threat-model review. Do not implement
an unverified proxy-header shortcut.

## Required principal binding and authorization flow

Whatever transport is selected must produce a server-side, verified identity
object containing a stable workload key. The API must then:

1. Resolve that key to exactly one existing `AGENT` or `AUDITOR` principal in
   the authoritative database; never accept a principal ID supplied by the
   caller as proof.
2. Check that the workload binding is enabled, unexpired, and bound to the
   expected principal and kind.
3. Check the principal credential is enabled and unexpired and that the exact
   project grant authorizes the requested capability.
4. Hold the appropriate row locks in the same transaction as sensitive reads,
   claims, completion, review, or mutation, following the existing
   credential/grant revocation serialization contract.
5. Record an audit event with principal, operation, and outcome, but no token,
   private key, or raw certificate material.

For certificate identity, use a stable opaque SAN identifier or certificate
serial mapped in the database; do not infer authority from a display name,
CN, DNS name, or caller header. For peer-credential identity, map the kernel
reported UID to an explicitly provisioned service principal; do not use a UID
sent by the client.

## Lifecycle and operational requirements

- Provisioning is explicit and idempotent. It binds one workload identity to
  one principal and records issuer, kind, expiry, and revocation state.
- Rotation has bounded overlap and a recovery procedure for crashes between
  issue, install, verification, and old-identity revocation. An old identity
  must not remain valid indefinitely after failed rotation.
- Revocation must block the next authorized request, including requests over
  an already-established TLS connection or a reused local socket.
- Issuer keys/CA trust material are root-controlled or held by a dedicated
  identity service; they are not readable by ordinary workers. If the API
  process can mint arbitrary identities, document that as an explicit trust
  boundary and constrain it with an independently protected signer where
  feasible.
- Short certificate/token TTL is defense in depth, not a substitute for the
  database enabled/grant checks. Define clock-skew bounds and fail closed when
  identity state cannot be fetched.
- Deploy separate API listeners/units for browser/CEO access and workloads if
  the chosen transport requires it. Do not expose an internal identity
  assertion header on an untrusted listener.
- Document host bootstrap, file/socket ownership and modes, monitoring, key
  rotation, outage behavior, rollback, and secret-safe evidence collection.

## Acceptance tests and gates

Before deployment, test against the actual production-mode transport and
identity verifier, not only `AAO_ENV=test` bearer auth:

- valid identity maps only to its registered principal;
- unknown, malformed, expired, disabled, wrong-kind, wrong-project, and revoked
  identities fail closed;
- caller-supplied principal IDs and identity headers cannot override transport
  identity;
- replay/rotation overlap and concurrent revocation have defined, tested
  outcomes;
- service restart, identity-provider outage, and stale connection behavior are
  fail-closed and recoverable;
- no secret enters logs, argv, environment dumps, responses, or audit payloads;
- cross-project access and CEO-only operations remain denied;
- the deployment runbook and rollback are exercised on a disposable host.

Independent security review and the applicable AAO authorization gates remain
required before production enablement. CI, merge, or this document alone does
not accept the design or authorize a worker to run.
