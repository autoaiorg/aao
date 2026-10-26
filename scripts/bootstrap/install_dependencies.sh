#!/usr/bin/env bash
# Install required system packages, Node.js 24 LTS, and isolated Python venv for AAO.
set -euo pipefail

say() { echo "== [DEPENDENCIES] $*"; }
die() { echo "FAIL [DEPENDENCIES]: $*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "Run as root."

export DEBIAN_FRONTEND=noninteractive

say "Updating apt package index..."
apt-get update -qq

say "Installing core system packages..."
apt-get install -y -qq \
  git \
  python3 \
  python3-venv \
  python3-pip \
  openssl \
  acl \
  bubblewrap \
  curl \
  ca-certificates \
  systemd \
  libpq-dev \
  postgresql-16 \
  postgresql-client-16

say "Verifying Node.js and npm..."
NEED_NODE=1
if command -v node >/dev/null 2>&1; then
  NODE_VER=$(node -v | tr -d 'v' | cut -d. -f1)
  if (( NODE_VER >= 22 )); then
    say "Node.js v$(node -v) is already installed."
    NEED_NODE=0
  fi
fi

if (( NEED_NODE )); then
  say "Installing Node.js 24 LTS via NodeSource..."
  curl -fsSL https://deb.nodesource.com/setup_24.x | bash -
  apt-get install -y -qq nodejs
  say "Installed Node.js $(node -v) and npm $(npm -v)"
fi

say "Preparing isolated application directory layout..."
mkdir -p /opt/aao/repo /opt/aao/frontend /var/log/aao /etc/aao /var/backups/aao
chmod 0755 /opt/aao
chmod 0750 /var/log/aao /etc/aao /var/backups/aao

say "Setting up isolated production Python virtual environment in /opt/aao/venv..."
if [[ ! -d /opt/aao/venv ]]; then
  python3 -m venv /opt/aao/venv
fi
/opt/aao/venv/bin/pip install --quiet --upgrade pip setuptools wheel

say "Dependencies installed successfully."
exit 0
