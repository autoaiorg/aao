#!/usr/bin/env bash
# Initialize and compartment environment secrets for AAO services.
# Conforms to CEO Condition 7: strict separation of service permissions and credentials.
set -euo pipefail

say() { echo "== [SECRETS] $*"; }
die() { echo "FAIL [SECRETS]: $*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "Run as root."

mkdir -p /etc/aao
getent group aao-host-id-read >/dev/null || die "aao-host-id-read group is missing; run identity bootstrap first."
chown root:aao-host-id-read /etc/aao
chmod 0750 /etc/aao

DB_SECRET_FILE="/etc/aao/aao-db.secret"
API_ENV_FILE="/etc/aao/aao-api.env"
WORKER_ENV_FILE="/etc/aao/aao-worker.env"
HOST_ID_FILE="/etc/aao/host-id"

if [[ -L "$HOST_ID_FILE" ]]; then
  die "$HOST_ID_FILE must not be a symbolic link"
fi
if [[ ! -e "$HOST_ID_FILE" ]]; then
  [[ -s /etc/machine-id ]] || die "A stable /etc/machine-id is required for host fencing."
  install -o root -g root -m 0440 /etc/machine-id "$HOST_ID_FILE"
fi
[[ -f "$HOST_ID_FILE" && -s "$HOST_ID_FILE" ]] || die "Host identity file is invalid."

say "Reading or generating database password..."
if [[ ! -f "$DB_SECRET_FILE" ]]; then
  DB_PASS=$(openssl rand -hex 24)
  echo -n "$DB_PASS" > "$DB_SECRET_FILE"
  chmod 0600 "$DB_SECRET_FILE"
else
  DB_PASS=$(cat "$DB_SECRET_FILE")
fi

say "Configuring /etc/aao/aao-api.env..."
if [[ -f "$API_ENV_FILE" ]]; then
  say "Reusing existing $API_ENV_FILE"
else
  CEO_TOKEN=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
  cat > "$API_ENV_FILE" <<EOF
# Production environment for aao-api.service
AAO_ENV=production
AAO_POSTGRES_URL=postgresql://aao_app:${DB_PASS}@127.0.0.1:5432/aao_prod
AAO_CEO_TOKEN=${CEO_TOKEN}
AAO_STATIC_DIR=/opt/aao/frontend/dist
AAO_SELF_DEV_REPOSITORY=/opt/aao/repo
AAO_CEO_SESSION_ALLOWED_ORIGINS=http://127.0.0.1:8001
EOF
  say "Generated $API_ENV_FILE"

  CEO_USER="${CEO_USER:-${SUDO_USER:-$(logname 2>/dev/null || true)}}"
  if [[ -n "$CEO_USER" ]] && id "$CEO_USER" >/dev/null 2>&1; then
    echo -n "$CEO_TOKEN" > /etc/aao/aao-ceo.token
    chown "$CEO_USER:$CEO_USER" /etc/aao/aao-ceo.token
    chmod 0600 /etc/aao/aao-ceo.token
    say "Provisioned CEO token for '$CEO_USER' at /etc/aao/aao-ceo.token"
  fi
fi

# Ensure permissions: owned by root:aao-api with 0640 (readable only by aao-api and root)
if id aao-api >/dev/null 2>&1; then
  chown root:aao-api "$API_ENV_FILE"
  chmod 0640 "$API_ENV_FILE"
else
  chmod 0600 "$API_ENV_FILE"
fi

say "Configuring /etc/aao/aao-worker.env..."
if [[ -f "$WORKER_ENV_FILE" ]]; then
  say "Reusing existing $WORKER_ENV_FILE"
else
  cat > "$WORKER_ENV_FILE" <<EOF
# Production environment for aao-worker-self-dev.service
AAO_ENV=production
AAO_API=http://127.0.0.1:8001
AAO_SELF_DEV_REPOSITORY=/opt/aao/repo
AAO_AGENT_PROVIDER=fixture
AAO_AGENT_BACKEND=fixture
# Set only after the CEO-confirmed mandate and AGENT grant are provisioned.
AAO_WORKER_PROJECT_ID=
AAO_WORKER_PRINCIPAL_ID=
EOF
  say "Generated $WORKER_ENV_FILE"
fi

if id aao-impl-ag >/dev/null 2>&1; then
  chown root:aao-impl-ag "$WORKER_ENV_FILE"
  chmod 0640 "$WORKER_ENV_FILE"
  chown root:aao-host-id-read "$HOST_ID_FILE"
  chmod 0440 "$HOST_ID_FILE"
  chown root:aao-host-id-read /etc/aao
else
  chmod 0600 "$WORKER_ENV_FILE"
  chmod 0600 "$HOST_ID_FILE"
fi

say "Secrets configured with strict least-privilege permissions."
exit 0
