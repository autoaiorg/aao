#!/usr/bin/env bash
# The CEO's consolidated privileged steps, in order, stopping at the first failure. Run as the CEO (not root);
# it uses sudo itself. Nothing here is decided by the script: every authorization is an argument the CEO gives.
#
#   ceo_session.sh login-codex
#       Only under CEO-DEC-AUDIT-CODEX-2026-10-24: installs the pinned Codex binary root-owned and logs aao-auditor-alt
#       into its OWN Codex session (device auth, interactive). Never copies a credential.
#   ceo_session.sh audits <REV> <R1_BASE> <TRIAL_BASE> [antigravity|codex]
#       Independent Antigravity audits of REV (r1-chain and p2p3-trial), copies to ~/, verdict replay. Read-only
#       for the trust root. Send the output to the PM; continue only with two APPROVE-TECHNICAL.
#   ceo_session.sh apply <REV> <R1_REPORT_SHA256> [CEO-DEC-AUDIT-CODEX-2026-10-24]
#       Root clone at REV, trust-root upgrade (dry run, then apply, PASS required), full P2/P3 trial (A-13 left
#       running detached), evidence archive in ~/, and the canonical fork-PR approval policy (CEO-DEC-P2P3 §4).
#   ceo_session.sh dictamen <REV> <BASE> [antigravity|codex]
#       Independent Antigravity dictamen on committed trial evidence (prompt p2p3-dictamen).
#   ceo_session.sh a13 <REV> <RUN_ID>
#       Collect the detached A-13 token-expiry result.
set -euo pipefail
[[ $EUID != 0 ]] || { echo 'run as the CEO, not root (sudo is used per step)' >&2; exit 2; }
SESSION_STATE_HOME=${XDG_STATE_HOME:-$HOME/.local/state}
[[ $SESSION_STATE_HOME == /* ]] || { echo 'XDG_STATE_HOME must be an absolute path' >&2; exit 2; }
SESSION_ROOT=${AAO_SESSION_ROOT:-$SESSION_STATE_HOME/aao/sessions}
[[ $SESSION_ROOT == /* ]] || { echo 'AAO_SESSION_ROOT must be an absolute path' >&2; exit 2; }
SESSION_MONTH=$(date -u +%Y/%m)
SESSION_STAMP=$(date -u +%Y%m%dT%H%M%SZ)
(umask 077; mkdir -p -- "$SESSION_ROOT/$SESSION_MONTH")
chmod 700 -- "$SESSION_ROOT"
OUT=$(umask 077; mktemp -d "$SESSION_ROOT/$SESSION_MONTH/$SESSION_STAMP-XXXXXXXX")
# Never read code from a working copy: its .git is agent-writable (hooks, config, replace objects). Every file this
# session installs or runs comes from a private clean clone of the public repository, by exact SHA.
SRC=$OUT/src
g(){ env -i PATH=/usr/bin:/bin HOME=/nonexistent LANG=C.UTF-8 GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 \
       GIT_NO_REPLACE_OBJECTS=1 GIT_TERMINAL_PROMPT=0 git -c core.hooksPath=/dev/null -c core.fsmonitor=false "$@"; }
say(){ printf '\n==== %s\n' "$*" | tee -a "$OUT/session.log"; }
die(){ printf 'STOP: %s\nNothing after this step was run. Send %s/session.log to the PM.\n' "$*" "$OUT" | tee -a "$OUT/session.log" >&2; exit 1; }
sha(){ [[ $1 =~ ^[0-9a-f]{40}$ ]] || die "$2 must be a full 40-hex SHA"; }
fetch_rev(){
  [[ -d $SRC/.git ]] || g clone -q --no-checkout https://github.com/autoaiorg/aao.git "$SRC" || die "cannot clone the public repository"
  g -C "$SRC" cat-file -e "$1^{commit}" || die "revision $1 not found in a fresh clone of autoaiorg/aao"
}
install_audit_runner(){
  for f in scripts/audit/run_agy_audit.sh:0755 scripts/audit/run_codex_audit.sh:0755 docs/audit-prompts/r1-chain.md:0644 docs/audit-prompts/p2p3-trial.md:0644 \
           docs/audit-prompts/p2p3-dictamen.md:0644; do
    g -C "$SRC" show "$1:${f%:*}" | sudo install -o root -g root -m "${f#*:}" /dev/stdin "/opt/aao-audit/$(basename "${f%:*}")"
  done
}
audit(){ # base head prompt [tool]
  local suffix="" runner=run_agy_audit.sh tool=${4:-antigravity}; [[ $3 == r1-chain ]] || suffix="-$3"
  case $tool in antigravity) ;; codex) runner=run_codex_audit.sh;; *) die "unknown auditor tool $tool";; esac
  say "$tool audit $3 of $2 (10-30 min, silent: do not interrupt)"
  sudo -u aao-auditor-alt -H "/opt/aao-audit/$runner" "$1" "$2" "$3" 2>&1 | tee -a "$OUT/session.log" || die "audit $3 failed"
  sudo cat "/home/aao-auditor-alt/aao-audits/$2$suffix/report.md" > "$HOME/aao-agy-audit-$2$suffix.md"
  sudo cat "/home/aao-auditor-alt/aao-audits/$2$suffix/attestation.json" > "$HOME/aao-agy-attest-$2$suffix.json"
  python3 -I - "$HOME/aao-agy-attest-$2$suffix.json" "$HOME/aao-agy-audit-$2$suffix.md" "$2" <<'PY' | tee -a "$OUT/session.log"
import hashlib, json, re, sys
att, report, rev = json.load(open(sys.argv[1])), open(sys.argv[2], "rb").read(), sys.argv[3]
assert att["head"] == att["checked_out_head"] == rev and att["os_user"] == "aao-auditor-alt", "attestation is not for this REV"
assert hashlib.sha256(report).hexdigest() == att["report_sha256"], "report does not match its attestation"
verdicts = {re.sub(r"[\s*`]", "", l.split("Veredicto:", 1)[1]) for l in report.decode().splitlines() if "Veredicto:" in l}
print(f"{att['prompt_name']} ({att['auditor']}): verdict {sorted(verdicts)} report_sha256={att['report_sha256']}")
PY
}

CODEX_SHA256=b93f6811d3f653f0fb83be4050d857fb9abbb111dfa2ce160563327daff7f306
HOST_SHA256=8ee4f472e92ac226a189e98998633b2d07f989f208515750764db660369f2926
case ${1:-} in
  login-codex)
    src=$(readlink -f "$(command -v codex)") || die "no codex binary for this user"
    tmpbin=$(mktemp); cp -- "$src" "$tmpbin"
    [[ $(sha256sum "$tmpbin" | cut -d' ' -f1) == "$CODEX_SHA256" ]] || { rm -f "$tmpbin"; die "$src is not the pinned Codex 0.164.0 release binary"; }
    sudo install -o root -g root -m 0755 "$tmpbin" /usr/local/bin/codex; rm -f "$tmpbin"
    host=$(dirname "$src")/codex-code-mode-host; tmpbin=$(mktemp); cp -- "$host" "$tmpbin"
    [[ $(sha256sum "$tmpbin" | cut -d' ' -f1) == "$HOST_SHA256" ]] || { rm -f "$tmpbin"; die "$host is not the pinned codex-code-mode-host release binary"; }
    sudo install -o root -g root -m 0755 "$tmpbin" /usr/local/bin/codex-code-mode-host; rm -f "$tmpbin"
    say "log aao-auditor-alt into its own Codex session: open the URL, enter the code"
    sudo -u aao-auditor-alt -H sh -c 'umask 077; exec /usr/local/bin/codex login --device-auth'  # never group-writable state
    sudo -u aao-auditor-alt -H /usr/local/bin/codex login status | tee -a "$OUT/session.log" ;;
  audits)
    (($# == 4 || $# == 5)) || die "usage: audits <REV> <R1_BASE> <TRIAL_BASE> [antigravity|codex]"; sha "$2" REV; sha "$3" R1_BASE; sha "$4" TRIAL_BASE
    fetch_rev "$2"; install_audit_runner "$2"
    audit "$3" "$2" r1-chain "${5:-antigravity}"; audit "$4" "$2" p2p3-trial "${5:-antigravity}"
    say "DONE. Send this output to the PM. Do not run 'apply' unless both verdicts are ['APPROVE-TECHNICAL']." ;;
  apply)
    (($# == 3 || $# == 4)) || die "usage: apply <REV> <R1_REPORT_SHA256> [CEO-DEC-AUDIT-CODEX-2026-10-24]"; sha "$2" REV; fetch_rev "$2";
    EXC=(); [[ -z ${4:-} ]] || EXC=(--audit-exception "$4")
    [[ $3 =~ ^[0-9a-f]{64}$ ]] || die "R1_REPORT_SHA256 must be 64 hex"
    REV=$2 RH=$3
    say "1/5 root clone at $REV"
    if sudo test -e /root/aao-src; then sudo mv /root/aao-src "/root/aao-src.old-$(date +%Y%m%dT%H%M%S)"; fi
    sudo env -i PATH=/usr/bin:/bin HOME=/root GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 GIT_NO_REPLACE_OBJECTS=1 \
      git -c core.hooksPath=/dev/null clone -q https://github.com/autoaiorg/aao.git /root/aao-src
    sudo git -C /root/aao-src -c advice.detachedHead=false checkout -q "$REV"
    [[ $(sudo git -C /root/aao-src rev-parse HEAD) == "$REV" ]] || die "root clone is not at $REV"
    [[ $(sudo sha256sum "/home/aao-auditor-alt/aao-audits/$REV/report.md" | cut -d' ' -f1) == "$RH" ]] || die "the r1-chain report is not the one you pinned"
    B=(sudo /root/aao-src/scripts/bootstrap/host_bootstrap.sh --rev "$REV" --ceo-user "$USER")
    say "2/5 trust-root upgrade: dry run"
    "${B[@]}" --trust-root-upgrade --loop-repo autoaiorg/aao-governance-trial --audit-report-sha256 "$RH" "${EXC[@]}" 2>&1 | tee "$OUT/upgrade-dry.log" \
      || die "upgrade dry run failed"
    grep -q "audit verdict \['APPROVE-TECHNICAL'\]" "$OUT/upgrade-dry.log" || die "dry run did not accept the audit"
    say "3/5 trust-root upgrade: apply"
    "${B[@]}" --apply --trust-root-upgrade --loop-repo autoaiorg/aao-governance-trial --audit-report-sha256 "$RH" "${EXC[@]}" 2>&1 | tee "$OUT/upgrade.log" \
      || die "upgrade failed (see the rollback instructions printed above)"
    grep -q '^RESULT: PASS' "$OUT/upgrade.log" && grep -q "^upgraded .* -> $REV" "$OUT/upgrade.log" || die "upgrade did not end with verifier PASS"
    say "4/5 full P2/P3 trial (30-60 min; A-13 keeps running ~62 min detached)"
    set +e; sudo /root/aao-src/scripts/trial/run_trial.sh --rev "$REV" 2>&1 | tee "$OUT/trial.log"; trial_rc=${PIPESTATUS[0]}; set -e
    TS=$(sudo ls -t /var/log/aao-trial | head -1)
    sudo tar -C /var/log/aao-trial -czf "$OUT/aao-trial-$TS.tgz" "$TS" && sudo chown "$USER": "$OUT/aao-trial-$TS.tgz"
    echo "trial exit=$trial_rc run_id=$TS (FAIL lines are results for the PM to analyse, not a reason to stop)" | tee -a "$OUT/session.log"
    ((trial_rc != 99)) || die "the trial could not restore ruleset A (exit 99): fix that before anything else"
    say "5/5 canonical fork-PR approval policy -> all_external_contributors (CEO-DEC-P2P3 §4)"
    g -C "$SRC" show "$REV:scripts/governance/canonical_protection.py" > "$OUT/canonical_protection.py"
    python3 -I "$OUT/canonical_protection.py" --repo autoaiorg/aao approval 2>&1 | tee -a "$OUT/session.log" \
      || die "approval policy not set"
    say "DONE. Send $OUT (session.log, trial.log, aao-trial-$TS.tgz) to the PM. A-13: '$0 a13 $REV $TS' in ~65 min." ;;
  dictamen)
    (($# == 3 || $# == 4)) || die "usage: dictamen <REV> <BASE> [antigravity|codex]"; sha "$2" REV; sha "$3" BASE
    fetch_rev "$2"; install_audit_runner "$2"; audit "$3" "$2" p2p3-dictamen "${4:-antigravity}"
    say "DONE. Send this output to the PM." ;;
  a13)
    (($# == 3)) || die "usage: a13 <REV> <RUN_ID>"; sha "$2" REV
    sudo /root/aao-src/scripts/trial/run_trial.sh --rev "$2" --a13-collect "$3" 2>&1 | tee -a "$OUT/session.log" ;;
  *) sed -n '2,20p' "$0"; exit 2 ;;
esac
