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
| Direct mTLS to a dedicated workload API listener | The verified client certificate gives each workload principal a distinct cryptographic identity, including overlapping rotation cycles. | Must prove the ASGI server exposes the verified peer certificate safely, require client certificates on this listener, and control CA issuance/revocation. | **Preferred design for cycle-capable production workloads**, subject to implementation and independent review. |
| Local Unix socket + peer credentials | Kernel-authenticated UID identifies a local Linux account without a bearer secret. | The PM and cycle workers reuse fixed Linux accounts while rotation creates overlapping, distinct AAO principals. UID alone cannot distinguish the old worker from the new one during overlap; mapping one UID to the current principal would misattribute requests. | **Not sufficient for cycle identity as currently deployed.** Reconsider only with unique OS identities per concurrently valid principal or another unforgeable per-process credential. |
| Shared bearer or caller-supplied identity header | Easy to deploy. | A stolen/shared value is replayable and does not prove which workload sent a request. Headers can be forged if the network boundary is wrong. | Rejected. |

## Current deployment evidence and recommended first implementation

The current local deployment is single-host: API and worker services run under
separate Linux accounts and communicate over loopback HTTP. The API's
`require_worker` dependency still uses the development/test bearer-token
authenticator. An unset `AAO_ENV` is not a production identity mode: it leaves
that authenticator disabled, so an agent token is rejected (the observed
`403 Individual agent credential rejected` is expected). Do not “fix” this by
setting `AAO_ENV=development` or by re-enabling bearer tokens in production.

The installed Uvicorn H11 protocol does not place Unix peer credentials in the
ASGI scope. A production implementation therefore cannot safely infer identity
from ordinary ASGI `client` data or a caller-supplied header. Uvicorn's
`Config` accepts a protocol class, so a narrowly scoped custom HTTP protocol
can read Linux `SO_PEERCRED` from the accepted Unix-domain socket and attach
the kernel-reported UID to a private ASGI scope extension. This is a viable
same-host implementation path, but it still needs an integration test using
the deployed Uvicorn version before it is treated as supported.

**Recommendation:** use a dedicated mTLS workload listener, separate from the
browser/CEO listener. Issue a distinct client certificate and private key for
each AAO workload principal; bind its verified certificate fingerprint (or
stable opaque SAN URI, not a display name) to that exact principal in the
database. This distinguishes old and new cycle principals while both run under
the same Linux account during bounded overlap. Keep the browser/CEO API on its
existing TCP listener and do not accept caller-supplied identity headers on
either listener. Preserve development/test bearer auth only in those
environments. Deliver client keys through protected systemd credentials or an
equivalent root-controlled file path, never argv or a general environment
variable. The API must check the database binding and principal/grant state on
each operation, so revocation blocks an established TLS connection too.

The AF_UNIX/SO_PEERCRED adapter in this worktree is a transport experiment only;
it proves that Uvicorn can attach kernel-reported local UID metadata, but UID is
not a unique identity for overlapping cycle principals. It must not be wired
into production authentication for the current deployment. Reconsider it only
if each concurrently valid workload principal gets a distinct OS identity (or
another independently verified, per-process identity).

This recommendation is not an implementation or deployment authorization.
The API must still re-check principal state, kind, expiry and grants in the
authoritative database for each operation, and the production integration
tests and independent security review below remain mandatory.

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

For mTLS identity, require certificate verification at the workload listener
and map the verified fingerprint or stable opaque SAN identifier to exactly
one explicitly provisioned service principal; do not infer authority from a
display name, CN, DNS name, or caller header. If the AF_UNIX alternative is
ever used, the UID must identify exactly one concurrently valid principal;
mapping a shared role UID to whichever cycle is newest is prohibited.

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
- Deploy separate API listeners/units for browser/CEO access and workloads.
  The workload listener must require and verify client certificates. Do not
  expose an internal identity assertion header on an untrusted listener.
- Document host bootstrap, file/socket ownership and modes, monitoring, key
  rotation, outage behavior, rollback, and secret-safe evidence collection.

## Acceptance tests and gates

Before deployment, test against the actual production-mode transport and
identity verifier, not only `AAO_ENV=test` bearer auth:

- valid identity maps only to its registered principal;
- concurrently valid old/new cycle certificates map to their respective
  principals even when both workers run under the same Linux account;
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

## Concrete cycle-identity proposal (not implemented or deployed)

The current binding table maps a certificate fingerprint to one principal. It
does not represent a renewal cycle, and the cycle issuer currently creates
bearer credentials without a certificate. Therefore the PM certificate cannot
be reused to call as an implementer or auditor, and the renewal timer must stop
before reading credentials whenever `AAO_ENV=production`.

### Authority and CA boundary

Use a dedicated, root-owned host signing service as the only CA signing
boundary. Its private CA key is readable only by that service (or held in a
hardware-backed signer); neither the API, PM, implementer, reviewer nor
publisher account receives it. The service accepts a narrowly typed issuance
intent over a local Unix socket with peer-UID authorization, not an arbitrary
CSR plus caller-selected principal or expiry. The intent is created by the API
only after the cycle issuance transaction commits and contains the exact
principal ID, cycle ID, workload kind, and bounded `not_after`. The signer
checks the committed cycle record itself before signing. Private keys are
generated by the target workload account, kept mode 0600, and only the CSR
crosses the local socket. The signer returns a certificate chain, never a
private key. This keeps signing authority separate from the API's database
authority and prevents the PM from minting identities for another principal.

### Data binding, issue, rotation, and revocation

Add a cycle binding record with unique `(cycle_id, principal_id)` and unique
certificate fingerprint, `kind`, `not_before`, `not_after`, and `revoked_at`.
The issuance transaction must create the cycle principals, exact project
grants, and a pending signing intent atomically. A reconciler asks the signer
to materialize that intent idempotently; an incomplete or absent certificate
keeps the cycle in `ISSUING` and not executable. The signer has no endpoint to
change grants, enable principals, or set expiry beyond the committed cycle
expiry. All values are server-derived from the authorized cycle request.

During rotation, keep old and new cycle certificates bound to their respective
principal IDs during the explicitly bounded overlap. The API resolves each
verified certificate to its own principal, never to “the current cycle” by
Linux UID. After drain or the overlap deadline, one DB transaction revokes the
old binding, disables/revokes the old principal, and marks that cycle revoked.
Every protected operation rechecks binding and principal state while holding
the transaction locks used for the work/lease/effect mutation. Thus an existing
TLS connection does not preserve authority after revocation. Certificate
expiry is an outer bound; the DB check is the immediate revocation mechanism.

### Worker consumption and host rollout

Each implementer and reviewer gets its own per-cycle keypair and certificate.
The worker unit consumes them through systemd `LoadCredential=` from a
root-controlled staging area; its process reads only its own credential files
from `$CREDENTIALS_DIRECTORY`. Do not put key bytes, bearer values, or paths to
secret-bearing files in argv or general environment. Renewal installs the new
certificate atomically under the target account, verifies the public
fingerprint against the API binding, starts a distinct cycle unit with the new
credentials, proves `/v1/principals/me` resolves to that exact principal, then
drains and revokes the old cycle. Crashes leave either the old cycle active or
the new cycle in non-executable `ISSUING`; there is no fallback to a PM token.

Host deployment is explicitly blocked until an independently reviewed signer
and wrapper exist. An administrator must then, in a real terminal:

1. Install the signer binary/unit and CA trust chain from an accepted frozen
   revision; create the CA key only through the selected protected signer
   mechanism, never a shell command or checked-in file.
2. Set signer unit, socket, CA public certificate and API service ownership to
   root; grant only the signer socket to the API identity for issuance and only
   the exact target role UID for its own CSR request. Do not grant workers access
   to the CA key or other roles' private keys.
3. Install the reviewed mTLS API workload unit with client-certificate
   verification required; keep the browser/CEO listener separate.
4. Install the reviewed per-cycle credential helper and systemd templates,
   run metadata-only preflight and the disposable-host revocation/rotation
   acceptance suite, and only then enable the timer under its explicit gate.

No `sudo` command is provided yet: the required signer and wrapper artifacts do
not exist in this branch, and running ad-hoc signing commands would create an
unreviewed trust root. The concrete sudo runbook must be generated from those
accepted artifacts, not guessed now.

## Publisher identity is a separate blocked contract

W2 publishers are not self-development cycle roles. A publisher needs a
separate service identity and cannot borrow either a PM/worker cert or a
publisher bearer token in production. The safe target is a local publisher
broker/API: the role-specific process authenticates with its own mTLS
certificate; the API resolves the exact publisher principal and transactionally
reserves the authorized publication effect; the broker then uses that role's
GitHub App key from its own systemd credential directory. The CEO credential
issuer remains an explicit, bounded provisioning action and is not available to
the worker. A publication dispatched to GitHub cannot be undone merely by
revoking the certificate, so idempotency/effect reconciliation must remain
inside the existing publication-effect protocol.

This branch does not implement the broker or a secure publisher CLI contract.
`scripts/publish_candidate.py` therefore rejects production mode before reading
any publisher token. Direct SQL, `PGOPTIONS`, alternate role bearer tokens,
shared certificates, or a generic local root helper are not acceptable
substitutes. Publisher enablement remains blocked until the broker's identity,
effect reservation, GitHub credential isolation, retry and revocation behavior
receive separate tests and independent review.
