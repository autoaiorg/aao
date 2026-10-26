#!/usr/bin/env bash
# Host preflight checks for AAO integral installation.
# Verifies OS platform, hardware requirements, privileges, and detects existing installations.
set -euo pipefail

say() { echo "== [PREFLIGHT] $*"; }
die() { echo "FAIL [PREFLIGHT]: $*" >&2; exit 1; }

say "Checking root privileges..."
[[ $EUID -eq 0 ]] || die "Preflight must be run as root (EUID 0)."

say "Checking Linux OS distribution..."
[[ -f /etc/os-release ]] || die "/etc/os-release not found. Unsupported platform."
# shellcheck source=/dev/null
source /etc/os-release

if [[ "${ID:-}" != "ubuntu" && "${ID_LIKE:-}" != *"debian"* && "${ID:-}" != "debian" ]]; then
  die "Platform '${ID:-unknown}' is not supported. Ubuntu 24.04 LTS (Noble) or Debian 12 required."
fi
say "OS detected: ${PRETTY_NAME:-$ID} (compatible)"

say "Checking CPU architecture..."
ARCH=$(uname -m)
[[ "$ARCH" == "x86_64" || "$ARCH" == "aarch64" ]] || die "Unsupported CPU architecture: $ARCH (expected x86_64 or aarch64)"
say "Architecture: $ARCH"

say "Checking memory..."
TOTAL_MEM_KB=$(grep MemTotal /proc/meminfo | awk '{print $2}')
TOTAL_MEM_MB=$(( TOTAL_MEM_KB / 1024 ))
if (( TOTAL_MEM_MB < 3500 )); then
  echo "WARN [PREFLIGHT]: Memory is ${TOTAL_MEM_MB}MB (recommended >= 4096MB)."
else
  say "Memory verified: ${TOTAL_MEM_MB}MB"
fi

say "Checking available disk space on / ..."
AVAIL_DISK_MB=$(df -m / | awk 'NR==2 {print $4}')
if (( AVAIL_DISK_MB < 5000 )); then
  die "Insufficient disk space on /: ${AVAIL_DISK_MB}MB available (minimum 5000MB required)."
fi
say "Disk space verified: ${AVAIL_DISK_MB}MB available"

say "Detecting existing installation state..."
EXISTING_INSTALL=0
if id aao-api >/dev/null 2>&1; then
  echo "INFO: Detected existing service user 'aao-api'"
  EXISTING_INSTALL=1
fi
if [[ -d /opt/aao ]]; then
  echo "INFO: Detected existing directory '/opt/aao'"
  EXISTING_INSTALL=1
fi
if [[ -d /etc/aao ]]; then
  echo "INFO: Detected existing configuration directory '/etc/aao'"
  EXISTING_INSTALL=1
fi

if (( EXISTING_INSTALL )); then
  say "Mode: IDEMPOTENT UPGRADE / RE-RUN (existing components detected; will reconcile without destruction)"
else
  say "Mode: FRESH INSTALLATION (clean machine detected)"
fi

say "Checking port availability..."
check_port() {
  local port=$1
  local name=$2
  if command -v ss >/dev/null 2>&1; then
    if ss -ltn | grep -q ":${port} "; then
      echo "INFO: Port ${port} (${name}) is currently listening."
    fi
  elif command -v netstat >/dev/null 2>&1; then
    if netstat -ltn | grep -q ":${port} "; then
      echo "INFO: Port ${port} (${name}) is currently listening."
    fi
  fi
}
check_port 8001 "AAO API"
check_port 5432 "PostgreSQL"

say "Host preflight passed successfully."
exit 0
