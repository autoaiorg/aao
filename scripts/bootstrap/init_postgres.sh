#!/usr/bin/env bash
# Aprovisionamiento nativo e idempotente de PostgreSQL 16 para AAO.
set -euo pipefail

say() { echo "== [POSTGRES] $*"; }
die() { echo "FAIL [POSTGRES]: $*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "Run as root."

SECRET_FILE="/etc/aao/aao-db.secret"
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

say "Configuring PostgreSQL role and database..."
runuser -u postgres -- psql -v ON_ERROR_STOP=1 <<EOF
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'aao_app') THEN
    CREATE ROLE aao_app WITH LOGIN PASSWORD '${DB_PASS}';
  ELSE
    ALTER ROLE aao_app WITH PASSWORD '${DB_PASS}';
  END IF;
END \$\$;
EOF

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
EOF

say "Verifying PostgreSQL connection for aao_app..."
PGPASSWORD="$DB_PASS" psql -h 127.0.0.1 -U aao_app -d aao_prod -c "SELECT 1" >/dev/null || \
PGPASSWORD="$DB_PASS" psql -U aao_app -d aao_prod -c "SELECT 1" >/dev/null || \
  die "Failed to connect to aao_prod as aao_app."

say "PostgreSQL provisioned and verified successfully."
exit 0
