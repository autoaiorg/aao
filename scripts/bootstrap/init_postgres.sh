#!/usr/bin/env bash
# Aprovisionamiento nativo e idempotente de PostgreSQL 16 para AAO.
set -euo pipefail
umask 077

say() { echo "== [POSTGRES] $*"; }
die() { echo "FAIL [POSTGRES]: $*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "Run as root."

SECRET_FILE="/etc/aao/aao-db.secret"
RUNTIME_SECRET_FILE="/etc/aao/aao-runtime-db.secret"
RECOVERY_SECRET_FILE="/etc/aao/aao-recovery-db.secret"
FENCER_SECRET_FILE="/etc/aao/aao-fencer-db.secret"
mkdir -p /etc/aao
chmod 0750 /etc/aao

say "Ensuring PostgreSQL service is running..."
if command -v systemctl >/dev/null 2>&1 && systemctl is-system-running >/dev/null 2>&1; then
  systemctl enable postgresql
  systemctl start postgresql
elif command -v pg_ctlcluster >/dev/null 2>&1; then
  pg_ctlcluster 16 main start 2>/dev/null || service postgresql start
elif command -v service >/dev/null 2>&1; then
  service postgresql start
fi

say "Generating or reading application database password..."
if [[ -f "$SECRET_FILE" ]]; then
  DB_PASS=$(cat "$SECRET_FILE")
  say "Reusing existing database password from $SECRET_FILE"
else
  DB_PASS=$(openssl rand -hex 24)
  echo -n "$DB_PASS" > "$SECRET_FILE"
  chmod 0600 "$SECRET_FILE"
  say "Generated new database password in $SECRET_FILE"
fi

say "Generating or reading API runtime database password..."
if [[ -f "$RUNTIME_SECRET_FILE" ]]; then
  RUNTIME_DB_PASS=$(cat "$RUNTIME_SECRET_FILE")
else
  RUNTIME_DB_PASS=$(openssl rand -hex 24)
  printf '%s' "$RUNTIME_DB_PASS" > "$RUNTIME_SECRET_FILE"
fi
if [[ -f "$RECOVERY_SECRET_FILE" ]]; then
  RECOVERY_DB_PASS=$(cat "$RECOVERY_SECRET_FILE")
else
  RECOVERY_DB_PASS=$(openssl rand -hex 24)
  printf '%s' "$RECOVERY_DB_PASS" > "$RECOVERY_SECRET_FILE"
fi
if [[ -f "$FENCER_SECRET_FILE" ]]; then
  FENCER_DB_PASS=$(cat "$FENCER_SECRET_FILE")
else
  FENCER_DB_PASS=$(openssl rand -hex 24)
  printf '%s' "$FENCER_DB_PASS" > "$FENCER_SECRET_FILE"
fi
chown root:root "$SECRET_FILE" "$RUNTIME_SECRET_FILE" "$RECOVERY_SECRET_FILE" "$FENCER_SECRET_FILE"
chmod 0600 "$SECRET_FILE" "$RUNTIME_SECRET_FILE" "$RECOVERY_SECRET_FILE" "$FENCER_SECRET_FILE"

say "Configuring PostgreSQL role and database without SQL password interpolation..."
runuser -u postgres -- psql -v ON_ERROR_STOP=1 <<'EOF'
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'aao_app') THEN
    CREATE ROLE aao_app WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
  ELSE
    ALTER ROLE aao_app WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'aao_runtime') THEN
    CREATE ROLE aao_runtime WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT CONNECTION LIMIT 20;
  ELSE
    ALTER ROLE aao_runtime WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT CONNECTION LIMIT 20;
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'aao_recovery') THEN
    CREATE ROLE aao_recovery WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT CONNECTION LIMIT 10;
  ELSE
    ALTER ROLE aao_recovery WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT CONNECTION LIMIT 10;
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'aao_fencer') THEN
    CREATE ROLE aao_fencer WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT CONNECTION LIMIT 2;
  ELSE
    ALTER ROLE aao_fencer WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT CONNECTION LIMIT 2;
  END IF;
END $$;
-- A reused cluster may already contain role memberships. NOINHERIT prevents
-- automatic privilege inheritance, but does not prevent SET ROLE. Keep all
-- dedicated runtime roles isolated from every parent role before granting access.
DO $$
DECLARE
  member_role name;
  parent_role name;
BEGIN
  FOR member_role, parent_role IN
    SELECT member.rolname, parent.rolname
      FROM pg_auth_members membership
      JOIN pg_roles member ON member.oid = membership.member
      JOIN pg_roles parent ON parent.oid = membership.roleid
     WHERE member.rolname IN ('aao_runtime', 'aao_recovery', 'aao_fencer')
  LOOP
    EXECUTE format('REVOKE %I FROM %I', parent_role, member_role);
  END LOOP;
END $$;
EOF

say "Setting application database password via secure encrypted channel..."
printf "%s\n%s\n" "$DB_PASS" "$DB_PASS" | runuser -u postgres -- psql -v ON_ERROR_STOP=1 -c '\password aao_app'
printf "%s\n%s\n" "$RUNTIME_DB_PASS" "$RUNTIME_DB_PASS" | runuser -u postgres -- psql -v ON_ERROR_STOP=1 -c '\password aao_runtime'
printf "%s\n%s\n" "$RECOVERY_DB_PASS" "$RECOVERY_DB_PASS" | runuser -u postgres -- psql -v ON_ERROR_STOP=1 -c '\password aao_recovery'
printf "%s\n%s\n" "$FENCER_DB_PASS" "$FENCER_DB_PASS" | runuser -u postgres -- psql -v ON_ERROR_STOP=1 -c '\password aao_fencer'

# Create database if not exists
if ! runuser -u postgres -- psql -tAc "SELECT 1 FROM pg_database WHERE datname='aao_prod'" | grep -q 1; then
  say "Creating database 'aao_prod'..."
  runuser -u postgres -- createdb -O aao_app aao_prod
else
  say "Database 'aao_prod' already exists (reusing)."
fi

runuser -u postgres -- psql -d aao_prod -v ON_ERROR_STOP=1 <<EOF
GRANT ALL PRIVILEGES ON DATABASE aao_prod TO aao_app;
GRANT ALL ON SCHEMA public TO aao_app;
GRANT CONNECT ON DATABASE aao_prod TO aao_runtime;
GRANT CONNECT ON DATABASE aao_prod TO aao_recovery;
GRANT CONNECT ON DATABASE aao_prod TO aao_fencer;
GRANT USAGE ON SCHEMA public TO aao_runtime;
GRANT USAGE ON SCHEMA public TO aao_recovery;
GRANT USAGE ON SCHEMA public TO aao_fencer;
EOF

say "Verifying PostgreSQL connection for aao_app..."
PGPASSWORD="$DB_PASS" psql -h 127.0.0.1 -U aao_app -d aao_prod -c "SELECT 1" >/dev/null || \
PGPASSWORD="$DB_PASS" psql -U aao_app -d aao_prod -c "SELECT 1" >/dev/null || \
  die "Failed to connect to aao_prod as aao_app."

say "Verifying PostgreSQL connection for aao_runtime..."
PGPASSWORD="$RUNTIME_DB_PASS" psql -h 127.0.0.1 -U aao_runtime -d aao_prod -c "SELECT 1" >/dev/null || \
  die "Failed to connect to aao_prod as aao_runtime."

say "Verifying PostgreSQL connection for aao_recovery..."
PGPASSWORD="$RECOVERY_DB_PASS" psql -h 127.0.0.1 -U aao_recovery -d aao_prod -c "SELECT 1" >/dev/null || \
  die "Failed to connect to aao_prod as aao_recovery."

say "Verifying PostgreSQL connection for aao_fencer..."
PGPASSWORD="$FENCER_DB_PASS" psql -h 127.0.0.1 -U aao_fencer -d aao_prod -c "SELECT 1" >/dev/null || \
  die "Failed to connect to aao_prod as aao_fencer."

say "PostgreSQL provisioned and verified successfully."
exit 0
