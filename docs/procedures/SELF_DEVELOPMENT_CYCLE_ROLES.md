# Self Development lifecycle roles (operator provisioning)

This procedure is an explicitly operator-invoked recovery path for the
Self Development implementer and API lifecycle reviewer. It does not provision
a publisher. The implementer receives only `project.read`, `work.create`,
`work.admit`, `work.progress`, `execution.claim`, `code.propose`, and
`evidence.submit`. The separate `aao-auditor` Linux account receives only
`work.review`. Both principals are newly named, separate, and expire at the
CEO-selected timestamp, no more than eight hours after invocation.

## Boundary: API review is not formal independent audit

The review endpoint can advance a work item to API-level `VERIFIED` only after
it validates content-addressed evidence, a successful execution linked to the
candidate SHA, no active veto, and no running/uncertain execution. The reviewer
must be distinct from the author and every principal in durable execution
claim history. This is a lifecycle gate only; it does not establish truthful
evidence, human identity, GOV-REV-001 auditor independence, promotion
conformity, or permission to merge/publish. The Linux reviewer credential is
not a formal GOV-REV-001 audit credential. Formal audit still requires the
separate policy/key custody and trusted auditor revision described in
`INDEPENDENT_AUDIT_SERVICE.md`.

## Preconditions and operator command

Before running the provisioner, an operator must establish that:

1. The local AAO API is running on loopback and serves the current approved
   code/migration set. The script refuses non-loopback API URLs.
2. A worker runner/provider for `aao-impl-codex` is already intentionally
   configured and authorized. Credential provisioning does not enable a
   provider, start a worker, or create a work item.
3. The selected Self Development project is active and matches the supplied
   project UUID.
4. Both Linux accounts and their private `/run/user/<uid>` runtime directories
   exist; their UIDs differ from one another and the operator. The role helper
   validates ownership and mode `0700`.
5. The exact role-token files do not already exist. The installer refuses to
   overwrite them.

From a terminal with the current approved checkout/environment, invoke:

```sh
python scripts/provision_selfdev_cycle_roles.py \
  --project-id '<Self Development project UUID>' \
  --expires-at "$(date -u -d '+2 hours' '+%Y-%m-%dT%H:%M:%S+00:00')"
```

The command computes a UTC expiry two hours ahead; choose any expiry in the
future and within eight hours. The operator enters the CEO token at the
hidden prompt. Do not pass it in an argument or environment variable, and do
not paste it into chat. The command creates exactly one AGENT and one AUDITOR
principal, grants/readbacks the fixed capabilities, installs each credential
over stdin into that role's own runtime directory with mode `0600`, and
verifies it. On any failure it attempts to remove installed token files and
revoke every principal created in that invocation. If cleanup is reported
incomplete, the operator must revoke the named principal(s) through the CEO
channel and remove only the matching role-owned token file.

The token paths are `/run/user/<uid>/aao-self-development-agent.token` for
`aao-impl-codex` and
`/run/user/<uid>/aao-self-development-reviewer.token` for `aao-auditor`.
They are ephemeral; reboot removes them. This script does not activate the PM
service, provider, integrator, publisher, or any external effect.

## Can the current lifecycle produce an API-level candidate?

The code path exists: an admitted work item can be progressed, claimed and
completed by an authorized worker; a candidate can be proposed and linked
content-addressed evidence submitted; a distinct AUDITOR can review it. The
API's review route checks the successful execution/SHA, author and claimant
separation, vetoes and uncertain executions before setting `VERIFIED`.

This does **not** mean a candidate can be generated in the current live state.
The operator must first restore the expired role grants using the script, and
the implementer runner/provider must already be operational and authorized.
No provisioner can compensate for an absent runner/provider, and this procedure
does not create tasks or edit status directly. If no suitable existing work
item is in an executable state, the normal authorized API/PM workflow must
create/admit one; that is not a database edit. A formal GOV-REV-001 audit and
any promotion/publication remain independent gates after API-level `VERIFIED`.
