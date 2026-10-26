# Principal authorization matrix

**Scope:** current development API and internal execution/reconciliation
operations, updated through the pending content-addressed evidence increment.
This is an engineering inventory, not a production authorization policy or
independent security review. The PostgreSQL API and its internal helpers are
not a claim of M2 acceptance.

## External HTTP operations

| Operation | Authenticated identity / authority | Project capability and transaction check | Effect and known boundary |
| --- | --- | --- | --- |
| `GET /`, `GET /health` | None | None | Static workboard shell / service status only; health reports autonomous execution disabled. |
| `POST /v1/principals/credentials`, `/v1/principals/{id}/rotate`, `/revoke` | Static `AAO_CEO_TOKEN` bearer, compared before DB transaction; enabled only when `AAO_ENV` is explicitly `development` or `test`, otherwise 503 | No project grant; lifecycle writes and audit event share a DB transaction | Development-only credential administration; no constitutional signature, multi-party confirmation, or production identity. Production administration remains unavailable. |
| `POST /v1/mandates`, `/v1/mandates/{id}/confirm`, `/v1/projects` | Static CEO bearer; enabled only when `AAO_ENV` is explicitly `development` or `test`, otherwise 503 | No project grant; mandate/project row checked or locked within transaction | Development-only draft/confirm mandate and project creation. CEO identity is not a verified constitutional actor. |
| `POST /v1/projects/{id}/grants` | Static CEO bearer | No project grant; project, active principal identity and capability-compatible principal kind are checked in the transaction; credential row is locked under `FOR SHARE` | Rejects unknown/disabled principals and Agent/Auditor capability mismatches before persisting the grant. Idempotent grant conflicts do not emit a duplicate grant-created event. |
| `DELETE /v1/projects/{id}/grants/{principal}/{capability}` | Static CEO bearer | Deletes the exact matching grant inside a DB transaction | Returns 404 if project/grant is absent; writes `grant.revoked` event atomically with deletion. Protected operations hold `FOR SHARE` on the grant row, so deletion waits for their transaction. |
| `GET /v1/projects` | Development CEO bearer or individual AGENT bearer; CEO bearer is not recognized in production | Development CEO receives all projects; other readers need unexpired `project.read`. Individual credential and project grant rows are rechecked/locked under `FOR SHARE` in the transaction. | Project list is scoped for non-CEO readers. Shared worker/reviewer tokens are not accepted by this API. Production CEO access is unavailable. |
| `GET /v1/projects/{id}/board` | Same read-principal resolver | CEO bypasses grant; others pass `require_grant(project.read)` inside transaction. Individual credential and grant rows are locked under `FOR SHARE`. | Project-scoped board read. No DB RLS/role isolation is established by this application check. |
| `GET /v1/principals/me/grants` | Individual AGENT bearer only | Rechecks caller credential under `FOR SHARE`; reads only grants matching that caller under `FOR SHARE`; computes expiry with PostgreSQL `clock_timestamp()` | Self-scoped grant inventory, including expiry/active state. It grants no authority and is not cached as an authorization decision; protected routes continue to recheck grants. |
| `GET /v1/auditors/me/grants` | Individual AUDITOR bearer only | Rechecks caller credential under `FOR SHARE`; reads only grants matching that caller under `FOR SHARE`; computes expiry with PostgreSQL `clock_timestamp()` | Auditor self-scoped grant inventory for least-privilege planning. It does not establish audit independence or grant authority; protected review/reconciliation operations continue to recheck grants. |
| `POST /v1/projects/{id}/work` | Individual AGENT bearer | `work.create`; individual credential and grant rows locked under `FOR SHARE` in transaction | Persists authenticated principal as author; ignores client `author_id`. |
| `POST /v1/projects/{id}/capability-evaluations` | Individual AGENT bearer | `work.create`; credential and grant rechecked under `FOR SHARE`; group children are locked and limited to their assigned agent | Records a non-authorizing recommendation. Non-group tasks retain the existing grant contract; an agent with `work.create` cannot assess another agent's assigned group child. |
| `POST /v1/work/{id}/admit` | Individual AGENT bearer | `work.admit`; credential and grant recheck under `FOR SHARE` | Deterministic admission call uses simulated capacity, budget, risk and emergency-stop inputs; not real resource admission. |
| `POST /v1/work/{id}/progress` | Individual AGENT bearer | `work.progress`; credential and grant recheck under `FOR SHARE` | Advances READY-to-IN_PROGRESS and IN_PROGRESS-to-IN_REVIEW. VERIFIED-to-DONE is disabled even if a legacy APPROVE row exists, until independent approval verification is available. |
| `POST /v1/work/{id}/reviews` | Individual AUDITOR bearer | `work.review`; individual AUDITOR credential and grant rows locked under `FOR SHARE`; locks work and its execution rows | Rejects the author and any principal ID in durable execution claim history. `APPROVE` fails closed with 409 because independent human identity and evidence references are not verified; it records no review and cannot set `VERIFIED`. `REJECT` may return work to `IN_PROGRESS`, including while execution is incomplete. This is only ID-level separation, not proof of independent human identity or evidence validity. |
| `POST /v1/work/{id}/stage-inert` | Individual AGENT bearer | Requires both `work.admit` and `execution.claim`; credential and grant rows locked under `FOR SHARE` | Feature-flagged staging of fixed inert payload only. No model/tool/external action. A negative integration case rejects an admitted agent without the execution capability. |

The PostgreSQL API no longer accepts shared worker/reviewer tokens. SQLite
prototype tokens are a separate path. Individual bearer authentication first
resolves identity and protected API operations recheck the credential row
inside their transaction. HTTP dependencies currently resolve the bearer
before the protected operation transaction; the authenticated request context
retains the presented token digest, which is matched again under `FOR SHARE`
inside the protected transaction. Thus a token rotated in that gap does not
match the credential row. This path is covered by transaction-level unit
checks and a disposable PostgreSQL route test that captures a context, rotates
the token before the project-list transaction, and observes denial; a fresh
context is allowed. That route test also retains the fresh context, revokes its
`project.read` grant, then observes 403 from the protected board route. This is
a concurrent test queues grant deletion first, observes the board's grant query
blocked by that revoker, then confirms deletion commits and the board returns
403. The same test retains a sequential revoke-before-route check.
The static CEO bearer is development-only and is
rejected for CEO authorization outside explicit development/test modes; this
does not establish a production CEO identity flow. See the latest evidence
register for test status.

## Internal PostgreSQL operations (not HTTP authorization boundaries)

| Operation | Identity / capability check | Transaction boundary | Known boundary |
| --- | --- | --- | --- |
| `execution_queue.claim()` / `complete()` | Individual AGENT credential; requires unexpired `execution.claim` project grant | Credential and grant are checked with `FOR SHARE`; queue/project rows are locked. | Migration 006 transfers legacy identities and drops the old registry. Lease expiry is computed and checked with PostgreSQL `clock_timestamp()`; a real database-lock-wait test covers delayed completion. Other lease/revocation schedules remain open. |
| `execution_reconciliation.reconcile()` | Active AUDITOR bearer credential resolves reviewer in-transaction; unexpired `execution.reconcile` grant; AGENT credentials denied | Locks credential, queue/project, grant, and referenced evidence rows | No HTTP endpoint. Evidence refs resolve to project-scoped append-only artifacts and bytes are re-hashed; this does not prove truth/authorship. Controlled auditor-credential revocation schedules cover both dispositions. |
| `external_effect_registry.propose()` | Active individual AGENT credential must match `worker_id`; requires `effect.propose` grant | In one transaction, locks credential, execution/project, then grant; requires active project, `RUNNING`, matching worker and lease token, and a lease not expired by DB clock | Records only; never executes. Appends `effect.proposed` journal event with proposer identity and request digest. No external adapter is enabled. |
| `external_effect_reconciliation.reject_unexecuted_proposal()` | Active AUDITOR bearer credential resolves reviewer in-transaction; unexpired `effect.reconcile` grant; AGENT credentials denied | Locks credential, effect/queue, grant, and referenced evidence rows | Evidence refs resolve to project-scoped append-only artifacts and bytes are re-hashed; this does not prove truth/authorship. Internal helper only; no external effect is executed. |

| `evidence_registry.register_evidence()` / `read_evidence()` | Submit: active individual AGENT matching submitter plus `evidence.submit`; read: active individual AUDITOR plus `execution.reconcile` or `effect.reconcile` | Credential and matching project grant are checked under row lock in the transaction; artifact bytes are re-hashed | Internal Python operations, no HTTP interface. Artifacts/references are bounded (1 MiB each, 32 refs), project-scoped, and row UPDATE/DELETE/TRUNCATE are denied by triggers. A DB owner can disable triggers; integrity does not establish truth/authorship or human identity. |

## Cross-cutting gaps and test status

- API, queue and reconciliation authorization checks hold matching grant
  tuples under `FOR SHARE`; CEO grant deletion serializes behind in-flight
  protected transactions. PostgreSQL schedules cover an HTTP work-creation
  transaction, queue claim, and queue completion each holding authorization
  while grant deletion waits. Queue completion has also been observed holding
  the AGENT credential row while credential revocation waits; after the
  operation commits, the revocation succeeds and subsequent completion is
  denied. A separate AUDITOR auth/revocation schedule and AGENT auth/rotation
  schedule exercise credential row locks. These are selected controlled lock
  schedules; a queue-claim/credential-revocation schedule now also observes
  credential revocation wait until claim commits, then denies later claims.
  Reconciliation's `MARK_FAILED` and `RETRY_CONFIRMED_SAFE` dispositions have
  each been observed committing before an in-flight auditor credential
  revocation; the revoked auditor is denied on a subsequent attempt. Effect
  proposal now requires the worker's
  active credential, explicit `effect.propose` grant and live lease. Three
  local focused reruns exercised a controlled execution-row-lock schedule: the
  test observed proposal blocked while completion competed; completion
  succeeded, and proposal either committed before it or was denied after
  completion. This is selected controlled coverage, not exhaustive or
  adversarial race coverage.
- Effect proposal now has controlled disposable-PostgreSQL schedules against
  both AGENT credential revocation and `effect.propose` grant deletion. In each
  tested ordering, proposal locks authorization and waits later in its
  transaction, revocation is observed blocked by the proposal PID, proposal
  commits first, revocation succeeds, and a subsequent proposal is denied.
  Inverse schedules observe revocation queued first, then verify proposal waits
  on that transaction, which commits before the proposal is denied. These are
  controlled schedules, not exhaustive hostile concurrency coverage.
- Sequential credential revocation tests and unit mocks that assert SQL text
  do not prove real PostgreSQL lock behavior. Several real lock schedules now
  cover work creation, queue claim/completion against grant deletion, queue
  completion against credential revocation, and both reconciliation grant
  revocation paths in selected orderings. Real review-route schedules also
  observe an authorized `REJECT` holding its AUDITOR credential and
  `work.review` grant while CEO revocation waits; after the review commits and
  revocation succeeds, subsequent authorization is denied. Other business
  writes, additional dispositions, and hostile schedules remain untested.
- A separate stale-context test supplies the review route with a request
  authenticated before revocation. Revoking either the AUDITOR credential or
  its `work.review` grant before the route transaction causes the in-transaction
  check to return 403 without inserting a review. This complements, but does
  not replace, the selected operation-first lock schedules above.
- The full local suite at `a2791349e6000bec56d95cfe0ede587bb631573b` has 66
  tests, including the HTTP token-rotation gap check, grant-row, auditor
  credential-lock, and completion-after-lease-expiry-during-row-lock-wait
  coverage, AGENT authentication/rotation, and selected protected-operation
  revocation schedules. Three
  controlled races between completion and quarantine after
  expiry also finish in `UNCERTAIN`; this is not a broad adversarial schedule
  proof. Proposal and retry do not form a meaningful valid-operation race
  because proposals require a live RUNNING lease while retry requires
  UNCERTAIN; a prior test purported to exercise that schedule and has been
  replaced with proposal/completion coverage. A cold PostgreSQL
  restart has been manually verified for one expired lease; broad restart and
  crash-recovery schedules remain open.
- GitHub CI configures a fresh disposable PostgreSQL service and runs the
  guarded integration suite; runs `39258084851`, `39258576394`, and
  `39258935861` passed on code SHAs `424016daabda4f2cb0cd337be449b71d687d4cac`,
  `22f7310822c2ca3bfe59b8e2ccbb9d8dbc856b0d`, and
  `9247f7a3e8708efcbddce6652ab5f56d13bb1aa4`, respectively. Current exact local results and
  prior candidate SHA-specific CI runs are recorded in the evidence register;
  this is not independent review or M2 acceptance.
- Grant expiry uses `clock_timestamp()` when the locked authorization query is
  evaluated, avoiding PostgreSQL transaction-start `now()` semantics. This
  does not itself prove every long-running operation stops exactly at expiry;
  authorization is held through transaction end and that contract needs
  separate review.
- External execution remains inert. No real model, tool, external effect,
  production identity, or autonomous operation is authorized by this matrix.

## Source map

- HTTP routes and auth helpers: `src/aao/work_management_api.py`
- Credential resolution: `src/aao/principal_credentials.py`
- Reconciliation credentials are verified and locked via
  `authenticate_in_transaction()` in the operation's database transaction.
- Execution claims/completion: `src/aao/execution_queue.py`
- Legacy worker rows are transferred by `db/postgres/006_unified_execution_identity.sql`; no legacy runtime verifier remains.
- Execution reconciliation: `src/aao/execution_reconciliation.py`
- Effect proposal/reconciliation: `src/aao/external_effect_registry.py`,
  `src/aao/external_effect_reconciliation.py`
- Relevant integration suites: `tests/test_project_workflow_integration.py`,
  `tests/test_execution_leases_integration.py`,
  `tests/test_execution_reconciliation_integration.py`,
  `tests/test_principal_credential_lifecycle_integration.py`
