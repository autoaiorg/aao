#!/usr/bin/env bash
# Export one exact, clean Git revision into an empty release directory.
set -euo pipefail

die() { echo "FAIL [RELEASE SOURCE]: $*" >&2; exit 1; }

[[ $# == 3 ]] || die "Usage: stage_release_source.sh <repo-dir> <revision> <empty-release-dir>"
REPO_DIR=$1
REV=$2
RELEASE_DIR=$3

[[ "$REV" =~ ^[0-9a-f]{40}$ ]] || die "Revision must be a full 40-character commit SHA."
[[ -d "$REPO_DIR" ]] || die "Repository directory does not exist."
[[ -d "$RELEASE_DIR" ]] || die "Release directory does not exist."
[[ -z "$(find "$RELEASE_DIR" -mindepth 1 -maxdepth 1 -print -quit)" ]] \
  || die "Release directory must be empty."

git -C "$REPO_DIR" cat-file -e "$REV^{commit}" 2>/dev/null \
  || die "Revision is not available as a commit in the source repository."
if ! git -C "$REPO_DIR" diff --quiet "$REV" -- .; then
  die "Tracked source differs from requested revision; refusing mismatched bootstrap and release code."
fi

# `git archive` includes only tracked files from the verified commit, excluding
# ignored/untracked credentials, generated artifacts, and developer state.
git -C "$REPO_DIR" archive --format=tar "$REV" | tar -xf - -C "$RELEASE_DIR"
