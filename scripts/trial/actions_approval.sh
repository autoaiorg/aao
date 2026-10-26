#!/usr/bin/env bash
# CEO only, own gh login. CEO decision 2026-10-24 (#65, decision 4): on the trial repository, require
# approval before running workflows from ALL outside contributors (P3-10 depends on it). Saves before/after.
set -euo pipefail
umask 077
R=autoaiorg/aao-governance-trial
DATA_HOME=${XDG_DATA_HOME:-$HOME/.local/share}
[[ $DATA_HOME == /* ]] || { echo 'XDG_DATA_HOME must be an absolute path' >&2; exit 2; }
OUT=${1:-$DATA_HOME/aao/evidence/trials/actions/$(date -u +%Y/%m/%dT%H%M%SZ)}
(umask 077; mkdir -p "$OUT"); chmod 700 "$OUT"
P=repos/$R/actions/permissions
gh api "$P/fork-pr-contributor-approval" > "$OUT/approval.before.json"
gh api "$P/workflow" > "$OUT/workflow-token.before.json"
gh api -X PUT "$P/fork-pr-contributor-approval" -f approval_policy=all_external_contributors
gh api "$P/fork-pr-contributor-approval" | tee "$OUT/approval.after.json"
gh api "$P/workflow" | tee "$OUT/workflow-token.after.json"
[[ $(jq -r .approval_policy "$OUT/approval.after.json") == all_external_contributors ]] || { echo "approval policy NOT set" >&2; exit 1; }
[[ $(jq -r .default_workflow_permissions "$OUT/workflow-token.after.json") == read ]] || { echo "workflow token is not read-only" >&2; exit 1; }
sha256sum "$OUT"/*.json | tee "$OUT/SHA256SUMS"; echo "OK: evidence in $OUT"
