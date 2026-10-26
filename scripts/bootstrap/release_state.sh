#!/usr/bin/env bash
# Small, shared release-link primitives used by bootstrap and its rollback tests.
set -euo pipefail

aao_capture_active_release() {
  local current_link=$1
  if [[ -L "$current_link" && -d "$current_link" ]]; then
    readlink -f -- "$current_link"
  fi
}

aao_restore_release_links() {
  local root=$1
  local release=$2
  [[ -d "$release" ]] || return 1

  ln -sfn -- "$release" "$root/current.rollback.$$"
  mv -Tf -- "$root/current.rollback.$$" "$root/current"
  if [[ -L "$root/repo" ]]; then
    ln -sfn -- "$root/current" "$root/repo"
  fi
  if [[ -d "$release/venv" ]]; then
    ln -sfn -- "$release/venv" "$root/venv.rollback.$$"
    mv -Tf -- "$root/venv.rollback.$$" "$root/venv"
  fi
}
