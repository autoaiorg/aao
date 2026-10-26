# M2 — Uncertain execution reconciliation

An execution whose lease expires is quarantined in `UNCERTAIN`.
`execution_reconciliation.reconcile()` allows two dispositions only:
`MARK_FAILED` or `RETRY_CONFIRMED_SAFE`. It never invokes a worker or tool.

The quarantine transition is a database operation, not a recovery policy. The
opt-in `scripts/run_execution_lease_recovery_worker.py` invokes it once by
default, or polls it with `--watch`; run it under a service identity that has
the same PostgreSQL access as the existing queue service. It only marks expired
leases `UNCERTAIN` and writes the existing journal/event/escalation records. It
does not retry or reassign work. The worker is not installed or enabled by this
change; deployment must explicitly add and operate it. A PostgreSQL outage
returns a failure in one-shot mode, and watch mode reports only the exception
type (not connection details) before continuing to poll.

Migration `007_fence_leases_across_project_state_changes` binds each newly
claimed lease to the project's state generation. Any actual state transition,
including pause followed by resume, invalidates the prior lease for completion
and effect proposal. The stale row remains `RUNNING` until explicit expiry
quarantine; retry still requires independent reconciliation. Migration 007 is
forward-only after deployment so execution and journal evidence is preserved;
use a new corrective migration rather than removing the fence.

The reviewer must present an active individual `AUDITOR` credential and have
an unexpired project-scoped `execution.reconcile` grant; the reviewer ID is
derived from that credential inside the same transaction. AGENT credentials
are rejected. The same principal ID as the former execution worker is rejected,
but principal-ID separation is not proof of distinct human identity. Evidence
references must resolve to project-scoped, append-only artifacts whose bytes
are re-hashed during reconciliation. This establishes stored-byte integrity,
not the truth of the content, its authorship, or independent review. There is
no HTTP upload/read endpoint. `evidence_registry.read_evidence()` permits an
individually authenticated auditor with an applicable project reconciliation
grant to inspect bytes via the internal Python interface; this is not a human
identity or production access system.
Retry is refused when the project is paused or cancelled, or when any external
effect exists except one explicitly rejected. That restriction errs on the
side of refusing potentially unsafe duplicate effects.

An external-effect proposal is a ledger record only. `propose()` now requires
an active individual AGENT credential matching the current worker, the
project-scoped `effect.propose` grant, an active project, and the matching
unexpired lease token on a `RUNNING` execution. The credential, execution,
project, and grant checks and proposal+journal writes occur in one transaction.
This does not authorize or execute any external action; no effect adapter is
enabled.

**Important caveats:** the function remains intentionally **not exposed as an
HTTP endpoint**. A caller with direct database/code execution privileges can
bypass this Python policy; database roles/permissions must also be secured.
Disposable-PostgreSQL tests now cover both controlled grant-deletion orderings
for execution reconciliation (`MARK_FAILED`) and effect-proposal rejection,
and both execution-reconciliation dispositions against auditor credential
revocation. These schedules do not prove exhaustive/adversarial concurrency,
human auditor independence, or evidence integrity. Tests of database-level
reconciliation require an isolated PostgreSQL instance.

## Next gates
- Controlled auditor credential-revocation schedules cover both
  `MARK_FAILED` and `RETRY_CONFIRMED_SAFE`. Both grant-deletion orderings have
  selected tests for `execution.reconcile` (`MARK_FAILED`) and
  `effect.reconcile`; broaden adversarial and repeated schedules as warranted.
- Proposal/rejection lock-order tests and effect-proposal credential/grant
  revocation schedules cover selected controlled orderings. Broader adversarial
  schedules remain open.
- Evidence truth/authorship, human auditor identity, and database-owner
  protection against disabling mutation/truncation triggers; no signed
  disposition exists yet.
- Recovery of paused/running work and explicit in-flight effects reconciliation.
- Repeated crash/credential rotation and concurrent-worker integration tests.

Effect rejection now locks the execution/project before locking the effect row,
matching proposal replay's execution-before-effect order. Idempotent replay of a
rejected effect fails closed rather than returning it as an active proposal.
This reduces a plausible lock-order inversion; no prior deadlock was reproduced.
