# Threat model: W2 publisher self-rotation

## Decision and scope

The PM must not issue, receive, relay, or log an implementer's bearer. Each
publisher process rotates only its own existing credential, authenticated by
that credential, through the AAO API. The API restricts the caller to an
existing `aao-publisher-pm-*` or `aao-publisher-impl-*` AGENT principal with
exactly the two live W2 grants on the uniquely active Self Development project.
Rotation can renew those grants for at most eight hours; it cannot create a
principal, change its identity, or add a grant. This avoids adding delegated
issuance authority to the PM.

## Assets and trust boundaries

- Bearers and their digests; target account's `/run/user/<uid>` directory; the
  two W2 grant rows; audit events.
- The target's role-owned helper and AAO API are trusted to hold the target
  bearer. The PM, CEO process, logs, command line, environment, and other role
  accounts are outside that bearer boundary.
- The helper may pass the bearer only in the `X-Agent-Token` HTTP header to the
  loopback API. A newly generated bearer is returned only to that same target
  helper, staged in a `0600` file, confirmed, then atomically installed.

## Threats and controls

| Threat | Control / evidence required |
|---|---|
| PM or logs disclose implementer bearer | No PM endpoint returns it; target helper calls self-rotation. Assert absence from PM responses, stdout/stderr, argv and environment. |
| Cross-role rotation or grant escalation | API validates principal namespace, exact active grant set and project under row locks; integration tests reject wrong role, extra/missing grants and wrong project. |
| Crash or API failure strands the target | Two-phase pending token (10-minute expiry); stage locally before confirm; retain staged token if confirm succeeded but final replacement failed, so next run can recover. Test rollback and recovery paths. |
| Replay or pending-token misuse | Pending token authenticates only the confirmation endpoint, expires, and is consumed transactionally. Test expired and replayed confirmation. |
| Symlink, permissive file, or wrong account | Helper requires the expected Linux account, private runtime directory, regular no-follow token file and `0600` mode; atomic replacement in the same directory. |

## Limits

This flow rotates already provisioned principals; initial principal issuance and
installation remain a separately authorized bootstrap. A stolen active target
token can rotate itself and deny service to its former holder, but gains no
additional grants; the audit event makes the action visible. No production
credentials, host deployment, or service activation are in scope. End-to-end
claims require tests against an explicitly disposable PostgreSQL database.
