#!/usr/bin/env bash
# Build and publish production React Control Center for AAO.
set -euo pipefail

say() { echo "== [FRONTEND] $*"; }
die() { echo "FAIL [FRONTEND]: $*" >&2; exit 1; }

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
REPO_DIR=$(cd "$SCRIPT_DIR/../.." && pwd)

if [[ -d "/opt/aao/current/frontend/app" ]]; then
  APP_DIR="/opt/aao/current/frontend/app"
else
  APP_DIR="$REPO_DIR/frontend/app"
fi
TARGET_DIR="${AAO_STATIC_DIR:-/opt/aao/frontend/dist}"

say "Compiling Control Center from $APP_DIR..."
[[ -d "$APP_DIR" ]] || die "Frontend directory $APP_DIR does not exist."

cd "$APP_DIR"
say "Installing npm dependencies cleanly..."
npm ci --no-audit

say "Running production build (tsc && vite build)..."
npm run build

[[ -f "$APP_DIR/dist/index.html" ]] || die "Build failed: $APP_DIR/dist/index.html missing."
[[ -d "$APP_DIR/dist/assets" ]] || die "Build failed: $APP_DIR/dist/assets missing."

say "Publishing build to $TARGET_DIR..."
mkdir -p "$TARGET_DIR"
rm -rf "${TARGET_DIR:?}"/*
cp -r "$APP_DIR/dist/"* "$TARGET_DIR/"

find "$TARGET_DIR" -type d -exec chmod 0755 {} +
find "$TARGET_DIR" -type f -exec chmod 0644 {} +

say "Control Center compiled and published successfully to $TARGET_DIR."
exit 0
