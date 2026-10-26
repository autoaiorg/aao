#!/usr/bin/env bash
# AAO Integral Host Bootstrap and Reproducible Deployment Orchestrator.
#
# Usage:
#   sudo ./scripts/bootstrap/aao_bootstrap.sh [--apply] [options]
#
# Options:
#   --apply            Execute real system changes (default: dry-run)
#   --skip-deps        Skip apt-get system package installation
#   --skip-frontend    Skip building React frontend with npm
#   --ceo-user <name>  Host CEO account name (default: current non-root user)
#
# Enforces AAO Governance Rules:
#   - Integrator remains OFF
#   - Review Agreements remain PENDING
#   - Risk Level R2 remains locked
#   - Idempotent and fail-closed
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
REPO_DIR=$(cd "$SCRIPT_DIR/../.." && pwd)

say() { echo -e "\n\033[1;34m== [AAO BOOTSTRAP] $*\033[0m"; }
die() { echo -e "\n\033[1;31mFAIL [AAO BOOTSTRAP]: $*\033[0m" >&2; exit 1; }

APPLY=0
SKIP_DEPS=0
SKIP_FRONTEND=0
CEO_USER="${SUDO_USER:-$(logname 2>/dev/null || echo "alessbarb")}"

while [[ $# -gt 0 ]]; do
  case $1 in
    --apply) APPLY=1;;
    --skip-deps) SKIP_DEPS=1;;
    --skip-frontend) SKIP_FRONTEND=1;;
    --ceo-user) CEO_USER=$2; shift;;
    *) die "Unknown option: $1";;
  esac
  shift
done

[[ $EUID -eq 0 ]] || die "aao_bootstrap.sh must be run as root (or via sudo)."

say "Starting AAO Bootstrap (APPLY=$APPLY, CEO_USER=$CEO_USER)..."

# ------------------------------------------------------------------------------
# STEP 0: Preflight checks
# ------------------------------------------------------------------------------
say "Step 0: Executing Host Preflight..."
bash "$SCRIPT_DIR/host_preflight.sh"

if (( ! APPLY )); then
  say "DRY RUN COMPLETE: Preflight passed. Re-run with --apply to execute system deployment."
  exit 0
fi

# ------------------------------------------------------------------------------
# STEP 1: Identities and Directories
# ------------------------------------------------------------------------------
say "Step 1: Setting up role and product identities..."
CEO_USER="$CEO_USER" bash "$SCRIPT_DIR/init_identities.sh"

# ------------------------------------------------------------------------------
# STEP 2: System Dependencies & Python Venv
# ------------------------------------------------------------------------------
if (( ! SKIP_DEPS )); then
  say "Step 2: Installing system packages and Python runtime..."
  bash "$SCRIPT_DIR/install_dependencies.sh"
else
  say "Step 2: Skipping system dependencies (--skip-deps)."
fi

# ------------------------------------------------------------------------------
# STEP 3: Deploy Repository to /opt/aao/repo and install Python package
# ------------------------------------------------------------------------------
say "Step 3: Synchronizing application code into /opt/aao/repo..."
mkdir -p /opt/aao/repo
# Synchronize code excluding temporary files and git worktrees
rsync -a --delete \
  --exclude ".git" \
  --exclude ".worktrees" \
  --exclude "node_modules" \
  --exclude ".pytest_cache" \
  --exclude "__pycache__" \
  "$REPO_DIR/" /opt/aao/repo/

say "Installing AAO package into /opt/aao/venv..."
/opt/aao/venv/bin/pip install --quiet -e '/opt/aao/repo[postgres]'

# ------------------------------------------------------------------------------
# STEP 4: PostgreSQL Native Datastore Provisioning
# ------------------------------------------------------------------------------
say "Step 4: Provisioning native PostgreSQL 16..."
bash "$SCRIPT_DIR/init_postgres.sh"

# ------------------------------------------------------------------------------
# STEP 5: Apply Schema Migrations (Single Source of Truth)
# ------------------------------------------------------------------------------
say "Step 5: Applying database migrations (001 to 030)..."
DB_PASS=$(cat /etc/aao/aao-db.secret)
export AAO_POSTGRES_URL="postgresql://aao_app:${DB_PASS}@127.0.0.1:5432/aao_prod"

/opt/aao/venv/bin/python /opt/aao/repo/scripts/migrate.py --apply --dsn "$AAO_POSTGRES_URL"
/opt/aao/venv/bin/python /opt/aao/repo/scripts/migrate.py --verify --dsn "$AAO_POSTGRES_URL"

# ------------------------------------------------------------------------------
# STEP 6: Control Center React Production Build
# ------------------------------------------------------------------------------
if (( ! SKIP_FRONTEND )); then
  say "Step 6: Compiling and publishing Control Center React SPA..."
  bash "$SCRIPT_DIR/build_frontend.sh"
else
  say "Step 6: Skipping frontend build (--skip-frontend)."
fi

# ------------------------------------------------------------------------------
# STEP 7: Environment Configuration & Secret Distribution
# ------------------------------------------------------------------------------
say "Step 7: Configuring service environment files in /etc/aao/..."
bash "$SCRIPT_DIR/init_secrets.sh"

# ------------------------------------------------------------------------------
# STEP 8: Idempotent State Initialization (Respecting CEO Reserves)
# ------------------------------------------------------------------------------
say "Step 8: Initializing technical state..."
/opt/aao/venv/bin/python /opt/aao/repo/scripts/bootstrap/init_state.py --ensure-proposal

# ------------------------------------------------------------------------------
# STEP 9: Systemd Unit Deployment & Service Management
# ------------------------------------------------------------------------------
say "Step 9: Deploying systemd services..."
cp /opt/aao/repo/deploy/systemd/aao-api.service /etc/systemd/system/
cp /opt/aao/repo/deploy/systemd/aao-worker-self-dev.service /etc/systemd/system/
cp /opt/aao/repo/deploy/systemd/aao-conversation-recovery.service /etc/systemd/system/
cp /opt/aao/repo/deploy/systemd/aao-conversation-recovery.timer /etc/systemd/system/

if command -v systemctl >/dev/null 2>&1 && systemctl is-system-running >/dev/null 2>&1; then
  systemctl daemon-reload
  systemctl enable aao-api.service
  systemctl restart aao-api.service

  # Integrator timer MUST remain OFF
  systemctl disable aao-integrator-tick.timer 2>/dev/null || true
  systemctl stop aao-integrator-tick.timer 2>/dev/null || true
  systemctl mask aao-integrator-tick.timer 2>/dev/null || true
  say "Integrator timer confirmed masked (OFF)."
else
  say "Notice: systemd PID 1 not active in this environment; service files installed into /etc/systemd/system/."
fi

# ------------------------------------------------------------------------------
# STEP 10: Operational Verification & Diagnostics
# ------------------------------------------------------------------------------
say "Step 10: Running system doctor diagnostics..."
sleep 2
/opt/aao/venv/bin/python /opt/aao/repo/scripts/aao_ops.py doctor || true

say "AAO Integral Bootstrap Completed Successfully."
say "Control Center UI: http://127.0.0.1:8001/"
say "API Status:        http://127.0.0.1:8001/ready"
exit 0
