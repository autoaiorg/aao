#!/usr/bin/env bash
# P1 — one-time identity separation on this host (CEO decision D9, Issue #25).
# Run as alessbarb (NOT with sudo); it asks for your sudo password once.
#
# 1. Extracts the reviewed scripts from commit 38f40e5 (PR #23) and checks
#    their sha256 against the values Codex approved.
# 2. Shows the dry run and waits for your confirmation.
# 3. Applies, then runs the isolation verifier as each role.
# 4. Saves all output to ${XDG_DATA_HOME:-~/.local/share}/aao/evidence/identity-separation/<timestamp>/.
#
# Undo:  sudo <evidence dir>/identity_separation.sh --revert   (lock, keep data)
#        sudo <evidence dir>/identity_separation.sh --purge    (archive + verify, then remove)
set -euo pipefail
umask 077

REPO="$HOME/workspace/repos/active/aao"
COMMIT=38f40e5c35d3a5745b36491ff9c33168ad1743ed
declare -A EXPECTED=(
  [identity_separation.sh]=5115cbc6452b40f8f5e6fe8e41a462291cc96bfc9f5415e0d9fd96f7f2ab2b09
  [verify_identity_separation.sh]=d1259211e27d48b58d982ab658d77ca9c9db6c92f7b4400c2513e7d6e5041c6f
)
ROLES=(aao-pm aao-impl-codex aao-impl-claude aao-impl-ag aao-auditor aao-auditor-alt aao-integrator aao-supervisor aao-notifier)

[[ $EUID -ne 0 ]] || { echo "Run as your normal user, not with sudo." >&2; exit 1; }

DATA_HOME=${XDG_DATA_HOME:-$HOME/.local/share}
[[ $DATA_HOME == /* ]] || { echo 'XDG_DATA_HOME must be an absolute path' >&2; exit 2; }
EVID="$DATA_HOME/aao/evidence/identity-separation/$(date -u +%Y/%m/%dT%H%M%SZ)"
(umask 077; mkdir -p "$EVID"); chmod 700 "$EVID"
# The verifier must be readable by the role accounts, so the scripts go to a
# root-owned, world-readable directory instead of your private home.
STAGE=/opt/aao-p1
exec > >(tee "$EVID/run.log") 2>&1

echo "== 1/4 extract reviewed scripts from $COMMIT"
git -C "$REPO" cat-file -e "$COMMIT^{commit}" 2>/dev/null || git -C "$REPO" fetch -q origin
git -C "$REPO" cat-file -e "$COMMIT^{commit}"
for f in "${!EXPECTED[@]}"; do
  git -C "$REPO" show "$COMMIT:scripts/$f" > "$EVID/$f"
  got=$(sha256sum "$EVID/$f" | cut -d' ' -f1)
  [[ "$got" == "${EXPECTED[$f]}" ]] || { echo "HASH MISMATCH $f: $got" >&2; exit 1; }
  echo "OK  $f  $got"
done
chmod 0755 "$EVID"/*.sh
sudo install -d -o root -g root -m 0755 "$STAGE"
sudo install -o root -g root -m 0755 "$EVID/identity_separation.sh" "$EVID/verify_identity_separation.sh" "$STAGE/"

echo "== 2/4 dry run (no changes)"
"$STAGE/identity_separation.sh"
read -r -p "Apply these changes? Type YES to continue: " answer
[[ "$answer" == YES ]] || { echo "Aborted, nothing changed."; exit 0; }

echo "== 3/4 apply"
sudo "$STAGE/identity_separation.sh" --apply

echo "== 4/4 verify isolation as each role"
fails=0
for r in "${ROLES[@]}"; do
  echo "----- $r"
  if sudo -u "$r" bash "$STAGE/verify_identity_separation.sh"; then :; else fails=$((fails + 1)); fi
done
echo "----- alessbarb (CEO; expected to FAIL: it keeps sudo/docker)"
bash "$STAGE/verify_identity_separation.sh" || true

echo
if (( fails )); then
  echo "RESULT: $fails role(s) FAILED isolation. Paste $EVID/run.log in Issue #25."
else
  echo "RESULT: all ${#ROLES[@]} roles PASSED. Paste $EVID/run.log in Issue #25."
fi
echo "Evidence directory: $EVID"
