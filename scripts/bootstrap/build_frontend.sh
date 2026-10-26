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

say "Publishing build to $TARGET_DIR atomically..."
PARENT_DIR=$(dirname "$TARGET_DIR")
mkdir -p "$PARENT_DIR"
STAGING_DIR="$PARENT_DIR/.dist_staging_$$"
rm -rf "$STAGING_DIR"
mkdir -p "$STAGING_DIR"
cp -r "$APP_DIR/dist/"* "$STAGING_DIR/"
find "$STAGING_DIR" -type d -exec chmod 0755 {} +
find "$STAGING_DIR" -type f -exec chmod 0644 {} +

if [[ "$TARGET_DIR" == "/opt/aao/frontend/dist" ]]; then
  RELEASES_DIR="/opt/aao/frontend/releases"
  TIMESTAMP=$(date +%Y%m%d%H%M%S)
  RELEASE_DIR="$RELEASES_DIR/build-$TIMESTAMP"
  mkdir -p "$RELEASES_DIR"
  mv "$STAGING_DIR" "$RELEASE_DIR"

  # Atomic symlink swap
  if [[ -e "$TARGET_DIR" && ! -L "$TARGET_DIR" ]]; then
    mv "$TARGET_DIR" "/opt/aao/frontend/dist-legacy-$$"
  fi
  ln -sfn "$RELEASE_DIR" "$TARGET_DIR.tmp"
  mv -Tf "$TARGET_DIR.tmp" "$TARGET_DIR"

  # Update previous pointer
  ln -sfn "$RELEASE_DIR" "/opt/aao/frontend/previous.tmp" 2>/dev/null || true
  mv -Tf "/opt/aao/frontend/previous.tmp" "/opt/aao/frontend/previous" 2>/dev/null || true
else
  # Arbitrary target directory: atomic staging swap
  if [[ -e "$TARGET_DIR" ]]; then
    BACKUP_DIR="$PARENT_DIR/.dist_prev_$$"
    mv "$TARGET_DIR" "$BACKUP_DIR"
    mv "$STAGING_DIR" "$TARGET_DIR"
    rm -rf "$BACKUP_DIR"
  else
    mv "$STAGING_DIR" "$TARGET_DIR"
  fi
fi

say "Control Center compiled and published successfully to $TARGET_DIR."
exit 0
