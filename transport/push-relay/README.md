# Conditional push transport prototype — NOT deployed

Construction only, Phase 0 / B-2 recovery contribution, not gate acceptance.
The CEO approved Worker Free + D1 Free as a candidate architecture on 2026-10-27,
NOT its external deployment. First validate private pull/reconciliation end-to-end. No account, domain,
endpoint, webhook, service, billing or administrator permission is configured here.
No fact about the CEO's current Cloudflare account/domain is asserted.

## Boundaries and protocol

Separate planes: public reception is ONLY a prospective Worker `/github/push`;
private operational collection is an outbound HTTPS request by the supervisor.
Control Center, AAO API, PostgreSQL and host administration remain INTERNAL and
are never routed through this transport. The receiver has no agent tokens,
supervisor key, ledger permissions, database credentials, model or event executor.
D1 is only a transport mailbox, never AAO business state.

- POST `/github/push`: HMAC-SHA256 over exact bytes, push-only, repository allowlist,
  UUID, branch transition checks; 1 MiB body cap, including streamed bodies.
- Successful response follows the D1 write. UUID replay with identical bytes is
  idempotent; different bytes conflict. Preserve exact body and signature.
- GET `/receipts`: at most one unacknowledged original body (base64) and signature.
- POST `/receipts/{uuid}/ack`: mark acknowledged; retain the record/tombstone.
- Both private operations require HMAC-SHA256 with a DISTINCT >=32-byte secret:
  `METHOD + "\n" + PATH + "\n" + UNIX_SECONDS + "\n" + SHA256_HEX(BODY)`.
  Headers: `X-AAO-Timestamp`, `X-AAO-Signature` (lowercase hex); 300-second skew.
  WebCrypto performs signature verification. Replays are idempotent reads/acks;
  no arbitrary state mutations or execution are offered.
- `aao.push_relay.drain_one` uses HTTPS without redirects and processes the head
  in this order: (1) webhook HMAC over the exact relayed bytes, before any GitHub
  call; (2) quarantine of non-attributable heads (below); (3) a head whose signed
  local receipt already exists with identical content is only re-acked, without
  a new GitHub lookup (lost-ack recovery); (4) GitHub delivery corroboration;
  (5) durable signed receipt via the EXISTING `store_push_receipt`; (6) ACK.
  Credentials never in URLs.

A valid HMAC authenticates a payload, NOT an authorized AAO agent. Existing
supervisor chain attribution and verified GitHub App/AAO identity correlation
remain mandatory. Unknown actors, missing chains or missing identity evidence
must not gain authority. This prototype does not implement or claim that final
identity correlation, live reconciliation, W2/R1 or B-2 acceptance has passed.

`aao.github_delivery_corroboration` IMPLEMENTS the independent check against
GitHub's delivery API before a receipt is stored: configured hook and repository
ID, exact delivery GUID (list, detail and `X-GitHub-Delivery`), push event
(header and detail), immutable sender ID + login present in a caller-supplied
persisted AAO identity map, and the exact ref/before/after transition. A relay
holding the webhook secret can forge both payload and sender, so raw HMAC plus
sender.login alone is insufficient. The caller must source the `PushWebhookTrust`
(repository/hook IDs, identity map) from verified configuration and persisted AAO
identities; that provisioning, live GitHub behaviour and scheduling are NOT done
here. No new authoritative attribution source is wired into supervisor_service
by this change. Never invent historical recovery or infer identity authority
from the mailbox.

Outcomes (all fail closed; only (a) and (b) ack):
- (a) corroborated: signed receipt stored, then acked.
- (b) quarantined: HMAC-valid push from a repository outside the verified
  configuration (forks included) or from a sender without a persisted AAO
  mapping (humans, `github-actions[bot]`, dependabot, renamed logins). A
  supervisor-signed `aao.github-push-quarantine.v1` record with
  `status: PROVISIONAL`, the reason, the exact raw body and webhook signature is
  stored under `<receipts>/quarantine/`, then acked. It is never read as a push
  receipt and grants no attribution; reconcile it later under an approved procedure.
- (c) retryable `DeliveryCorroborationInconclusive` (not acked): the GUID is not
  within the bounded scan (10 pages x 100 via the Link cursor; owner/name and
  `/repositories/{id}` link forms are accepted, only the cursor is reused),
  GitHub rate limiting (429, or 403 with `X-RateLimit-Remaining: 0`/`Retry-After`;
  `retry_after` is the backoff hint for the scheduler), 5xx or network failure,
  or a not-yet-listed delivery within 600 s of the payload's `pushed_at`.
- (d) invalid (not acked, stalls the queue): bad HMAC, malformed body/list/link,
  revoked credential, GUID absent from the exhausted list after the grace period,
  or any GitHub mismatch (a forgery signal).

PENDING design, not implemented: `drain_one` takes ONE `PushWebhookTrust`, i.e.
one repository and hook. Pushes to W2 forks (which have their own repository
and hook IDs) are therefore quarantined as `repository-not-configured` and never
attributed through this path, even when listed in `REPOSITORIES_JSON`. Fork
attribution needs a trust map keyed by repository ID; until then the raw fork
deliveries are preserved in quarantine for later reconciliation.

## Persistence, failure and compromise

No expiry deletes unacknowledged data. This prototype never deletes any row,
including acknowledged rows. At 10,000 total receipts or 50 MB total bodies the
SQL trigger refuses new inserts, atomically, including concurrent writers.
Retention/ack-only compaction is future explicit work, NOT an enabled job.
A host outage leaves receipts pending remotely; restart pulls the oldest first.
An invalid oldest receipt (outcome (d)) stalls collection (fail closed); do not
silently ack or skip it. Investigate by a separately approved administrative
procedure. Because GitHub lists newest deliveries first, an inconclusive head
can drift past the scan bound or the 3-day retention and become invalid; that
also needs operator follow-up.

Compromised receiver: because it holds the webhook secret, it can forge a valid
GitHub HMAC as well as suppress/replay data or deny service. Host HMAC revalidation
alone does NOT detect that fabrication; independent GitHub corroboration is required.
Quarantine reasons are derived from relay-supplied claims that GitHub has not
checked, so a compromised receiver can divert a genuine push into quarantine
(suppression, already within this boundary). It cannot divert a push into
attribution: that path always requires GitHub corroboration.
Compromise of webhook secret can forge payloads: suspend intake, rotate the secret
in GitHub and receiver and supervisor under CEO-approved procedure; reconcile
with GitHub delivery records and AAO evidence before trusting affected intervals.
Compromise of pull secret permits reading/acking mailbox data, not forging local
supervisor signatures; revoke/rotate it, preserve local receipts, reconcile gaps.
Host compromise requires supervisor trust/key recovery, not a transport bypass.
No claim of remote exactly-once delivery or adversarial completeness is made.

Rotation is manual, not implemented automation: pause collection/ingestion;
first durably drain and verify pending receipts under the old webhook secret,
then replace webhook secret at all three participants and test a controlled push.
Do not rotate away the only verification secret with pending old receipts. Pull
secret changes require receiver+supervisor coordination; failures never trigger
an unauthenticated fallback. Preserve known local evidence and record gaps.

## Absolute cost ceiling: 0 EUR

No subscription, paid plan, usage billing, domain purchase, automatic upgrade or
fallback is authorized. A prospective operator MUST verify the chosen account
is Workers Free + D1 Free, no paid resource/billing dependency, and quotas fail
closed BEFORE seeking deployment approval. Do not request new credentials here.
The local capacity limits are NOT a substitute for checking account-level quotas.
Cloud provider exhaustion returns failure; no code upgrades the account or falls
back to a paid service. If Free cannot support this safely, stop and report.

## Local verification (no external services)

```
node --experimental-sqlite --test transport/push-relay/test.mjs
PYTHONPATH=src .venv/bin/python -m pytest -q -W error tests/test_push_relay.py tests/test_push_receipts.py
```

Node tests use the actual SQL with an in-memory SQLite adapter, NOT a deployed D1
binding. Worker runtime/D1 compatibility and real GitHub delivery are untested.
The Python test opener is in-memory; local receipt signatures use real OpenSSL.

## Intervention proposal, only after architecture/CEO approval

1. Verify Free-only eligibility and separated planes. If unavailable, stop.
2. Provision a dedicated mailbox with `schema.sql` and bind it as `DB`; Worker
   entry is `worker.mjs`. No migration touches AAO PostgreSQL.
3. Provision `GITHUB_SECRET`, `PULL_SECRET`, `REPOSITORIES_JSON` through approved
   secret/config channels. Distinct high-entropy secrets, >=32 bytes; configure
   canonical repository AND every W2 fork. Do not put secrets in source or logs.
4. Configure webhook only for push after receiver controls and data handling are
   approved. No deployment configuration file in this prototype can do this.
5. Run collector under supervisor identity with explicitly supplied secrets and
   existing private signing key. Wire scheduling/liveness separately; currently
   no service/CLI auto-discovers secrets or enables collection.
6. Prove real App push, original HMAC and identity correlation; restart/outage,
   lost ack, conflict, invalid signature, exhausted capacity and incomplete chain.
   Record SHA/evidence. Do not activate integrator or declare final acceptance.

Primary references checked during construction:
- https://docs.github.com/en/rest/repos/webhooks (delivery API is recovery, not unlimited push history)
- https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries
- https://docs.github.com/en/webhooks/testing-and-troubleshooting-webhooks/viewing-webhook-deliveries (3-day history)
- https://developers.cloudflare.com/workers/platform/limits/
- https://developers.cloudflare.com/d1/platform/pricing/
