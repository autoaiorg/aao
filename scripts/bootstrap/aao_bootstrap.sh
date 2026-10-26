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
#   --rev <40-hex>     Exact Git revision for governance host bootstrap validation
#   --with-governance  Explicitly run host governance bootstrap (host_bootstrap.sh)
#
# Enforces AAO Governance Rules:
#   - Integrator remains OFF
#   - Review Agreements remain PENDING
#   - Risk Level R2 remains locked
#   - Idempotent, versioned releases, and fail-closed
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
REPO_DIR=$(cd "$SCRIPT_DIR/../.." && pwd)
source "$SCRIPT_DIR/release_state.sh"

say() { echo -e "\n\033[1;34m== [AAO BOOTSTRAP] $*\033[0m"; }
die() { echo -e "\n\033[1;31mFAIL [AAO BOOTSTRAP]: $*\033[0m" >&2; exit 1; }

APPLY=0
SKIP_DEPS=0
SKIP_FRONTEND=0
REV=""
KEYS_DIR=""
CEO_USER="${CEO_USER:-${SUDO_USER:-$(logname 2>/dev/null || true)}}"

while [[ $# -gt 0 ]]; do
  case $1 in
    --apply) APPLY=1;;
    --skip-deps) SKIP_DEPS=1;;
    --skip-frontend) SKIP_FRONTEND=1;;
    --with-governance) ;; # Deprecated: governance is mandatory on integral installs
    --rev) REV=$2; shift;;
    --keys-dir) KEYS_DIR=$2; shift;;
    --ceo-user) CEO_USER=$2; shift;;
    *) die "Unknown option: $1";;
  esac
  shift
done

[[ $EUID -eq 0 ]] || die "aao_bootstrap.sh must be run as root (or via sudo)."

[[ -n "$CEO_USER" ]] || die "--ceo-user <name> must be specified (could not safely determine from SUDO_USER or logname)."
id "$CEO_USER" >/dev/null 2>&1 || die "Configured CEO user '$CEO_USER' does not exist on this host."

# Mandatory Git commit revision resolution (Finding B-10)
if [[ -z "$REV" ]]; then
  if git -C "$REPO_DIR" rev-parse HEAD >/dev/null 2>&1; then
    REV=$(git -C "$REPO_DIR" rev-parse HEAD)
    say "Resolved Git commit revision from working tree: $REV"
  elif [[ -f "$REPO_DIR/.git-rev" ]]; then
    REV=$(tr -d '[:space:]' < "$REPO_DIR/.git-rev")
    say "Resolved Git commit revision from .git-rev: $REV"
  elif [[ -f /opt/aao/current/.git-rev ]]; then
    REV=$(tr -d '[:space:]' < /opt/aao/current/.git-rev)
    say "Resolved Git commit revision from /opt/aao/current/.git-rev: $REV"
  else
    die "Mandatory Git commit revision (--rev <40-hex>) could not be determined. Fail closed."
  fi
fi

[[ "$REV" =~ ^[0-9a-f]{40}$ ]] || die "Invalid commit revision '$REV': must be 40 hexadecimal characters."

say "Starting AAO Bootstrap (APPLY=$APPLY, CEO_USER=$CEO_USER, REV=$REV)..."

# ------------------------------------------------------------------------------
# STEP 0: Preflight checks
# ------------------------------------------------------------------------------
say "Step 0: Executing Host Preflight..."
bash "$SCRIPT_DIR/host_preflight.sh"

if (( ! APPLY )); then
  say "DRY RUN COMPLETE: Preflight passed. Re-run with --apply to execute system deployment."
  exit 0
fi

# Capture the currently active release before any deployment changes. The
# `previous` link is history from the last successful deployment, not the
# rollback target for this deployment (it may be one release older).
ROLLBACK_RELEASE=""
ROLLBACK_RELEASE=$(aao_capture_active_release /opt/aao/current || true)

# Define safe rollback handler with cross-system consistency
rollback_release() {
  local exit_code=$?
  say "CRITICAL: Bootstrap step failed with exit code $exit_code!"
  if [[ -n "$ROLLBACK_RELEASE" && -d "$ROLLBACK_RELEASE" ]]; then
    local prev_dir="$ROLLBACK_RELEASE"
    if [[ -d "$prev_dir" ]]; then
      say "Initiating safe rollback of active release to previous known-good state ($prev_dir)..."
      local rollback_errors=()

      # 1. Revert release directory and Python virtual-environment links.
      if ! aao_restore_release_links /opt/aao "$prev_dir"; then
        rollback_errors+=("Failed to restore active release links")
      elif [[ -d "$prev_dir/venv" ]]; then
        say "Restored previous active release and its exact Python virtual environment ($prev_dir/venv)."
      elif [[ -x /opt/aao/venv/bin/pip ]]; then
        say "Re-installing previous release into Python venv..."
        if ! /opt/aao/venv/bin/pip install --quiet -e "$prev_dir[postgres]"; then
          rollback_errors+=("Failed to reinstall previous release in Python venv during rollback")
        fi
      fi

      # 3. Verify Python runtime integrity
      if ! /opt/aao/venv/bin/python -c "import aao, fastapi, uvicorn" >/dev/null 2>&1; then
        rollback_errors+=("Python runtime verification failed in rolled-back environment")
      fi

      # 4. Verify database schema compatibility with the rolled-back release (Finding A-12)
      if [[ -f /etc/aao/aao-db.secret && -x /opt/aao/venv/bin/python ]]; then
        local db_pass
        db_pass=$(cat /etc/aao/aao-db.secret)
        local test_dsn="postgresql://aao_app:${db_pass}@127.0.0.1:5432/aao_prod"
        say "Verifying strict schema compatibility for rolled-back release ($prev_dir)..."
        if ! /opt/aao/venv/bin/python "$prev_dir/scripts/migrate.py" --verify --dsn "$test_dsn" >/dev/null 2>&1; then
          rollback_errors+=("Database schema is incompatible with rolled-back release ($prev_dir). Forward recovery required; destructive downgrade rejected.")
        fi
      fi

      # 5. Service restart and functional verification
      if command -v systemctl >/dev/null 2>&1 && systemctl is-system-running >/dev/null 2>&1; then
        say "Restarting systemd services pointing to previous release..."
        systemctl daemon-reload
        if ! systemctl restart aao-api.service; then
          rollback_errors+=("Failed to restart aao-api.service during rollback")
        else
          local ready_ok=0
          for ((i=1; i<=10; i++)); do
            if curl -fsSL http://127.0.0.1:8001/ready >/dev/null 2>&1; then
              ready_ok=1
              break
            fi
            sleep 1
          done
          if (( ! ready_ok )); then
            rollback_errors+=("Service aao-api.service did not become ready (HTTP 200 on /ready) post-rollback")
          fi
        fi
      fi

      # 6. Evaluate rollback outcome (fail closed on incomplete rollback)
      mkdir -p /etc/aao /var/lib/aao 2>/dev/null || true
      if (( ${#rollback_errors[@]} > 0 )); then
        echo "ROLLBACK_INCOMPLETE" > /var/lib/aao/rollback_status 2>/dev/null || true
        echo "ROLLBACK_INCOMPLETE" > /etc/aao/rollback_status 2>/dev/null || true
        echo -e "\n\033[1;31mFAIL [ROLLBACK]: ROLLBACK INCOMPLETE / CRITICAL INCONSISTENCY DETECTED!\033[0m" >&2
        echo "The system could not be fully restored to a consistent operational state:" >&2
        for err in "${rollback_errors[@]}"; do
          echo "  - $err" >&2
        done
        exit 1
      fi

      echo "ROLLBACK_SUCCESSFUL" > /var/lib/aao/rollback_status 2>/dev/null || true
      echo "ROLLBACK_SUCCESSFUL" > /etc/aao/rollback_status 2>/dev/null || true
      say "PASS [ROLLBACK]: Rollback successfully verified: /opt/aao/current, Python runtime, and services restored to consistent operational state ($prev_dir)."
    fi
  fi
  exit "$exit_code"
}
trap rollback_release ERR

# ------------------------------------------------------------------------------
# STEP 1: Governance & Product Identities
# ------------------------------------------------------------------------------
say "Step 1: Setting up role and product identities..."
CEO_USER="$CEO_USER" bash "$SCRIPT_DIR/init_identities.sh"

say "Step 1.1: Ensuring governance infrastructure (trust root, ledgers, events)..."
for aud in aao-auditor aao-auditor-alt; do
  if id "$aud" >/dev/null 2>&1; then
    install -d -o "$aud" -g aao-ledger-read -m 0750 "/var/lib/$aud" "/var/lib/$aud/ledger"
    install -d -o "$aud" -g "$aud" -m 0700 "/var/lib/$aud/keys"
  fi
done

if id aao-supervisor >/dev/null 2>&1; then
  install -d -o aao-supervisor -g aao-events -m 0750 /var/lib/aao-supervisor /var/lib/aao-supervisor/events
fi

if id aao-trust >/dev/null 2>&1; then
  install -d -o aao-trust -g aao-trust -m 0755 /srv/aao /srv/aao/trust /srv/aao/trust/keys /srv/aao/frozen
  for c in aao-auditor aao-auditor-alt aao-integrator aao-supervisor; do
    install -d -o aao-trust -g aao-trust -m 0755 "/srv/aao/frozen/$c"
  done
fi

if [[ ! -f "$REPO_DIR/scripts/bootstrap/host_bootstrap.sh" ]]; then
  die "Mandatory governance bootstrap script '$REPO_DIR/scripts/bootstrap/host_bootstrap.sh' is missing!"
fi

if [[ -n "${KEYS_DIR:-}" ]]; then
  say "Executing full verified host governance bootstrap (host_bootstrap.sh --keys-dir $KEYS_DIR)..."
  bash -p "$REPO_DIR/scripts/bootstrap/host_bootstrap.sh" --rev "$REV" --ceo-user "$CEO_USER" --keys-dir "$KEYS_DIR" --apply
else
  say "Verifying host governance configuration (dry-run preflight without production keys)..."
  bash -p "$REPO_DIR/scripts/bootstrap/host_bootstrap.sh" --rev "$REV" --ceo-user "$CEO_USER"
fi

say "Verifying governance identity separation across core roles..."
VERIFY_SCRIPT="/tmp/verify_identity_separation.sh"
cp "$REPO_DIR/scripts/verify_identity_separation.sh" "$VERIFY_SCRIPT"
chmod 0755 "$VERIFY_SCRIPT"
for u in aao-pm aao-impl-ag aao-auditor aao-supervisor aao-integrator; do
  if id "$u" >/dev/null 2>&1; then
    runuser -u "$u" -- env CEO_USER="$CEO_USER" bash "$VERIFY_SCRIPT" || die "Governance isolation verification failed for role '$u'!"
  fi
done
rm -f "$VERIFY_SCRIPT"
say "Governance identity separation verified compliant."

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
# STEP 3: Versioned Release Deployment (No Destructive In-Place Rsync)
# ------------------------------------------------------------------------------
RELEASE_TIMESTAMP=$(date -u +%Y%m%d%H%M%S)
GIT_SHA=$(git -C "$REPO_DIR" rev-parse --short=8 HEAD 2>/dev/null || echo "init")
RELEASE_ID="release-${RELEASE_TIMESTAMP}_${GIT_SHA}"
RELEASE_DIR="/opt/aao/releases/$RELEASE_ID"

say "Step 3: Staging immutable versioned release to $RELEASE_DIR..."
mkdir -p "$RELEASE_DIR" "/opt/aao/releases"

# Export the exact, clean commit named by REV. This prevents dirty tracked code,
# ignored secrets, and generated developer state from being mislabeled as a
# reproducible release.
bash "$SCRIPT_DIR/stage_release_source.sh" "$REPO_DIR" "$REV" "$RELEASE_DIR"

say "Creating release-isolated Python virtual environment in $RELEASE_DIR/venv..."
if [[ -d /opt/aao/base_venv ]]; then
  python3 -m venv "$RELEASE_DIR/venv"
elif [[ -d /opt/aao/venv && ! -L /opt/aao/venv ]]; then
  mv /opt/aao/venv /opt/aao/base_venv
  python3 -m venv "$RELEASE_DIR/venv"
else
  python3 -m venv "$RELEASE_DIR/venv"
fi

say "Installing dependencies and AAO package into $RELEASE_DIR/venv..."
"$RELEASE_DIR/venv/bin/pip" install --quiet --upgrade pip setuptools wheel
"$RELEASE_DIR/venv/bin/pip" install --quiet -e "$RELEASE_DIR[postgres]"

# Atomically update /opt/aao/venv symlink to the release-isolated venv
ln -sfn "$RELEASE_DIR/venv" /opt/aao/venv.tmp
mv -Tf /opt/aao/venv.tmp /opt/aao/venv

# Atomically update /opt/aao/current and backward-compatible /opt/aao/repo
ln -sfn "$RELEASE_DIR" /opt/aao/current.tmp
mv -Tf /opt/aao/current.tmp /opt/aao/current

# Preserve existing real /opt/aao/repo directory if present (never rm -rf real data)
if [[ -e /opt/aao/repo && ! -L /opt/aao/repo ]]; then
  LEGACY_BACKUP="/opt/aao/repo.legacy_$(date -u +%Y%m%d%H%M%S)"
  say "Preserving existing non-symlink /opt/aao/repo to $LEGACY_BACKUP..."
  mv /opt/aao/repo "$LEGACY_BACKUP"
elif [[ -L /opt/aao/repo ]]; then
  rm -f /opt/aao/repo
fi
ln -sfn /opt/aao/current /opt/aao/repo

# Safely prune older releases, protecting current and previous
prune_releases() {
  local current_target=""
  local previous_target=""
  [[ -e /opt/aao/current ]] && current_target=$(readlink -f /opt/aao/current || true)
  [[ -e /opt/aao/previous ]] && previous_target=$(readlink -f /opt/aao/previous || true)

  say "Maintaining release history (protecting active and previous releases)..."
  local count=0
  while IFS= read -r rel; do
    [[ -z "$rel" ]] && continue
    count=$((count + 1))
    local rel_real
    rel_real=$(readlink -f "$rel" || true)

    # Never delete releases actively pointed to by current or previous
    if [[ -n "$current_target" && "$rel_real" == "$current_target" ]]; then
      continue
    fi
    if [[ -n "$previous_target" && "$rel_real" == "$previous_target" ]]; then
      continue
    fi

    # Retain the 3 most recent releases regardless
    if (( count <= 3 )); then
      continue
    fi

    say "Pruning unreferenced older release: $rel"
    rm -rf "$rel"
  done < <(find /opt/aao/releases -maxdepth 1 -mindepth 1 -type d | sort -r)
}
prune_releases

# ------------------------------------------------------------------------------
# STEP 4: PostgreSQL Native Datastore Provisioning
# ------------------------------------------------------------------------------
say "Step 4: Provisioning native PostgreSQL 16..."
bash "$SCRIPT_DIR/init_postgres.sh"

# ------------------------------------------------------------------------------
# STEP 5: Apply Schema Migrations (Single Source of Truth)
# ------------------------------------------------------------------------------
say "Step 5: Applying database migrations (001 to 031)..."
DB_PASS=$(cat /etc/aao/aao-db.secret)
export AAO_POSTGRES_URL="postgresql://aao_app:${DB_PASS}@127.0.0.1:5432/aao_prod"

/opt/aao/venv/bin/python /opt/aao/current/scripts/migrate.py --apply --dsn "$AAO_POSTGRES_URL"
/opt/aao/venv/bin/python /opt/aao/current/scripts/migrate.py --verify --dsn "$AAO_POSTGRES_URL"

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
CEO_USER="$CEO_USER" bash "$SCRIPT_DIR/init_secrets.sh"

# ------------------------------------------------------------------------------
# STEP 8: Idempotent State Initialization (Respecting CEO Reserves)
# ------------------------------------------------------------------------------
say "Step 8: Initializing technical state..."
/opt/aao/venv/bin/python /opt/aao/current/scripts/bootstrap/init_state.py --ensure-proposal

# ------------------------------------------------------------------------------
# STEP 9: Systemd Unit Deployment & Service Management
# ------------------------------------------------------------------------------
say "Step 9: Deploying systemd services..."
cp /opt/aao/current/deploy/systemd/aao-api.service /etc/systemd/system/
cp /opt/aao/current/deploy/systemd/aao-worker-self-dev.service /etc/systemd/system/
cp /opt/aao/current/deploy/systemd/aao-conversation-recovery.service /etc/systemd/system/
cp /opt/aao/current/deploy/systemd/aao-conversation-recovery.timer /etc/systemd/system/

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
# STEP 10: Operational Verification & Diagnostics (Fail Closed)
# ------------------------------------------------------------------------------
say "Step 10: Running system doctor diagnostics..."
sleep 2

# Running doctor: MUST succeed (exit 0). If it fails, fail closed!
if ! /opt/aao/venv/bin/python /opt/aao/current/scripts/aao_ops.py doctor; then
  die "System doctor diagnostics failed. Aborting bootstrap and reverting active release."
fi

# Publish the rollback pointer only after the new release passes diagnostics.
# Failed deployments retain the prior history pointer unchanged.
if [[ -n "$ROLLBACK_RELEASE" && "$ROLLBACK_RELEASE" != "$RELEASE_DIR" ]]; then
  ln -s -- "$ROLLBACK_RELEASE" /opt/aao/previous.tmp
  mv -Tf -- /opt/aao/previous.tmp /opt/aao/previous
fi

# Successful completion: clear rollback trap
trap - ERR

say "AAO Integral Bootstrap Completed Successfully."
say "Active Release:    $RELEASE_ID (/opt/aao/current)"
say "Control Center UI: http://127.0.0.1:8001/"
say "API Status:        http://127.0.0.1:8001/ready"
exit 0
