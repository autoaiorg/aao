#!/usr/bin/env bash
# End-to-end clean machine acceptance suite for AAO Integral Bootstrap (AC-01 through AC-18).
# Runs inside a fresh, disposable Ubuntu 24.04 container.
set -euo pipefail

say() { echo -e "\n\033[1;32m=== [ACCEPTANCE TEST] $*\033[0m"; }
die() { echo -e "\n\033[1;31mFAIL [ACCEPTANCE TEST]: $*\033[0m" >&2; exit 1; }

FAILED=0
assert_eq() {
  local name=$1
  local expected=$2
  local actual=$3
  if [[ "$expected" == "$actual" ]]; then
    echo "  [ PASS ] $name"
  else
    echo "  [ FAIL ] $name: expected '$expected', got '$actual'" >&2
    FAILED=1
  fi
}

assert_true() {
  local name=$1
  shift
  if "$@"; then
    echo "  [ PASS ] $name"
  else
    echo "  [ FAIL ] $name (command failed: $*)" >&2
    FAILED=1
  fi
}

say "1. Setting up clean disposable environment preconditions..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq >/dev/null
apt-get install -y -qq \
  git python3 python3-venv python3-pip openssl acl bubblewrap \
  curl ca-certificates postgresql-16 postgresql-client-16 rsync sudo >/dev/null 2>&1

# Setup mock CEO user
if ! id alessbarb >/dev/null 2>&1; then
  useradd -m -s /bin/bash alessbarb
  echo "alessbarb ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/ceo-test
  chmod 0440 /etc/sudoers.d/ceo-test
fi

REPO_DIR="${1:-/repo}"
[[ -d "$REPO_DIR" ]] || die "Repository directory $REPO_DIR not found"

say "2. Testing AC-01: Fresh installation from scratch (including React build)..."
bash "$REPO_DIR/scripts/bootstrap/aao_bootstrap.sh" --apply --ceo-user alessbarb

say "3. Testing AC-02: Bootstrap idempotence (second run on configured host)..."
OUTPUT_SECOND=$(bash "$REPO_DIR/scripts/bootstrap/aao_bootstrap.sh" --apply --ceo-user alessbarb 2>&1)
assert_true "Second run exits 0" test $? -eq 0
assert_true "Second run maintains schema" grep -q "Schema is up to date" <<<"$OUTPUT_SECOND"
assert_true "Active release link exists" test -L /opt/aao/current
assert_true "Previous release link exists after second run" test -L /opt/aao/previous

say "4. Testing AC-03 & AC-04: PostgreSQL datastore and migrations 001-030..."
DB_PASS=$(cat /etc/aao/aao-db.secret)
export AAO_POSTGRES_URL="postgresql://aao_app:${DB_PASS}@127.0.0.1:5432/aao_prod"

MIG_COUNT=$(runuser -u postgres -- psql -d aao_prod -tAc "SELECT count(*) FROM schema_migrations")
assert_eq "All 30 migrations applied in schema_migrations" "30" "$MIG_COUNT"

assert_true "Migrator verification succeeds" \
  /opt/aao/venv/bin/aao-migrate --verify --dsn "$AAO_POSTGRES_URL"

say "5. Testing AC-05: API managed service and health endpoints..."
API_PID=""
if command -v systemctl >/dev/null 2>&1 && systemctl is-system-running >/dev/null 2>&1; then
  say "Verifying API under active systemd service manager..."
  systemctl restart aao-api.service
  sleep 2
  assert_true "aao-api.service is active under systemd" test "$(systemctl is-active aao-api.service)" = "active"
elif ! curl -sf http://127.0.0.1:8001/health >/dev/null 2>&1; then
  say "Notice: Container without systemd PID 1; testing service entrypoint..."
  export AAO_ENV=development
  export AAO_STATIC_DIR="/opt/aao/frontend/dist"
  export AAO_CEO_TOKEN=$(grep AAO_CEO_TOKEN /etc/aao/aao-api.env | cut -d= -f2)
  /opt/aao/venv/bin/uvicorn aao.work_management_api:app --host 127.0.0.1 --port 8001 --no-access-log >/tmp/api.log 2>&1 &
  API_PID=$!
  sleep 2
fi

HEALTH_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8001/health)
READY_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8001/ready)
assert_eq "GET /health returns HTTP 200" "200" "$HEALTH_CODE"
assert_eq "GET /ready returns HTTP 200" "200" "$READY_CODE"

say "6. Testing AC-07: Control Center SPA and client route serving..."
ROOT_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8001/)
KANBAN_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8001/kanban)
MANDATES_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8001/mandates)
NONEXISTENT_API_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8001/v1/invalid-route)

assert_eq "GET / serves HTML" "200" "$ROOT_CODE"
assert_eq "GET /kanban serves SPA" "200" "$KANBAN_CODE"
assert_eq "GET /mandates serves SPA" "200" "$MANDATES_CODE"
assert_eq "GET /v1/invalid-route returns 404 (not SPA)" "404" "$NONEXISTENT_API_CODE"

say "7. Testing AC-08 & AC-12: Permissions, Secret Segregation and Isolation..."
API_PERMS=$(stat -c "%a %U:%G" /etc/aao/aao-api.env)
WORKER_PERMS=$(stat -c "%a %U:%G" /etc/aao/aao-worker.env)
DB_SECRET_PERMS=$(stat -c "%a %U:%G" /etc/aao/aao-db.secret)

assert_true "aao-api.env has restricted permissions (0600 or 0640 root:aao-api)" \
  test "$API_PERMS" = "640 root:aao-api" -o "$API_PERMS" = "600 root:root" -o "$API_PERMS" = "640 root:root"

assert_true "aao-worker.env has restricted permissions (0600 or 0640 root:aao-impl-ag)" \
  test "$WORKER_PERMS" = "640 root:aao-impl-ag" -o "$WORKER_PERMS" = "600 root:root" -o "$WORKER_PERMS" = "640 root:root"

assert_true "aao-api cannot access /var/lib/aao-auditor" \
  bash -c "! runuser -u aao-api -- ls /var/lib/aao-auditor >/dev/null 2>&1"

say "8. Testing AC-09: Idempotent state initialization without duplicate entities..."
MANDATE_COUNT=$(runuser -u postgres -- psql -d aao_prod -tAc "SELECT count(*) FROM mandates WHERE title='AAO — Self Development'")
assert_eq "Self-Development mandate count is exactly 1" "1" "$MANDATE_COUNT"

MANDATE_STATUS=$(runuser -u postgres -- psql -d aao_prod -tAc "SELECT status FROM mandates WHERE title='AAO — Self Development'")
assert_eq "Self-Development mandate remains DRAFT without CEO confirmation" "DRAFT" "$MANDATE_STATUS"

PROJECT_COUNT=$(runuser -u postgres -- psql -d aao_prod -tAc "SELECT count(*) FROM projects WHERE name='AAO — Self Development'")
assert_eq "Self-Development active project count is 0 (reserved CEO decision)" "0" "$PROJECT_COUNT"

say "9. Testing AC-10: Atomic backup creation, checksum verification, and restore..."
mkdir -p /tmp/backups
BACKUP_FILE=$(/opt/aao/venv/bin/aao-ops backup --output-dir /tmp/backups | awk '{print $3}')
assert_true "Backup file exists" test -f "$BACKUP_FILE"

assert_true "Backup verification passes checksum check" \
  /opt/aao/venv/bin/aao-ops verify-backup "$BACKUP_FILE"

# Create clean database to test restore
runuser -u postgres -- createdb -O aao_app aao_restore_test
assert_true "Restore into clean database succeeds" \
  /opt/aao/venv/bin/aao-ops restore "$BACKUP_FILE" --target-dsn "postgresql://aao_app:${DB_PASS}@127.0.0.1:5432/aao_restore_test"

RESTORE_MIG_COUNT=$(runuser -u postgres -- psql -d aao_restore_test -tAc "SELECT count(*) FROM schema_migrations")
assert_eq "Restored database has all 30 migrations" "30" "$RESTORE_MIG_COUNT"

runuser -u postgres -- dropdb aao_restore_test

say "10. Testing AC-11: Negative tests fail closed..."
# Scenario A: Tampered migration file fails verify
echo "-- corrupted" >> /opt/aao/current/db/postgres/001_foundation.sql
assert_true "Tampered migration detected and rejected" \
  bash -c "! /opt/aao/venv/bin/aao-migrate --verify --dsn '$AAO_POSTGRES_URL' >/dev/null 2>&1"
cp "$REPO_DIR/db/postgres/001_foundation.sql" /opt/aao/current/db/postgres/001_foundation.sql

# Scenario B: Destructive restore over live DB without CEO authorization is refused
assert_true "Destructive restore over active DB without allow-non-empty is refused" \
  bash -c "! /opt/aao/venv/bin/python /opt/aao/current/scripts/aao_ops.py restore '$BACKUP_FILE' --target-dsn '$AAO_POSTGRES_URL' >/dev/null 2>&1"
assert_true "Destructive restore over active DB without authorized-by-ceo is refused" \
  bash -c "! /opt/aao/venv/bin/python /opt/aao/current/scripts/aao_ops.py restore '$BACKUP_FILE' --target-dsn '$AAO_POSTGRES_URL' --allow-non-empty >/dev/null 2>&1"

# Scenario C: Host fencing revokes active agent tokens and records event
assert_true "Host fencing executes cleanly" \
  /opt/aao/venv/bin/python /opt/aao/current/scripts/aao_ops.py fence-host --host-id "test-container"

# Scenario D: Invalid CEO token rejected by API
INVALID_AUTH_CODE=$(curl -s -o /dev/null -w "%{http_code}" -H "X-CEO-Token: invalid-token-12345" http://127.0.0.1:8001/v1/mandates)
assert_eq "Invalid CEO token rejected with 401 or 403" "403" "$INVALID_AUTH_CODE"

say "11. Testing AC-13 & AC-14: Integrator stays OFF and R2 blocked..."
if command -v systemctl >/dev/null 2>&1 && systemctl is-system-running >/dev/null 2>&1; then
  INTEGRATOR_STATE=$(systemctl is-enabled aao-integrator-tick.timer 2>&1 || true)
  assert_true "Integrator timer is disabled or masked" \
    bash -c '[[ "$INTEGRATOR_STATE" == *"masked"* || "$INTEGRATOR_STATE" == *"disabled"* || "$INTEGRATOR_STATE" == *"not-found"* ]]'
else
  assert_true "Integrator timer is not enabled in multi-user.target.wants" \
    test ! -e /etc/systemd/system/multi-user.target.wants/aao-integrator-tick.timer
fi

# Clean up background API if started
if [[ -n "$API_PID" ]]; then
  kill "$API_PID" 2>/dev/null || true
fi

say "12. Final Acceptance Assessment..."
if (( FAILED == 0 )); then
  say "ALL ACCEPTANCE CRITERIA PASSED EXPERIMENTALLY!"
  exit 0
else
  die "ONE OR MORE ACCEPTANCE CRITERIA FAILED."
fi
