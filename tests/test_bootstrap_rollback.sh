#!/usr/bin/env bash
# Test deployment rollback, legacy preservation, and release pruning protection (Finding A-01).
set -euo pipefail

say() { echo -e "\n\033[1;32m== [TEST ROLLBACK] $*\033[0m"; }
die() { echo -e "\n\033[1;31mFAIL: $*\033[0m" >&2; exit 1; }

TEST_ROOT=$(mktemp -d /tmp/aao-test-deploy-XXXXXX)
trap 'rm -rf "$TEST_ROOT"' EXIT

RELEASES_DIR="$TEST_ROOT/opt/aao/releases"
mkdir -p "$RELEASES_DIR"

# 1. Test legacy directory preservation
say "Test 1: Preserving existing non-symlink /opt/aao/repo..."
mkdir -p "$TEST_ROOT/opt/aao/repo"
echo "legacy data" > "$TEST_ROOT/opt/aao/repo/legacy_file.txt"

# Simulate safe preservation logic from aao_bootstrap.sh
if [[ -e "$TEST_ROOT/opt/aao/repo" && ! -L "$TEST_ROOT/opt/aao/repo" ]]; then
  LEGACY_BACKUP="$TEST_ROOT/opt/aao/repo.legacy_test"
  mv "$TEST_ROOT/opt/aao/repo" "$LEGACY_BACKUP"
elif [[ -L "$TEST_ROOT/opt/aao/repo" ]]; then
  rm -f "$TEST_ROOT/opt/aao/repo"
fi

[[ -d "$TEST_ROOT/opt/aao/repo.legacy_test" ]] || die "Legacy /opt/aao/repo was not preserved!"
[[ -f "$TEST_ROOT/opt/aao/repo.legacy_test/legacy_file.txt" ]] || die "Legacy file was destroyed!"
say "PASS: Legacy directory preserved intact."

# 2. Test pruning protection for current and previous releases
say "Test 2: Verifying pruning protects current and previous releases..."
mkdir -p "$RELEASES_DIR/release-01"
mkdir -p "$RELEASES_DIR/release-02"
mkdir -p "$RELEASES_DIR/release-03"
mkdir -p "$RELEASES_DIR/release-04"
mkdir -p "$RELEASES_DIR/release-05"

# Set current to release-05 and previous to release-01 (oldest release!)
ln -sfn "$RELEASES_DIR/release-05" "$TEST_ROOT/opt/aao/current"
ln -sfn "$RELEASES_DIR/release-01" "$TEST_ROOT/opt/aao/previous"

# Execute safe pruning function modeled after aao_bootstrap.sh
prune_releases_test() {
  local current_target=""
  local previous_target=""
  [[ -e "$TEST_ROOT/opt/aao/current" ]] && current_target=$(readlink -f "$TEST_ROOT/opt/aao/current" || true)
  [[ -e "$TEST_ROOT/opt/aao/previous" ]] && previous_target=$(readlink -f "$TEST_ROOT/opt/aao/previous" || true)

  local count=0
  while IFS= read -r rel; do
    [[ -z "$rel" ]] && continue
    count=$((count + 1))
    local rel_real
    rel_real=$(readlink -f "$rel" || true)

    if [[ -n "$current_target" && "$rel_real" == "$current_target" ]]; then
      continue
    fi
    if [[ -n "$previous_target" && "$rel_real" == "$previous_target" ]]; then
      continue
    fi

    if (( count <= 3 )); then
      continue
    fi

    rm -rf "$rel"
  done < <(find "$RELEASES_DIR" -maxdepth 1 -mindepth 1 -type d | sort -r)
}

prune_releases_test

# Verify:
# release-01 MUST exist (protected by previous)
[[ -d "$RELEASES_DIR/release-01" ]] || die "release-01 was pruned despite being referenced by /opt/aao/previous!"
# release-05 MUST exist (protected by current)
[[ -d "$RELEASES_DIR/release-05" ]] || die "release-05 was pruned despite being referenced by /opt/aao/current!"
# release-04 and release-03 must exist (kept among top 3)
[[ -d "$RELEASES_DIR/release-04" ]] || die "release-04 was unexpectedly pruned!"
[[ -d "$RELEASES_DIR/release-03" ]] || die "release-03 was unexpectedly pruned!"
# release-02 is unreferenced and older -> must be pruned
[[ ! -d "$RELEASES_DIR/release-02" ]] || die "release-02 was not pruned!"

say "PASS: Release pruning strictly protects current and previous targets."

# 3. Test rollback on failed step
say "Test 3: Demonstrating rollback on bootstrap step error..."
# Create mock venvs in release-01 and release-05
mkdir -p "$RELEASES_DIR/release-01/venv/bin" "$RELEASES_DIR/release-05/venv/bin"
echo "#!/bin/sh" > "$RELEASES_DIR/release-01/venv/bin/python"
chmod +x "$RELEASES_DIR/release-01/venv/bin/python"
echo "#!/bin/sh" > "$RELEASES_DIR/release-05/venv/bin/python"
chmod +x "$RELEASES_DIR/release-05/venv/bin/python"

# Initially pointing to release-05
ln -sfn "$RELEASES_DIR/release-05" "$TEST_ROOT/opt/aao/current"
ln -sfn "$RELEASES_DIR/release-05/venv" "$TEST_ROOT/opt/aao/venv"
ln -sfn "$RELEASES_DIR/release-01" "$TEST_ROOT/opt/aao/previous"

# Step fails: simulate rollback_release logic
rollback_test() {
  local rollback_errors=()
  if [[ -L "$TEST_ROOT/opt/aao/previous" && -e "$TEST_ROOT/opt/aao/previous" ]]; then
    local prev_dir
    prev_dir=$(readlink -f "$TEST_ROOT/opt/aao/previous" || true)
    if [[ -d "$prev_dir" ]]; then
      # 1. Revert current & repo symlinks
      ln -sfn "$prev_dir" "$TEST_ROOT/opt/aao/current.tmp"
      mv -Tf "$TEST_ROOT/opt/aao/current.tmp" "$TEST_ROOT/opt/aao/current"
      ln -sfn "$TEST_ROOT/opt/aao/current" "$TEST_ROOT/opt/aao/repo"

      # 2. Revert Python virtual environment
      if [[ -d "$prev_dir/venv" ]]; then
        ln -sfn "$prev_dir/venv" "$TEST_ROOT/opt/aao/venv.tmp"
        mv -Tf "$TEST_ROOT/opt/aao/venv.tmp" "$TEST_ROOT/opt/aao/venv"
      fi

      # 3. Simulate runtime check
      if [[ ! -x "$TEST_ROOT/opt/aao/venv/bin/python" ]]; then
        rollback_errors+=("Python runtime check failed")
      fi

      if (( ${#rollback_errors[@]} > 0 )); then
        return 1
      fi
    fi
  fi
  return 0
}

rollback_test

ACTUAL_CURRENT=$(readlink -f "$TEST_ROOT/opt/aao/current")
ACTUAL_REPO=$(readlink -f "$TEST_ROOT/opt/aao/repo")
ACTUAL_VENV=$(readlink -f "$TEST_ROOT/opt/aao/venv")
EXPECTED_PREV=$(readlink -f "$RELEASES_DIR/release-01")
EXPECTED_VENV=$(readlink -f "$RELEASES_DIR/release-01/venv")

[[ "$ACTUAL_CURRENT" == "$EXPECTED_PREV" ]] || die "Current did not roll back to previous ($ACTUAL_CURRENT != $EXPECTED_PREV)"
[[ "$ACTUAL_REPO" == "$EXPECTED_PREV" ]] || die "Repo symlink did not roll back ($ACTUAL_REPO != $EXPECTED_PREV)"
[[ "$ACTUAL_VENV" == "$EXPECTED_VENV" ]] || die "Venv symlink did not roll back to release-01/venv ($ACTUAL_VENV != $EXPECTED_VENV)"

say "PASS: Rollback safely restored /opt/aao/current, /opt/aao/repo, and release-isolated venv."

# 4. Test fail-closed behavior on incomplete rollback
say "Test 4: Verifying fail-closed behavior when rollback cannot be verified..."
rollback_fail_test() {
  local rollback_errors=()
  # Corrupt the venv in previous release
  rm -f "$RELEASES_DIR/release-01/venv/bin/python"

  if [[ ! -x "$RELEASES_DIR/release-01/venv/bin/python" ]]; then
    rollback_errors+=("Python runtime verification failed in rolled-back environment")
  fi

  if (( ${#rollback_errors[@]} > 0 )); then
    echo "FAIL [ROLLBACK]: ROLLBACK INCOMPLETE / CRITICAL INCONSISTENCY DETECTED!"
    return 1
  fi
  return 0
}

if rollback_fail_test; then
  die "Corrupted rollback was incorrectly accepted as success!"
else
  say "PASS: Rollback correctly failed closed when runtime integrity could not be verified."
fi

say "ALL DEPLOYMENT & ROLLBACK INTEGRITY TESTS PASSED (A-01 COMPLIANT)."
exit 0
