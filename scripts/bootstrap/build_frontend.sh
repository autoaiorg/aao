#!/usr/bin/env bash
# Build and publish production React Control Center for AAO.
set -euo pipefail

say() { echo "== [FRONTEND] $*"; }
die() { echo "FAIL [FRONTEND]: $*" >&2; exit 1; }

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
REPO_DIR=$(cd "$SCRIPT_DIR/../.." && pwd)

if [[ -n "${AAO_FRONTEND_APP_DIR:-}" ]]; then
  APP_DIR="$AAO_FRONTEND_APP_DIR"
elif [[ -d "/opt/aao/current/frontend/app" ]]; then
  APP_DIR="/opt/aao/current/frontend/app"
else
  APP_DIR="$REPO_DIR/frontend/app"
fi
FRONTEND_ROOT="${AAO_FRONTEND_ROOT:-/opt/aao/frontend}"
TARGET_DIR="${AAO_STATIC_DIR:-$FRONTEND_ROOT/dist}"

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
STAGING_DIR=$(mktemp -d "$PARENT_DIR/.dist_staging_XXXXXXXX")
cleanup() {
  if [[ -n "${STAGING_DIR:-}" && -e "$STAGING_DIR" ]]; then
    rm -rf -- "$STAGING_DIR"
  fi
  return 0
}
trap cleanup EXIT
cp -r "$APP_DIR/dist/"* "$STAGING_DIR/"
find "$STAGING_DIR" -type d -exec chmod 0755 {} +
find "$STAGING_DIR" -type f -exec chmod 0644 {} +

if [[ "$TARGET_DIR" == "$FRONTEND_ROOT/dist" ]]; then
  RELEASES_DIR="$FRONTEND_ROOT/releases"
  mkdir -p "$RELEASES_DIR"
  RELEASE_DIR=$(mktemp -d "$RELEASES_DIR/build-XXXXXXXX")
  rmdir "$RELEASE_DIR"
  mkdir -p "$RELEASES_DIR"
  mv "$STAGING_DIR" "$RELEASE_DIR"
  STAGING_DIR=""

  # Preserve the currently served release before switching dist. If interrupted
  # before the switch, dist remains live; after it, previous names the old dist.
  CURRENT_RELEASE=""
  if [[ -L "$TARGET_DIR" ]]; then
    CURRENT_RELEASE=$(readlink -f -- "$TARGET_DIR")
  elif [[ -d "$TARGET_DIR" ]]; then
    # Migrate an existing real dist without an absence window. Exchange it
    # atomically with the fully-built symlink; the old directory is left at
    # the temporary path and then retained as a rollback release.
    MIGRATION_LINK="$TARGET_DIR.migrate.$$"
    OLD_DIST="$FRONTEND_ROOT/.dist-legacy-$$"
    ln -s -- "$RELEASE_DIR" "$MIGRATION_LINK"
    python3 - "$TARGET_DIR" "$MIGRATION_LINK" <<'PY'
import ctypes
import os
import sys

libc = ctypes.CDLL(None, use_errno=True)
renameat2 = libc.renameat2
renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
renameat2.restype = ctypes.c_int
AT_FDCWD = -100
RENAME_EXCHANGE = 2
left, right = (os.fsencode(p) for p in sys.argv[1:])
if renameat2(AT_FDCWD, left, AT_FDCWD, right, RENAME_EXCHANGE) != 0:
    error = ctypes.get_errno()
    raise OSError(error, os.strerror(error))
PY
    mv -- "$MIGRATION_LINK" "$OLD_DIST"
    CURRENT_RELEASE="$OLD_DIST"
  fi

  if [[ -n "$CURRENT_RELEASE" && -d "$CURRENT_RELEASE" ]]; then
    ln -s -- "$CURRENT_RELEASE" "$FRONTEND_ROOT/previous.tmp.$$"
    mv -Tf -- "$FRONTEND_ROOT/previous.tmp.$$" "$FRONTEND_ROOT/previous"
  fi

  # Atomic symlink swap; release directory is complete before becoming visible.
  ln -s -- "$RELEASE_DIR" "$TARGET_DIR.tmp.$$"
  mv -Tf -- "$TARGET_DIR.tmp.$$" "$TARGET_DIR"
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
