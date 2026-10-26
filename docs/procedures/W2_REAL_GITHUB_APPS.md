# W2 real GitHub Apps exercise — CEO runbook

**Purpose:** exercise the production identity path for one already-approved AAO candidate, without using the CEO's `gh` session. This is a construction/acceptance exercise, not an R1 integration or permission to merge.

## Construction state

The code path exists in `scripts/publish_candidate.py` and `src/aao/pr_publisher.py`. `scripts/provision_w2_publishers.py` now provides a CEO-invoked provisioning path for two distinct AGENT principals, each with only `project.read` and expiring `code.publish` grants on the active `AAO — Self Development` project. It asks for the CEO token without echo, uses `sudo -u` to preflight and install each token through stdin into that role's private runtime, refuses overwrite, verifies mode `0600`, and revokes/cleans up partial provisioning where possible. It does not print or persist the publisher tokens itself.

Do not use the legacy `scripts/self_development_cycle.py setup` publisher token for W2: it creates one publisher identity in the invoking user's runtime and cannot preserve the required split attribution.

This provisioning script has only local unit-test coverage; it has not been executed against the host API or accounts. W2 remains unexercised until the CEO runs it, then completes the push/open steps below and verifies distinct principals in canonical project activity. Never copy one token to both accounts and do not create grants outside the active Self Development project.

### Provision the two role-scoped credentials

From the AAO checkout, with the API reachable on loopback and both role runtime sessions active:

```bash
PROJECT_ID='<active AAO Self Development project UUID>'
AAO_ROOT='<clean deployed AAO checkout>'
PYTHON='<Python executable accessible to the CEO and both role accounts>'

"$PYTHON" "$AAO_ROOT/scripts/provision_w2_publishers.py" \
  --project-id "$PROJECT_ID" --api http://127.0.0.1:8001 --python "$PYTHON"
```

The command prompts for the CEO token without echo and invokes `sudo` for each Linux account. The CEO must verify the project UUID before running it. It stops if the project is not the unique active Self Development project, either role cannot be impersonated for the safe install operation, or a publisher-token file already exists. On partial failure it attempts to remove matching token files and revoke every principal it created; verify that cleanup in the API before retrying. The script reports principal IDs and expiry only, never token values.

## Preconditions once that seam is implemented

1. Use only a work item in the authorized Self Development project that is `VERIFIED`, has an `APPROVE` review on the exact succeeded candidate SHA, and has no veto. The publisher re-derives this chain from PostgreSQL; do not manually alter its state.
2. Confirm `aao-impl-codex` has its own App config under `~aao-impl-codex/.config/aao/aao-impl-codex.{pem,json}`, and `aao-pm` has its own config under `~aao-pm/.config/aao/aao-pm.{pem,json}`. Private keys must remain owned by that role at mode `0600`; never copy either key to the other account.
3. Record the selected fork as `<IMPLEMENTER_OWNER>/aao` (or the actual installed fork). The implementer App must be installed on that fork; the PM App must have PR authority on `autoaiorg/aao`. The implementer App must not be installed on the canonical repository.
4. Ensure the role-specific publisher token is available as `$XDG_RUNTIME_DIR/aao-publisher.token` for each role, mode `0600`, with its matching AAO principal/grant. The provisioning command above verifies each file; never display, log, or reuse one role's token for the other.
5. Confirm PostgreSQL/API configuration and the candidate bare repository are accessible to both accounts through the established host configuration; do not copy `.env.local` or the CEO token.

## Two-step exercise

The CEO supplies the work ID, fork owner, and deployment paths from verified host configuration. Run the push as the implementer and the PR step as PM. Commands below intentionally use placeholders for deployment-specific, non-secret paths and fork name:

```bash
WORK_ID='<VERIFIED work item UUID>'
FORK='<implementer-owner>/aao'
AAO_ROOT='<clean deployed AAO checkout>'
PYTHON='<AAO virtualenv python>'
CANDIDATES='<shared candidate bare-repository path>'

# As CEO, confirm the role token files exist and are private without printing them:
sudo stat -c '%U %a %n' /run/user/$(id -u aao-impl-codex)/aao-publisher.token \
  /run/user/$(id -u aao-pm)/aao-publisher.token

# Step 1: GitHub App push; executes under the implementer uid and its private key.
sudo -u aao-impl-codex -H env \
  XDG_RUNTIME_DIR=/run/user/$(id -u aao-impl-codex) \
  AAO_PUBLISH_BASE_REPO=autoaiorg/aao AAO_PUBLISH_HEAD_REPO="$FORK" \
  AAO_PUBLISH_PUSH_APP=aao-impl-codex AAO_PUBLISH_PR_APP=aao-pm \
  AAO_CANDIDATE_REPOSITORY="$CANDIDATES" PYTHONPATH="$AAO_ROOT/src" \
  "$PYTHON" "$AAO_ROOT/scripts/publish_candidate.py" \
  --work-id "$WORK_ID" --step push --github apps

# Step 2: PM opens the PR from the already-pushed branch.
sudo -u aao-pm -H env \
  XDG_RUNTIME_DIR=/run/user/$(id -u aao-pm) \
  AAO_PUBLISH_BASE_REPO=autoaiorg/aao AAO_PUBLISH_HEAD_REPO="$FORK" \
  AAO_PUBLISH_PUSH_APP=aao-impl-codex AAO_PUBLISH_PR_APP=aao-pm \
  AAO_CANDIDATE_REPOSITORY="$CANDIDATES" PYTHONPATH="$AAO_ROOT/src" \
  "$PYTHON" "$AAO_ROOT/scripts/publish_candidate.py" \
  --work-id "$WORK_ID" --step open --github apps
```

If either command fails, stop; do not retry with `--github gh`, another account's key/token, or direct Git/API calls. The steps are idempotent for the same approved SHA and can be safely re-run under the same identities after diagnosing a non-authorization failure.

## Evidence to record

- exact AAO checkout SHA, work ID, candidate SHA, fork, App names, run time, and sanitized command exit statuses;
- `work.candidate_pushed` and `work.pr_opened` events from the canonical project activity, including distinct pusher/PM principals;
- PR URL/number, author `aao-pm[bot]`, head fork and exact candidate SHA;
- CI state on the PR. Do not merge as part of this exercise; R1 remains reserved for the acceptance rehearsal.

Do not include App keys, installation tokens, AAO bearer tokens, database URLs, or raw environment dumps in the evidence.
