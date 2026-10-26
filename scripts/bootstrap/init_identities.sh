#!/usr/bin/env bash
# Provision product service account aao-api and ensure governance role identities.
set -euo pipefail

say() { echo "== [IDENTITIES] $*"; }
die() { echo "FAIL [IDENTITIES]: $*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "Run as root."

CEO_USER="${CEO_USER:?CEO_USER environment variable must be specified}"
id "$CEO_USER" >/dev/null 2>&1 || die "CEO user '$CEO_USER' does not exist."

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
REPO_DIR=$(cd "$SCRIPT_DIR/../.." && pwd)

say "Applying governance identity separation for CEO_USER='$CEO_USER'..."
if [[ -f "$REPO_DIR/scripts/identity_separation.sh" ]]; then
  CEO_USER="$CEO_USER" bash "$REPO_DIR/scripts/identity_separation.sh" --apply || die "Governance identity separation failed."
else
  die "Required governance script $REPO_DIR/scripts/identity_separation.sh not found."
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

say "Verifying governance and product identity compliance..."
REQUIRED_USERS=(
  aao-api aao-pm aao-impl-codex aao-impl-claude aao-impl-ag
  aao-auditor aao-auditor-alt aao-integrator aao-supervisor aao-notifier aao-trust
)
for u in "${REQUIRED_USERS[@]}"; do
  id "$u" >/dev/null 2>&1 || die "Verification failed: required identity '$u' does not exist."
done

# Verify directory permissions
[[ -d /var/lib/aao-api ]] || die "Verification failed: /var/lib/aao-api does not exist."
[[ -d /var/lib/aao-auditor ]] || die "Verification failed: /var/lib/aao-auditor does not exist."
[[ -d /var/lib/aao-supervisor ]] || die "Verification failed: /var/lib/aao-supervisor does not exist."
[[ -d /srv/aao/trust ]] || die "Verification failed: /srv/aao/trust does not exist."

if [[ -f /etc/sudoers.d/aao-launch ]]; then
  mode=$(stat -c "%a" /etc/sudoers.d/aao-launch 2>/dev/null || stat -f "%Op" /etc/sudoers.d/aao-launch 2>/dev/null || echo "")
  if [[ "$mode" != "440" && "$mode" != "0440" ]]; then
    chmod 0440 /etc/sudoers.d/aao-launch
  fi
fi

say "Identities provisioned and verified compliant with governance P1."
exit 0
