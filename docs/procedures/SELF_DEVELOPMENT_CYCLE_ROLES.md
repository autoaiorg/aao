# Self Development cycle roles

The PM coordinator may request one fixed implementer/reviewer pair for the
active `AAO — Self Development` project. This removes routine CEO-token use;
it does **not** delegate general credential issuance. A CEO must first grant
the PM principal both `work.coordinate` and
`credential.issue_selfdev_cycle_roles` on that project. The latter grant must
have an explicit expiry no more than 30 days away. The API rejects requests
from any other principal, project, or inactive/ambiguous Self Development
project.

## Fixed scope and lifetime

Each request creates exactly two newly named principals:

| Role | Linux account | Grants |
|---|---|---|
| Implementer (`AGENT`) | `aao-impl-codex` | `project.read`, `work.create`, `work.admit`, `work.progress`, `execution.claim`, `code.propose`, `evidence.submit` |
| Lifecycle reviewer (`AUDITOR`) | `aao-auditor` | `work.review` |

Both credentials and grants expire at one server-calculated timestamp, at
most two hours after issuance. Authentication rejects an expired credential
even while its database row remains enabled. Expiry does not delete the row or
token file; it makes the credential unusable, while normal cycle cleanup
revokes the pair and removes files. The API never accepts a caller-selected
principal ID, kind, grant, project name, or expiry timestamp. The reviewer is not an independent
GOV-REV-001 auditor. These roles cannot publish code or change arbitrary work
status, and this endpoint does not activate a runner, provider, PM service, or
integrator.

The endpoint `POST /v1/projects/{project_id}/selfdev-cycle-roles` returns each
new secret once. Secrets are not written to events or logs. The endpoint
`DELETE /v1/projects/{project_id}/selfdev-cycle-roles/{cycle_id}` disables only
the two principals generated for that cycle, after checking their exact kind
and grant set. It clears pending self-rotation state and retains grant rows as
inert audit history. Issuance and revocation each create audit events naming
the PM issuer, cycle, principal, grants/expiry as applicable; no token or
digest is recorded.

## One-time authorization and host setup

This is a one-time administrative enablement, not a routine cycle step:

1. Verify the active PM coordinator principal and the exact Self Development
   project UUID through the trusted administration path.
2. Grant that PM principal `credential.issue_selfdev_cycle_roles` on that
   project with an explicit expiry of at most 30 days. It also needs the
   existing `work.coordinate` grant. Do not give this capability to
   implementers, reviewers, or publisher principals.
3. Copy the exact committed
   `scripts/selfdev_role_token_helper.py` to
   `/usr/local/libexec/aao/selfdev_role_token_helper.py` and the exact
   `scripts/install_publisher_token_for_role.py` to
   `/usr/local/libexec/aao/install_publisher_token_for_role.py`. Both files
   must be root-owned; use mode `0755` for the wrapper and `0644` for the
   installer. `/usr/local/libexec/aao` and every ancestor must be root-owned
   and not group/world writable. Do **not** execute the wrapper, interpreter,
   or installer from `/srv/aao`: `/srv/aao` ancestors are owned by `aao-trust`,
   which can replace even root-owned children. The installed wrapper has the
   fixed `#!/usr/bin/python3` interpreter, validates that interpreter and every
   path ancestor, and never runs code from the frozen tree as root. It accepts
   only the fixed account, token-kind and `check|install|verify|remove`
   allowlist, then calls `/usr/sbin/runuser` and the root-installed fixed
   installer with a minimal environment. Configure sudoers for only `/usr/bin/python3` with this exact wrapper path;
   both invoking scripts use that fixed root-owned interpreter and wrapper, and
   the wrapper argument parser enforces the allowlist. Do not grant
   arbitrary `sudo`, shells, interpreters, installer or commands. Validate the
   rule with `visudo -cf` before enabling the PM workflow.
4. Keep the PM token at `/run/user/<aao-pm uid>/aao-pm.token`, owned by
   `aao-pm`, regular, single-link, mode `0600`; the runtime directory must be
   private. The token is sent only to the loopback API and never to GitHub.

If the PM capability expires, a CEO must renew only that scoped grant. The PM
cannot grant capabilities, issue arbitrary credentials, extend its own issuer
grant, or use the API to modify the project workflow outside its existing
grants.

## Request and recovery

The coordinator invokes the provisioner as `aao-pm` from the approved frozen
tree:

```sh
sudo -u aao-pm -H env XDG_RUNTIME_DIR=/run/user/<uid> \
  /srv/aao/frozen/aao-pm/venv/bin/python \
  /srv/aao/frozen/aao-pm/tree/scripts/request_selfdev_cycle_roles.py \
  --project-id '<Self Development project UUID>'
```

The default is the maximum two-hour lifetime; a shorter positive value may be
selected with `--lifetime-seconds`. The script reads the PM token from its
private runtime file, preflights both role-owned token destinations, requests
the fixed pair, and installs/verifies each token via stdin into that account's
own runtime directory. It prints principal IDs and the expiry, never tokens.
It does not create or admit work items, nor set `VERIFIED` status.

The request includes a client-generated cycle ID. That ID is an idempotency
boundary, not a replay mechanism: a second POST for an existing role ID returns
HTTP 409 and never overwrites credentials. Role inserts, grants and issue
events share one transaction; conflict on the second role rolls back the first
role too. DELETE for the exact pair is idempotent: the first call disables both
roles and records two revoke events; later calls return `already_revoked: true`
and add no events. A malformed or expanded role/grant set returns HTTP 409.

If the API response is lost
or an install/verification step fails, the script uses that known ID to remove
any matching installed files and call the scoped cycle-revoke endpoint. If
cleanup reports incomplete, stop cycle execution and retry the same cycle
revoke as `aao-pm`; remove any remaining matching token files using the
role-owned installer. A missing response must not be treated as successful
issuance. Do not manually create a role or broaden grants to recover.

At normal cycle completion or abandonment, immediately revoke the cycle with
the same scoped endpoint and remove the role token files. Credential expiry
independently prevents authentication after the deadline; grant expiry removes
project authorization. Neither expiry physically deletes rows or files.
Reboot also removes `/run/user` files, but still requires API revocation to
disable the credentials. Audit event evidence and disabled credential state
must be checked before considering cleanup complete.

## Lifecycle boundary

The API review route can advance work only after it validates the linked
candidate SHA, successful execution, evidence, absence of veto, and reviewer /
author / claimant separation. This is an application lifecycle gate only. It
does not establish truthful evidence, independent review, promotion
conformity, or permission to merge or publish. Formal review remains subject to
the separate GOV-REV-001 process.
