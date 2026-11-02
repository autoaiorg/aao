#!/usr/bin/env bash
# Initialize and compartment environment secrets for AAO services.
# Conforms to CEO Condition 7: strict separation of service permissions and credentials.
set -euo pipefail
umask 077

say() { echo "== [SECRETS] $*"; }
die() { echo "FAIL [SECRETS]: $*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "Run as root."

mkdir -p /etc/aao
getent group aao-host-id-read >/dev/null || die "aao-host-id-read group is missing; run identity bootstrap first."
chown root:aao-host-id-read /etc/aao
chmod 0750 /etc/aao

DB_SECRET_FILE="/etc/aao/aao-db.secret"
RUNTIME_DB_SECRET_FILE="/etc/aao/aao-runtime-db.secret"
RECOVERY_DB_SECRET_FILE="/etc/aao/aao-recovery-db.secret"
FENCER_DB_SECRET_FILE="/etc/aao/aao-fencer-db.secret"
API_ENV_FILE="/etc/aao/aao-api.env"
RECOVERY_ENV_FILE="/etc/aao/aao-recovery.env"
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
[[ -s "$RUNTIME_DB_SECRET_FILE" ]] || die "API runtime database credential is missing; run init_postgres.sh first."
RUNTIME_DB_PASS=$(cat "$RUNTIME_DB_SECRET_FILE")
[[ -s "$RECOVERY_DB_SECRET_FILE" ]] || die "Recovery database credential is missing; run init_postgres.sh first."
RECOVERY_DB_PASS=$(cat "$RECOVERY_DB_SECRET_FILE")
[[ -s "$FENCER_DB_SECRET_FILE" ]] || die "Fencing database credential is missing; run init_postgres.sh first."
FENCER_DB_PASS=$(cat "$FENCER_DB_SECRET_FILE")

say "Configuring /etc/aao/aao-api.env..."
if [[ -f "$API_ENV_FILE" ]]; then
  say "Reusing existing $API_ENV_FILE"
else
  CEO_TOKEN=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
  cat > "$API_ENV_FILE" <<EOF
# Production environment for aao-api.service
AAO_ENV=production
AAO_POSTGRES_URL=postgresql://aao_runtime:${RUNTIME_DB_PASS}@127.0.0.1:5432/aao_prod
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

# Always switch an existing deployment from the migration owner to the runtime
# identity, while preserving all other operator-managed environment values.
[[ ! -L "$API_ENV_FILE" ]] || die "$API_ENV_FILE must not be a symbolic link"
AAO_RUNTIME_DB_PASS="$RUNTIME_DB_PASS" python3 - "$API_ENV_FILE" <<'PY'
import os
import pathlib
import tempfile
import sys

path = pathlib.Path(sys.argv[1])
dsn = f"postgresql://aao_runtime:{os.environ['AAO_RUNTIME_DB_PASS']}@127.0.0.1:5432/aao_prod"
lines = path.read_text().splitlines() if path.exists() else []
replacement = f"AAO_POSTGRES_URL={dsn}"
found = False
updated = []
for line in lines:
    if line.startswith("AAO_POSTGRES_URL="):
        if not found:
            updated.append(replacement)
            found = True
    else:
        updated.append(line)
if not found:
    updated.append(replacement)
data = "\n".join(updated) + "\n"
fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
try:
    with os.fdopen(fd, "w") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(temporary, 0o640)
    os.replace(temporary, path)
finally:
    if os.path.exists(temporary):
        os.unlink(temporary)
PY

# Ensure permissions: owned by root:aao-api with 0640 (readable only by aao-api and root)
if id aao-api >/dev/null 2>&1; then
  chown root:aao-api "$API_ENV_FILE"
  chmod 0640 "$API_ENV_FILE"
else
  chmod 0600 "$API_ENV_FILE"
fi

say "Configuring isolated /etc/aao/aao-recovery.env..."
if [[ ! -f "$RECOVERY_ENV_FILE" ]]; then
  cat > "$RECOVERY_ENV_FILE" <<EOF
# Production environment for aao-conversation-recovery.service
AAO_ENV=production
AAO_POSTGRES_URL=postgresql://aao_recovery:${RECOVERY_DB_PASS}@127.0.0.1:5432/aao_prod
AAO_CONVERSATION_RECOVERY_ENABLED=false
EOF
else
  say "Reusing existing $RECOVERY_ENV_FILE"
fi
[[ ! -L "$RECOVERY_ENV_FILE" ]] || die "$RECOVERY_ENV_FILE must not be a symbolic link"
AAO_RECOVERY_DB_PASS="$RECOVERY_DB_PASS" python3 - "$RECOVERY_ENV_FILE" <<'PY'
import os
import pathlib
import tempfile
import sys

path = pathlib.Path(sys.argv[1])
dsn = f"postgresql://aao_recovery:{os.environ['AAO_RECOVERY_DB_PASS']}@127.0.0.1:5432/aao_prod"
lines = path.read_text().splitlines() if path.exists() else []
replacement = f"AAO_POSTGRES_URL={dsn}"
found = False
updated = []
for line in lines:
    if line.startswith("AAO_POSTGRES_URL="):
        if not found:
            updated.append(replacement)
            found = True
    else:
        updated.append(line)
if not found:
    updated.append(replacement)
data = "\n".join(updated) + "\n"
fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
try:
    with os.fdopen(fd, "w") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(temporary, 0o640)
    os.replace(temporary, path)
finally:
    if os.path.exists(temporary):
        os.unlink(temporary)
PY
chown root:aao-recovery "$RECOVERY_ENV_FILE"
chmod 0640 "$RECOVERY_ENV_FILE"

say "Configuring root-only /etc/aao/aao-fencer.env..."
FENCER_ENV_FILE="/etc/aao/aao-fencer.env"
[[ ! -L "$FENCER_ENV_FILE" ]] || die "$FENCER_ENV_FILE must not be a symbolic link"
AAO_FENCER_DB_PASS="$FENCER_DB_PASS" python3 - "$FENCER_ENV_FILE" <<'PY'
import os
import pathlib
import tempfile
import sys

path = pathlib.Path(sys.argv[1])
dsn = f"postgresql://aao_fencer:{os.environ['AAO_FENCER_DB_PASS']}@127.0.0.1:5432/aao_prod"
data = f"AAO_FENCER_POSTGRES_URL={dsn}\n"
fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
try:
    with os.fdopen(fd, "w") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.chown(temporary, 0, 0)
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)
finally:
    if os.path.exists(temporary):
        os.unlink(temporary)
PY
chown root:root "$FENCER_ENV_FILE"
chmod 0600 "$FENCER_ENV_FILE"

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
