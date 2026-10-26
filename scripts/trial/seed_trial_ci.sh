#!/usr/bin/env bash
# CEO only (repository administrator), with his own gh login. CEO decision 2026-10-24 (#65, decision 1).
# Seeds the minimal `test` workflow into the disposable trial repository:
#   1. saves the full config of rulesets A, B, C;  2. disables A and B;  3. commits deploy/trial/test.yml;
#   4. re-enables A and B (also on any failure);  5. verifies all three are back exactly as saved.
# Exit 0 only if the protection is restored. If not, STOP the trial and restore by hand from the saved JSON.
#   scripts/trial/seed_trial_ci.sh [OUT_DIR]
set -euo pipefail
umask 077
R=autoaiorg/aao-governance-trial
A=25776805 B=25776806 C=25776807
WF=$(dirname "$0")/../../deploy/trial/test.yml
DATA_HOME=${XDG_DATA_HOME:-$HOME/.local/share}
[[ $DATA_HOME == /* ]] || { echo 'XDG_DATA_HOME must be an absolute path' >&2; exit 2; }
OUT=${1:-$DATA_HOME/aao/evidence/trials/ci-seed/$(date -u +%Y/%m/%dT%H%M%SZ)}
(umask 077; mkdir -p "$OUT")
chmod 700 "$OUT"
norm='del(.updated_at,.created_at,._links,.node_id,.current_user_can_bypass)'
for id in $A $B $C; do gh api "repos/$R/rulesets/$id" --jq "$norm" > "$OUT/ruleset-$id.before.json"; done
for id in $A $B $C; do
  [[ $(jq -r .enforcement "$OUT/ruleset-$id.before.json") == active ]] || { echo "ruleset $id not active before seeding; refusing" >&2; exit 1; }
done
restore() { for id in $A $B; do gh api -X PUT "repos/$R/rulesets/$id" -f enforcement=active >/dev/null || true; done; }
# Every exit after disabling (normal or failure) ends here: all three rulesets must match the saved config exactly,
# otherwise the script fails loudly and the trial must stop (Codex pre-audit, p2p3 A-01).
verify_restored() {
  local id bad=0
  for id in $A $B $C; do
    if gh api "repos/$R/rulesets/$id" --jq "$norm" > "$OUT/ruleset-$id.after.json" && diff -q "$OUT/ruleset-$id.before.json" "$OUT/ruleset-$id.after.json" >/dev/null; then
      echo "ruleset $id restored (identical)"
    else echo "RULESET $id DIFFERS from the saved config (or unreadable)"; diff "$OUT/ruleset-$id.before.json" "$OUT/ruleset-$id.after.json" || true; bad=1; fi
  done | tee -a "$OUT/seed.txt"
  ! grep -q DIFFERS "$OUT/seed.txt" || { echo "PROTECTION NOT RESTORED: stop the trial and restore by hand from $OUT/ruleset-*.before.json" >&2; return 1; }
}
trap 'restore; verify_restored || exit 1' EXIT
for id in $A $B; do gh api -X PUT "repos/$R/rulesets/$id" -f enforcement=disabled >/dev/null; done
sha=$(gh api -X PUT "repos/$R/contents/.github/workflows/test.yml" \
  -f message="ci: minimal test workflow for the P2/P3 trial" -f content="$(base64 -w0 "$WF")" --jq .commit.sha)
echo "workflow commit $sha" | tee "$OUT/seed.txt"
restore; trap - EXIT
verify_restored || exit 1
sha256sum "$OUT"/* | tee "$OUT/SHA256SUMS"
echo "OK: protection restored; evidence in $OUT"
