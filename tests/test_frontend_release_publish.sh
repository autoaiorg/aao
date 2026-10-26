#!/usr/bin/env bash
set -euo pipefail

ROOT=$(mktemp -d /tmp/aao-frontend-publish-XXXXXX)
trap 'rm -rf -- "$ROOT"' EXIT
mkdir -p "$ROOT/app/dist/assets" "$ROOT/bin" "$ROOT/frontend"
touch "$ROOT/app/package-lock.json"
cat >"$ROOT/bin/npm" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "ci" ]]; then exit 0; fi
if [[ "${FAIL_BUILD:-0}" == 1 ]]; then exit 31; fi
mkdir -p dist/assets
printf '%s' "$BUILD_VERSION" > dist/assets/version.js
printf '<html></html>' > dist/index.html
EOF
chmod +x "$ROOT/bin/npm"
SCRIPT="$(cd "$(dirname "$0")/.." && pwd)/scripts/bootstrap/build_frontend.sh"

publish() {
  BUILD_VERSION="$1" PATH="$ROOT/bin:$PATH" \
    AAO_FRONTEND_APP_DIR="$ROOT/app" AAO_FRONTEND_ROOT="$ROOT/frontend" \
    bash "$SCRIPT" >/dev/null
}

publish one
[[ "$(cat "$ROOT/frontend/dist/assets/version.js")" == one ]]
[[ ! -e "$ROOT/frontend/previous" ]]

publish two
[[ "$(cat "$ROOT/frontend/dist/assets/version.js")" == two ]]
[[ "$(cat "$(readlink -f "$ROOT/frontend/previous")/assets/version.js")" == one ]]

publish three
[[ "$(cat "$ROOT/frontend/dist/assets/version.js")" == three ]]
[[ "$(cat "$(readlink -f "$ROOT/frontend/previous")/assets/version.js")" == two ]]

# Interrupt before the dist link exchange: current assets must remain usable.
mkdir -p "$ROOT/interrupt-bin"
cat >"$ROOT/interrupt-bin/mv" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
destination="${!#}"
if [[ "$destination" == "$INTERRUPT_TARGET" ]]; then
  if [[ "$INTERRUPT_MODE" == before ]]; then
    kill -TERM "$PPID"
    exit 143
  fi
  /usr/bin/mv "$@"
  kill -TERM "$PPID"
  exit 143
fi
exec /usr/bin/mv "$@"
EOF
chmod +x "$ROOT/interrupt-bin/mv"
if BUILD_VERSION=four PATH="$ROOT/interrupt-bin:$ROOT/bin:$PATH" \
  AAO_FRONTEND_APP_DIR="$ROOT/app" AAO_FRONTEND_ROOT="$ROOT/frontend" \
  INTERRUPT_TARGET="$ROOT/frontend/dist" INTERRUPT_MODE=before \
  bash "$SCRIPT" >/dev/null 2>&1; then
  echo "pre-switch interruption unexpectedly succeeded" >&2
  exit 1
fi
[[ "$(cat "$ROOT/frontend/dist/assets/version.js")" == three ]]
[[ -f "$ROOT/frontend/dist/index.html" ]]
[[ "$(cat "$(readlink -f "$ROOT/frontend/previous")/assets/version.js")" == two ]]

# Interrupt immediately after the atomic dist exchange: old assets remain addressable.
if BUILD_VERSION=five PATH="$ROOT/interrupt-bin:$ROOT/bin:$PATH" \
  AAO_FRONTEND_APP_DIR="$ROOT/app" AAO_FRONTEND_ROOT="$ROOT/frontend" \
  INTERRUPT_TARGET="$ROOT/frontend/dist" INTERRUPT_MODE=after \
  bash "$SCRIPT" >/dev/null 2>&1; then
  echo "post-switch interruption unexpectedly succeeded" >&2
  exit 1
fi
[[ "$(cat "$ROOT/frontend/dist/assets/version.js")" == five ]]
[[ "$(cat "$(readlink -f "$ROOT/frontend/previous")/assets/version.js")" == three ]]
[[ -f "$(readlink -f "$ROOT/frontend/previous")/index.html" ]]

if FAIL_BUILD=1 BUILD_VERSION=four PATH="$ROOT/bin:$PATH" \
  AAO_FRONTEND_APP_DIR="$ROOT/app" AAO_FRONTEND_ROOT="$ROOT/frontend" \
  bash "$SCRIPT" >/dev/null 2>&1; then
  echo "failed build unexpectedly succeeded" >&2
  exit 1
fi
[[ "$(cat "$ROOT/frontend/dist/assets/version.js")" == five ]]
[[ "$(cat "$(readlink -f "$ROOT/frontend/previous")/assets/version.js")" == three ]]
echo "frontend release publication and failed-build preservation passed"

# Upgrade an installation whose dist is a real directory. Migration must not
# remove it before the new symlink can be exchanged into place.
mkdir -p "$ROOT/legacy/app/dist/assets" "$ROOT/legacy/frontend/dist/assets"
touch "$ROOT/legacy/app/package-lock.json"
printf legacy > "$ROOT/legacy/frontend/dist/assets/version.js"
printf '<html>legacy</html>' > "$ROOT/legacy/frontend/dist/index.html"
BUILD_VERSION=upgraded PATH="$ROOT/bin:$PATH" \
  AAO_FRONTEND_APP_DIR="$ROOT/legacy/app" AAO_FRONTEND_ROOT="$ROOT/legacy/frontend" \
  bash "$SCRIPT" >/dev/null
[[ -L "$ROOT/legacy/frontend/dist" ]]
[[ "$(cat "$ROOT/legacy/frontend/dist/assets/version.js")" == upgraded ]]
[[ "$(cat "$(readlink -f "$ROOT/legacy/frontend/previous")/assets/version.js")" == legacy ]]
[[ -f "$(readlink -f "$ROOT/legacy/frontend/previous")/index.html" ]]
echo "legacy real-directory migration passed"
