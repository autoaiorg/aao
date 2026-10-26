#!/usr/bin/env bash
# Provision product service account aao-api and ensure governance role identities.
set -euo pipefail

say() { echo "== [IDENTITIES] $*"; }
die() { echo "FAIL [IDENTITIES]: $*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "Run as root."

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
REPO_DIR=$(cd "$SCRIPT_DIR/../.." && pwd)

say "Applying governance identity separation..."
if [[ -f "$REPO_DIR/scripts/identity_separation.sh" ]]; then
  bash "$REPO_DIR/scripts/identity_separation.sh" --apply || die "Governance identity separation failed."
fi

say "Ensuring product service account 'aao-api'..."
if ! id aao-api >/dev/null 2>&1; then
  groupadd -r aao-api
  useradd -r -g aao-api -s /usr/sbin/nologin -d /var/lib/aao-api -m aao-api
  passwd -l aao-api >/dev/null 2>&1 || true
  say "Created service user 'aao-api' (locked, nologin)."
else
  say "User 'aao-api' already exists."
fi

say "Setting directory permissions..."
mkdir -p /var/lib/aao-api /var/log/aao
chown aao-api:aao-api /var/lib/aao-api
chmod 0750 /var/lib/aao-api

# Allow service accounts to write to logs
chown -R root:aao-api /var/log/aao
chmod 0775 /var/log/aao

say "Identities provisioned and verified."
exit 0
