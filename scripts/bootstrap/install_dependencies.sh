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
  gnupg \
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
  say "Configuring NodeSource repository with verified GPG keyring..."
  mkdir -p /etc/apt/keyrings
  if [[ ! -f /etc/apt/keyrings/nodesource.gpg ]]; then
    curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg
  fi
  echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_22.x nodistro main" > /etc/apt/sources.list.d/nodesource.list
  apt-get update -qq
  apt-get install -y -qq nodejs
  say "Installed Node.js $(node -v) and npm $(npm -v)"
fi

say "Preparing isolated application directory layout..."
mkdir -p /opt/aao/repo /opt/aao/frontend /var/log/aao /etc/aao /var/backups/aao
chmod 0755 /opt/aao
chmod 0750 /var/log/aao /etc/aao /var/backups/aao

say "Setting up base Python virtual environment in /opt/aao/base_venv..."
if [[ ! -d /opt/aao/base_venv ]]; then
  if [[ -d /opt/aao/venv && ! -L /opt/aao/venv ]]; then
    mv /opt/aao/venv /opt/aao/base_venv
  else
    python3 -m venv /opt/aao/base_venv
  fi
  /opt/aao/base_venv/bin/pip install --quiet --upgrade pip setuptools wheel
fi
if [[ ! -e /opt/aao/venv ]]; then
  ln -sfn /opt/aao/base_venv /opt/aao/venv
fi

say "Dependencies installed successfully."
exit 0
