# PostgreSQL development runtime (M1)

AAO now includes a **separate, actually PostgreSQL-backed API** at
`aao.work_management_api:app`. The original `aao.sqlite_api:app` remains SQLite-based.

This is a deliberate incremental cutover. It is not a transparent or complete
migration: use the PostgreSQL endpoint only for development mandates, projects,
grants, work creation and work admission. No real agents or external effects.

## Isolated setup

Requires a fresh, dedicated development PostgreSQL database. Apply the
schema migrations once, in order; migration 006 consolidates legacy worker
identities and migration 007 fences old leases across project-state changes.
Do not run migrations against production or a database with unreviewed data.
The migration ledger is `schema_migrations`; inspect it before upgrading and
never rerun an applied migration. The scripts are one-shot, not a general
schema-repair or rollback tool. If an interrupted migration leaves ambiguous
state, stop and inspect the database rather than rerunning it blindly.

Migration 031 installs the fencing schema but intentionally does not bind an
agent identity to a host. Before enabling a worker, an operator must register
its exact principal and host with `aao-ops register-host-worker --worker-id
<principal-id> --host-id <host-id>`. Claims fail closed until that explicit
binding exists. Fence the old host before registering the worker on a new host;
the unique active-binding constraint refuses an un-fenced reassignment.

## Unified Schema Migration Engine (Single Source of Truth)

AAO now incorporates a unified, atomic, and lock-protected migration subsystem
at `src/aao/migrator.py` (CLI entrypoints: `aao-migrate` or `python scripts/migrate.py`).
Manual shell loops are deprecated; both CI, host bootstrap, and day-to-day operations
consume this identical engine.

### Migration Management:
```sh
# Install dependencies
python -m pip install -e '.[postgres]'

# Check migration status (applied vs pending)
python scripts/migrate.py --status

# Apply pending migrations (001 to 031) with advisory locks and integrity verification
python scripts/migrate.py --apply

# Verify that all migrations in db/postgres/ are applied with intact SHA-256 checksums
python scripts/migrate.py --verify
```

### Full Migration Catalog (001 to 031):
The current canonical catalog comprises 31 versioned migrations in `db/postgres/`:
- `001_foundation`: Core tables (`schema_migrations`, `mandates`, `projects`, `principals`, `events`).
- `002_dev_identity`: Relaxed UUID identities to text development identities.
- `003_execution`: Execution queue and status lifecycle.
- `004_execution_guards`: Constraints preventing unauthorized state transitions.
- `005_principal_credentials`: Credential registry storing SHA-256 token digests.
- `006_unified_execution_identity`: Consolidates legacy worker identities into `principal_credentials`.
- `007_fence_leases_across_project_state_changes`: Project state triggers and fence generation numbers.
- `008_content_addressed_evidence`: Content-addressed SHA-256 evidence artifact storage.
- `009_prevent_evidence_truncation`: Guards ensuring complete immutable evidence recording.
- `010_capability_registry`: Versioned, project-local capability definitions and contracts.
- `011_sha_bound_reviews_and_veto`: SHA-bound reviews and independent auditor veto mechanisms.
- `012_patch_proposals`: Code patch proposals, base SHA binding, and validation records.
- `013_work_description`: Structured work item description and task criteria.
- `014_execution_retry`: Partial index `ux_execution_queue_active_work` supporting execution retries.
- `015_organization_profiles`: Canonical organizational units and member profiles (`/v1/organization`).
- `016_project_conversations`: CEO conversation session and turn tracking.
- `017_ceo_browser_sessions`: HTTP-only `__Host-aao_ceo_session` cookies and CSRF digests.
- `018_conversation_provider_metadata`: Metadata recording model and provider details per conversation.
- `019_project_conversation_turns`: Structured turn messages and assistant responses.
- `020_persistent_work_groups`: Multi-task persistent work group hierarchy.
- `021_conversation_turn_leases`: Turn lease timeout and heartbeat leases.
- `022_work_item_assignments`: Work item assignment to specific agent principals.
- `023_work_group_consolidations`: Aggregation and consolidation of work group child tasks.
- `024_work_group_partial_reports`: Intermediate progress reporting for complex task trees.
- `025_work_item_due_dates`: Scheduling, deadlines, and target completion timestamps.
- `026_capability_feedback_proposals`: Feedback submission on registered capabilities.
- `027_capability_feedback_review`: Review and dispositioning of capability feedback proposals.
- `028_capability_feedback_version_link`: Version linking between feedback proposals and capability revisions.
- `029_organization_profile_competencies`: Agent skills, competencies, and specialization tags.
- `030_conversation_work_group_results`: Grounding conversation outcomes to persisted work group executions.
- `031_host_worker_fencing`: Versioned host-worker binding registry, unique active worker binding, and execution claim fencing epoch.

For an existing database, apply only migrations absent from
`schema_migrations`, preserving the same order. The LIVE organization
projection (`GET /v1/organization`) requires
`015_organization_profiles.sql`, which creates the persisted organization
units and profiles used by that route. If that screen returns HTTP 500, inspect
the API traceback and `schema_migrations`; apply migration 015 only if it is
absent and the database is the explicitly designated development database.
Do not treat a missing-table error as permission to run migrations on an
unknown or production database. After `014_execution_retry`,
check that `execution_queue` no longer has the `execution_queue_work_id_key`
unique constraint and has the partial index `ux_execution_queue_active_work`
(`\d execution_queue`); otherwise a failed task cannot be re-run. Migration 007 is forward-only
after deployment: preserve queue/journal evidence and correct defects with a
new migration instead of dropping its generation columns or trigger. Recreate
only explicitly disposable databases when a clean migration replay is needed.
PostgreSQL work and review routes require individually issued credentials.
Use the CEO-authenticated `/v1/principals/credentials` endpoint to provision
an `AGENT` or `AUDITOR`, then send its one-time returned token as
`X-Agent-Token` or `X-Auditor-Token`. Grant the resulting principal ID only
the project capabilities it needs. `AAO_WORK_TOKEN` and `AAO_REVIEW_TOKEN`
are SQLite-prototype settings and are not accepted by this PostgreSQL API.

**Do not expose port 8001 beyond loopback.** Both secrets are development
credentials, not a production identity system. PostgreSQL permissions,
RLS, authenticated agent IDs, independent reviews and true resource/risk checks
are not yet established. `work.admit` presently uses development-only
assumptions for low risk and sufficient resources; it does not authorize
real execution.

The original schema includes UUID principals and FK constraints. The second
migration relaxes those to text development identities. Do not reuse these
migrations unchanged for production.

## Review and work progression (incremental)

The PostgreSQL service now exposes `POST /v1/work/{id}/progress` and
`POST /v1/work/{id}/reviews`. Progression follows
`READY -> IN_PROGRESS -> IN_REVIEW -> VERIFIED -> DONE`.
Only the review endpoint can reach VERIFIED. A rejected review returns the
task to IN_PROGRESS; completion requires an accepted review record.
Review identity derives from an individually issued AUDITOR credential, not
from the request body. The work author is bound to the authenticated AGENT
principal rather than trusting a caller-supplied author ID.

Grant checks use exact principal/project/capability matching and honor
`expires_at`. Test coverage is included for a disposable PostgreSQL database.

**Security limits:** development credentials still authenticate entire shared
roles; all approved evidence strings are references, not cryptographically
verified artifacts. No OAuth/OIDC identities, signed approvals, reviewer
qualification/independence assessment, project-scoped read authorization,
migration/rollback system, worker integration, dynamic risk assessment or
production-grade audit integrity exists yet. AAO remains development-only.


## Increment: PostgreSQL workboard on the same origin

The PostgreSQL API now serves the **read-only** workboard at its root
(`http://127.0.0.1:8001/`). It fetches `/v1/projects` and each
`/v1/projects/{id}/board` from the **same PostgreSQL API**, not from
the SQLite API on port 8000. No CORS proxy and no data synchronization
between SQLite and PostgreSQL is involved.

Project reads continue to require the development CEO token. On an
initial 403, the browser prompts for the development CEO token and holds
it only in the current tab's JavaScript memory, not localStorage or URL.
This is a **local development workflow only**; entering privileged tokens
in browser prompts is not an acceptable production authentication method.

SQLite remains available separately at port 8000 for backward inspection,
but it is no longer required to view the PostgreSQL workboard. The runtime
is **not fully unified**: CEO/project auth, work submission, effects,
and lifecycle still need a single hardened PostgreSQL application.

A test was added to verify same-origin page delivery and fail-closed
project listing without valid CEO credentials. It has not yet been run
against the operator's PostgreSQL instance.


## Project-scoped reader integration

The PostgreSQL development API accepts either the configured CEO token or an
individually issued AGENT credential on project and board reads. The CEO
development credential can see all projects; the AGENT identity sees only projects with
an explicit unexpired `project.read` grant, enforced for both listing and
direct board URLs. Ungranted project IDs cannot be read with the worker token.

This **does not** implement strong identity authentication: there is still one
separate AGENT principal and the browser presently prompts only for the CEO
credential. Production read isolation requires distinct principals,
role separation, server-enforced session identity, least-privilege database
roles and adversarial security review.

An isolated integration regression test demonstrates worker visibility for
one granted project and denial for another. The current full PostgreSQL suite
was run against the explicitly disposable local test database; see the
evidence register for the exact source checkpoint and outcomes.
