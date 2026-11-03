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
   only the fixed account, token-kind and `check|install|verify|remove|replace`
   allowlist, then calls `/usr/sbin/runuser` and the root-installed fixed
   installer with a minimal environment. Configure sudoers for only the
   installed wrapper executable, for example:
   `aao-pm ALL=(root) NOPASSWD: /usr/local/libexec/aao/selfdev_role_token_helper.py *`.
   The `*` is limited by the wrapper's strict account/token/operation allowlist;
   do not allow `/usr/bin/python3` itself, since that would permit arbitrary
   root Python code. The wrapper's fixed `#!/usr/bin/python3` shebang selects
   the interpreter internally. Do not grant arbitrary `sudo`, shells,
   interpreters, installer or commands. Validate the
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

## Atomic token replacement (`replace`)

`install` still refuses to overwrite an existing token file, and `remove`
still requires the old token on stdin. For unattended renewal of a cycle token
file, the wrapper also accepts `--operation replace`, with exactly the same
account/token-kind allowlist as `install`: `aao-impl-codex` with
`selfdev-implementer` and `aao-auditor` with `selfdev-reviewer`. The installer
itself rejects `--replace` for the `publisher` and `pm` token kinds. Running as
the role account, `install_publisher_token_for_role.py --replace`:

1. Reads the new token from stdin only; it is never written to argv, the
   environment, stdout or stderr.
2. Opens the runtime directory with `O_NOFOLLOW` and refuses unless it is owned
   by the role and mode `0700`. All following steps are relative to that
   directory descriptor.
3. Takes an exclusive advisory `flock` on the stable
   `.<token-name>.lock` file (role-owned, regular, single-link, mode `0600`).
   The lock is held through stale-temp cleanup, rename, directory fsync and
   post-write verification. It is intentionally persistent; do not delete it
   during normal cleanup. This serializes replacement calls for one token path
   and prevents stale-temp cleanup from unlinking another call's active temp.
   The lifecycle caller must also serialize the broader issue/install/revoke
   sequence with its own cycle lock; the installer lock covers replacement,
   not API issuance or cycle state transitions.
4. Removes leftover `.<token-name>.*.tmp` files that a crashed earlier run
   left for the same token name, while holding that lock.
5. If the target exists, refuses unless it is a regular, single-link file
   owned by the role with mode `0600`. Symlinks, FIFOs and directories are
   refused. It also refuses if the new token equals the installed one; this
   comparison happens in memory only.
6. Creates `.<token-name>.<random>.tmp` with
   `O_CREAT|O_EXCL|O_NOFOLLOW` and mode `0600`, writes the token, then fsyncs
   it. It renames the file over the target with `os.replace` and fsyncs the
   directory.
7. Checks the result: a regular, single-link, role-owned `0600` file whose
   SHA-256 matches the new token.

If the target is absent, `replace` creates it the same way, so it acts like
`install`. If the process crashes before the rename, the previous file stays
intact. If it crashes after the rename, the new file is complete. A partial
target file is never left behind. Any leftover temp file is removed on the
next `replace`. Exit code `3` means rename completed but directory fsync or
post-write verification failed; the target may already contain the new token.
The caller must not revoke the new principal or assume the old file remains in
place. It must inspect/verify the target through the role helper and reconcile
the lifecycle state without printing or logging token material. Other
non-zero results from before rename leave the prior target unchanged.

**One-time host reinstall required.** The root-owned copies in
`/usr/local/libexec/aao` do not update themselves. Until a host administrator
reinstalls them from the reviewed commit, `--operation replace` returns exit
code 2. Using the ownership and mode rules from step 3 of *One-time
authorization and host setup*, the administrator must replace exactly these
two files:

- `scripts/selfdev_role_token_helper.py` →
  `/usr/local/libexec/aao/selfdev_role_token_helper.py` (root:root, `0755`)
- `scripts/install_publisher_token_for_role.py` →
  `/usr/local/libexec/aao/install_publisher_token_for_role.py`
  (root:root, `0644`)

The sudoers rule does not change. Do not reinstall until the change has passed
independent review (GOV-REV-001).

## Lifecycle boundary

The API review route can advance work only after it validates the linked
candidate SHA, successful execution, evidence, absence of veto, and reviewer /
author / claimant separation. This is an application lifecycle gate only. It
does not establish truthful evidence, independent review, promotion
conformity, or permission to merge or publish. Formal review remains subject to
the separate GOV-REV-001 process.
