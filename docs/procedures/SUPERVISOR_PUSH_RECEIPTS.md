# Supervisor push-receipt intake (construction)

The supervisor can persist signed, authenticated GitHub `push` webhook receipts in
`/var/lib/aao-supervisor/push-receipts`. `attribution` unions these receipts with
the currently available Events API history. The event poll remains as a recovery
source; missing chains still fail closed. Receipt directories must be supervisor-
owned and non-writable by group/others. The supervisor signs each receipt locally;
the HTTP handler checks GitHub's `X-Hub-Signature-256`, event delivery UUID,
repository allowlist, sender, ref and commit transition. Identical delivery retries
are idempotent; conflicting delivery IDs are rejected.

## Not active by default

This code does not configure a GitHub webhook, publish a public endpoint, or enable
the systemd service. Those require host/network configuration and CEO operation.
The listener binds to loopback by default and **must only be exposed through an
approved TLS-terminating reverse proxy**. Configure that proxy to route only
`POST /github/push`; do not expose the service directly to the Internet. The
GitHub webhook secret is not stored in the repo and must be provisioned as a
root-owned, supervisor-readable file at the configured path. Use a high-entropy
secret of at least 32 bytes and add only the canonical/fork repositories that
actually emit pushes to `webhook_repositories`. In particular, the implementer
forks used by W2 need their own configured webhook deliveries; a canonical-repo
webhook alone cannot attest pushes made to forks.

The service is `aao-supervisor-push-webhook.service` and remains disabled unless
the CEO completes endpoint, TLS proxy, GitHub webhook secret, and repository-list
provisioning. After a controlled deployment, validate a push through an actual
GitHub delivery and confirm an attributed receipt under the supervisor identity.
Unit tests of the receiver are not evidence of host deployment or successful
GitHub delivery. Do not enable the integrator as part of this setup.
