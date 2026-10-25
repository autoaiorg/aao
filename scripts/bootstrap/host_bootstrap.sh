#!/bin/bash -p
# Bootstrap an AAO host from zero, by chaining the reviewed pieces in this repository.
#
# Run ONLY as root, from a root-owned clone checked out at the exact REV (see
# docs/procedures/HOST_BOOTSTRAP.md for the stub that makes that clone). Never from a
# working tree an agent can write.
#
#   host_bootstrap.sh --rev <40-hex> --ceo-user <name> [--apply] [phases/options]
#
# Phases (in order; each ends with its own check and stops on failure):
#   identities   P1 accounts, groups, directories, auditor keys   (scripts/identity_separation.sh)
#   app-keys     each GitHub App key into its uid's ~/.config/aao  (--keys-dir, root-owned 0700)
#   p2-verify    the nine Apps authenticate, permissions = manifests, exact repo scope (9/9 required)
#   antigravity  root copy of agy, audit runner + pinned prompt, read-only allowlist for aao-auditor-alt
#   trust-root   OPT-IN (--trust-root): frozen trees, units, supervisor/integrator keys, anchor,
#                registry (RA PENDING), verifier PASS, auditor dispatch. The integrator stays OFF.
#   trust-root-upgrade  OPT-IN (--trust-root-upgrade): move an INSTALLED trust root to a newer audited REV:
#                backs up config + frozen trees, keeps keys, ledger and ledger.anchor, regenerates the
#                registry (optionally --ra-status RA-0x=PASS, a CEO decision), verifier PASS, dispatch back on.
#   integrator   OPT-IN (--enable-integrator): only if every RA in the installed registry is PASS and the served
#                repository's rulesets verify exactly (scripts/governance/canonical_protection.py verify).
#   --audit-exception CEO-DEC-...: accept a substitute (codex) attestation only for that recorded CEO exception.
#
# Default is a dry run that prints what it would do. Fail closed. Phases 1-4 are re-runnable and never
# regenerate an existing key; the trust-root phase runs only on a host with no trust-root artifact at all.
set -euo pipefail
# Privileged mode (-p, in the shebang) makes bash ignore BASH_ENV/ENV, SHELLOPTS and every function
# in the environment before this line runs. Then a fixed PATH and IFS; nothing can skip this.
[[ $- == *p* ]] || { echo "FAIL: run as $0 (privileged mode), not through another shell" >&2; exit 1; }
# Children (identity_separation.sh, python, runuser) would still see the caller's environment, including
# exported functions. If it holds anything beyond the minimum, start over with an empty one.
if /usr/bin/env | /usr/bin/grep -qvE '^(PATH=/usr/sbin:/usr/bin:/sbin:/bin|HOME=/root|LANG=C\.UTF-8|PWD=.*|SHLVL=[0-9]+|_=.*)$'; then
  exec /usr/bin/env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin HOME=/root LANG=C.UTF-8 "$0" "$@"
fi
export PATH=/usr/sbin:/usr/bin:/sbin:/bin HOME=/root LANG=C.UTF-8; IFS=$' \t\n'; hash -r
unset BASH_ENV ENV CDPATH GLOBIGNORE PYTHONPATH PYTHONHOME PYTHONSTARTUP LD_PRELOAD LD_LIBRARY_PATH
umask 022

die() { echo "FAIL: $*" >&2; exit 1; }
say() { echo "== $*"; }
APPLY=0 REV="" CEO="" KEYS_DIR="" AGY_SRC="" AGY_SHA="" REPORT_SHA="" AUDIT_EXCEPTION="" TRUST_ROOT=0 LOOP_REPO="" ENABLE_INTEGRATOR=0 UPGRADE=0 RA_ARGS=()
while [[ $# -gt 0 ]]; do
  case $1 in
    --apply) APPLY=1;;
    --rev) REV=$2; shift;;
    --ceo-user) CEO=$2; shift;;
    --keys-dir) KEYS_DIR=$2; shift;;
    --agy) AGY_SRC=$2; shift;;
    --agy-sha256) AGY_SHA=$2; shift;;
    --trust-root) TRUST_ROOT=1;;
    --trust-root-upgrade) UPGRADE=1;;
    --ra-status) [[ ${2:-} =~ ^(RA-0[12379])=(PASS|PENDING)$ ]] || die "--ra-status RA-0x=PASS|PENDING"
      [[ " ${RA_ARGS[*]} " != *" ${BASH_REMATCH[1]}="* ]] || die "duplicate --ra-status ${BASH_REMATCH[1]}"
      RA_ARGS+=(--ra-status "$2"); shift;;
    --audit-report-sha256) REPORT_SHA=$2; shift;;
    --audit-exception) AUDIT_EXCEPTION=$2; shift;;
    --loop-repo) LOOP_REPO=$2; shift;;
    --enable-integrator) ENABLE_INTEGRATOR=1;;
    *) die "unknown option $1 (see the header of $0)";;
  esac
  shift
done
run() { if ((APPLY)); then "$@"; else printf 'DRY:'; printf ' %q' "$@"; echo; fi; }

# ---------- 0. preflight ----------
say "preflight"
[[ $EUID -eq 0 ]] || die "run as root"
[[ $REV =~ ^[0-9a-f]{40}$ ]] || die "--rev must be a full 40-hex SHA"
[[ -n $CEO ]] && getent passwd "$CEO" >/dev/null || die "--ceo-user must name an existing account"
SRC=$(cd "$(dirname "$0")/../.." && pwd)
# Every git call: no system/global config, no hooks, no replace refs, no prompt.
g() { env -i PATH=/usr/bin:/bin HOME=/nonexistent LANG=C.UTF-8 GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 \
        GIT_NO_REPLACE_OBJECTS=1 GIT_TERMINAL_PROMPT=0 git -c core.hooksPath=/dev/null -c safe.directory="*" "$@"; }
# A plain clone (.git is a directory, not a worktree pointer), entirely root's, nothing group/other-writable.
[[ -d $SRC/.git && ! -L $SRC/.git ]] || die "$SRC/.git must be a directory (a plain clone, not a worktree)"
[[ -z $(find "$SRC" \( ! -uid 0 -o \( ! -type l -perm /022 \) \) -print -quit) ]] || die "$SRC must be entirely root-owned and not group/other-writable"
[[ $(g -C "$SRC" rev-parse HEAD) == "$REV" ]] || die "$SRC is not checked out at $REV"
[[ -z $(g -C "$SRC" status --porcelain) ]] || die "$SRC has local changes"
for tool in git python3 openssl systemctl systemd-tmpfiles runuser install getfacl; do command -v $tool >/dev/null || die "missing $tool (packages: git python3 python3-venv openssl systemd acl)"; done
python3 -c 'import venv, ensurepip' 2>/dev/null || die "python3-venv is missing"
gv=$(git --version | awk '{print $3}'); [[ $(printf '%s\n2.38\n' "$gv" | sort -V | head -1) == 2.38 ]] || die "git >= 2.38 required (merge-tree --write-tree), found $gv"
REGISTRY=$SRC/deploy/github-apps/aao-github-apps-registry.json
LOG=/var/log/aao-bootstrap/$(date +%Y%m%dT%H%M%S); ((APPLY)) && install -d -m 0755 "$LOG" || LOG=$(mktemp -d)
echo "rev=$REV ceo=$CEO src=$SRC apply=$APPLY log=$LOG"
# Fork scope of each implementer App (verify_app_auth --fork). Change here if the forks move.
# Space-separated: production fork, then trial fork (parent <owner>/aao-governance-trial).
declare -A FORKS=([aao-impl-claude]="autoaiorg/aao-claude autoaiorg/aao-trial-claude"
                  [aao-impl-codex]="autoaiorg/aao-codex autoaiorg/aao-trial-codex"
                  [aao-impl-agy]="autoaiorg/aao-agy autoaiorg/aao-trial-agy")
apps() { python3 -I -c 'import json,sys
for a in json.load(open(sys.argv[1]))["apps"]: print(a["name"], a["linux_uid"], a["key_file"], int(a["app_id"]))' "$REGISTRY"; }

# ---------- 1. identities ----------
say "identities (P1)"
if ((APPLY)); then CEO_USER=$CEO "$SRC/scripts/identity_separation.sh" --apply; else CEO_USER=$CEO "$SRC/scripts/identity_separation.sh"; fi

# ---------- 2. App keys ----------
say "app-keys"
if [[ -n $KEYS_DIR ]]; then
  kd=$(realpath -e "$KEYS_DIR")
  [[ $kd != /home/* && $kd != /tmp/* ]] || die "--keys-dir must be outside /home and /tmp (agents can read those)"
  [[ $(stat -c '%u %a' "$kd") == "0 700" ]] || die "--keys-dir must be root:0700"
fi
missing=0
while read -r app uid key _; do
  if ! home=$(getent passwd "$uid" | cut -d: -f6); then
    ((APPLY)) && die "no account $uid"
    echo "pend $app key (account $uid is created by the identities phase)"; continue
  fi
  [[ $key == "$home/.config/aao/$app.pem" ]] || die "registry key_file for $app is not $home/.config/aao/$app.pem"
  # No component of the key path may be a symlink (stat without -L does not follow links).
  for c in "$home" "$home/.config" "$home/.config/aao" "$key"; do
    [[ ! -L $c ]] || die "$c is a symlink"
  done
  if [[ -e $key ]]; then
    [[ $(stat -c '%F %U %a' "$key") == "regular file $uid 600" ]] || die "$key exists but is not a $uid:0600 regular file"
    echo "ok   $app key present"; continue
  fi
  if [[ -n $KEYS_DIR && -e $kd/$app.pem ]]; then
    [[ $(stat -c '%F %u' "$kd/$app.pem") == "regular file 0" ]] || die "$kd/$app.pem must be a root-owned regular file"
    # A .config created by root (e.g. by an earlier manual install) is handed to the uid; never through a link.
    if [[ -d $home/.config && $(stat -c %u "$home/.config") == 0 ]]; then run chown "$uid:$uid" "$home/.config"; fi
    # Every write inside the home is done AS the uid, and the key travels on stdin: a planted link can only
    # reach what that uid could already write.
    run runuser -u "$uid" -- /usr/bin/install -d -m 0700 "$home/.config" "$home/.config/aao"
    if ((APPLY)); then runuser -u "$uid" -- /bin/sh -c 'umask 077 && set -C && cat > "$1"' sh "$key" < "$kd/$app.pem"; fi
    echo "new  $app key installed for $uid"
  else
    echo "MISSING $app key ($key)"; missing=1
  fi
done < <(apps)
((missing == 0 || APPLY == 0)) || die "App keys missing: put <app>.pem in --keys-dir (see HOST_BOOTSTRAP.md)"
# GitHubAppClient reads the app_id from ~/.config/aao/<app>.json (not secret). Written as the uid, never overwritten.
while read -r app uid _ id; do
  home=$(getent passwd "$uid" | cut -d: -f6) || continue
  meta=$home/.config/aao/$app.json
  [[ ! -L $meta ]] || die "$meta is a symlink"
  if [[ -e $meta ]]; then echo "ok   $app metadata present"; continue; fi
  if ((APPLY)); then printf '{"id": %d}\n' "$id" | runuser -u "$uid" -- /bin/sh -c 'umask 077 && set -C && cat > "$1"' sh "$meta"; fi
  echo "new  $app metadata (app_id $id) for $uid"
done < <(apps)

# ---------- 3. P2 verification ----------
say "p2-verify (9/9 required)"
run install -d -o root -g root -m 0755 /opt/aao-p2 /opt/aao-p2/github-apps
run install -o root -g root -m 0755 "$SRC/scripts/github_apps/verify_app_auth.py" /opt/aao-p2/
run install -o root -g root -m 0644 "$REGISTRY" /opt/aao-p2/
for m in "$SRC"/docs/proposals/github-apps/*.json; do run install -o root -g root -m 0644 "$m" /opt/aao-p2/github-apps/; done
if ((APPLY)); then
  pass=0
  while read -r app uid _; do
    extra=(); for f in ${FORKS[$app]:-}; do extra+=(--fork "$f"); done
    if runuser -u "$uid" -- env -i HOME="$(getent passwd "$uid" | cut -d: -f6)" PATH=/usr/bin:/bin \
         /usr/bin/python3 -I /opt/aao-p2/verify_app_auth.py "$app" "${extra[@]}" >> "$LOG/app-auth.jsonl"; then
      pass=$((pass + 1))
    fi
  done < <(apps)
  echo "app auth: $pass/9 ($LOG/app-auth.jsonl)"; [[ $pass == 9 ]] || die "App verification not 9/9"
fi

# ---------- 4. Antigravity (alternate auditor) ----------
say "antigravity"
# agy comes from a path agents may control, so it is installed only against a hash the CEO supplies:
# copy once into a root-only temp file, hash that copy, install that same copy.
if [[ -n $AGY_SRC ]]; then
  [[ $AGY_SHA =~ ^[0-9a-f]{64}$ ]] || die "--agy needs --agy-sha256 <hex> (the hash of the agy binary you trust)"
  tmp_agy=$(mktemp); cp --no-dereference -- "$AGY_SRC" "$tmp_agy"; [[ -f $tmp_agy && ! -L $tmp_agy ]] || die "$AGY_SRC is not a regular file"
  [[ $(sha256sum "$tmp_agy" | cut -d' ' -f1) == "$AGY_SHA" ]] || { rm -f "$tmp_agy"; die "agy sha256 does not match --agy-sha256"; }
  run install -o root -g root -m 0755 "$tmp_agy" /usr/local/bin/agy; rm -f "$tmp_agy"
elif [[ -f /usr/local/bin/agy ]]; then
  echo "ok   /usr/local/bin/agy present sha256=$(sha256sum /usr/local/bin/agy | cut -d' ' -f1)"
else
  echo "TODO no /usr/local/bin/agy: rerun with --agy <path> --agy-sha256 <hex>"
fi
run install -d -o root -g root -m 0755 /opt/aao-audit
run install -o root -g root -m 0755 "$SRC/scripts/audit/run_agy_audit.sh" "$SRC/scripts/audit/run_codex_audit.sh" /opt/aao-audit/
for pr in "$SRC"/docs/audit-prompts/*.md; do run install -o root -g root -m 0644 "$pr" /opt/aao-audit/; done
alt_home=$(getent passwd aao-auditor-alt | cut -d: -f6 || true)
[[ -n $alt_home ]] || { ((APPLY)) && die "no account aao-auditor-alt"; alt_home=/home/aao-auditor-alt; }
# Only single read-only git commands; agy denies everything else in print mode (see the audit prompt).
run runuser -u aao-auditor-alt -- env -i HOME="$alt_home" PATH=/usr/bin:/bin /usr/bin/python3 -I -c '
import json, os
p = os.path.expanduser("~/.gemini/antigravity-cli/settings.json")
os.makedirs(os.path.dirname(p), mode=0o700, exist_ok=True)
d = json.load(open(p)) if os.path.exists(p) else {}
d.setdefault("permissions", {})["allow"] = ["command(git diff)", "command(git show)", "command(git log)",
                                            "command(git ls-files)", "command(git grep)"]
fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
os.write(fd, (json.dumps(d, indent=1) + "\n").encode()); os.close(fd)'
if [[ -n $(getent passwd aao-auditor-alt) ]] && runuser -u aao-auditor-alt -- test -s "$alt_home/.gemini/antigravity-cli/antigravity-oauth-token"; then
  echo "ok   agy session present for aao-auditor-alt"
else
  echo "TODO agy login (interactive, once):"
  echo "     sudo -u aao-auditor-alt -H env -i HOME=$alt_home PATH=/usr/bin:/bin:/usr/local/bin /usr/local/bin/agy"
  echo "     Join the printed URL into ONE line before opening it."
fi

# ---------- 5. trust root (opt-in) ----------
((TRUST_ROOT && UPGRADE)) && die "--trust-root (fresh host) and --trust-root-upgrade are exclusive"
((${#RA_ARGS[@]} == 0 || UPGRADE)) || die "--ra-status is only accepted with --trust-root-upgrade"
check_audit() {
  [[ $LOOP_REPO =~ ^[A-Za-z0-9-]+/[A-Za-z0-9._-]+$ ]] || die "--loop-repo OWNER/REPO is required (the repo the R1 loop serves)"
  # The CEO authorizes the trust root (§12.3 op. 1) by pinning the exact audit report they read.
  [[ $REPORT_SHA =~ ^[0-9a-f]{64}$ ]] || die "--audit-report-sha256 <sha256 of the report.md you read> is required"
  # The independent audit of this exact REV, where only aao-auditor-alt can write it.
  A=$alt_home/aao-audits/$REV
  for f in "$A" "$A/attestation.json" "$A/report.md"; do
    [[ ! -L $f && $(stat -c %U "$f" 2>/dev/null) == aao-auditor-alt && $(( 0$(stat -c %a "$f") & 022 )) == 0 ]] \
      || die "$f missing, a symlink, or not exclusively aao-auditor-alt's: run the Antigravity audit of $REV first"
  done
  # One root-owned snapshot of both files; every check below reads only that snapshot (no swap in between).
  snap=$(mktemp -d); cat -- "$A/attestation.json" > "$snap/attestation.json"; cat -- "$A/report.md" > "$snap/report.md"
  [[ $(sha256sum "$snap/report.md" | cut -d' ' -f1) == "$REPORT_SHA" ]] || die "$A/report.md is not the report you pinned"
  # The independent auditor is Antigravity. A substitute auditor is accepted only for a CEO exception that the
  # CEO names explicitly here AND that is recorded at REV naming that auditor (CEO-DEC-AUDIT-CODEX-2026-10-24).
  allowed=antigravity
  if [[ -n $AUDIT_EXCEPTION ]]; then
    [[ $AUDIT_EXCEPTION =~ ^CEO-DEC-[A-Z0-9-]+$ && -f $SRC/docs/decisions/$AUDIT_EXCEPTION.md ]] \
      || die "--audit-exception $AUDIT_EXCEPTION is not a decision recorded at $REV"
    grep -q '^auditor_sustituto: codex$' "$SRC/docs/decisions/$AUDIT_EXCEPTION.md" || die "$AUDIT_EXCEPTION does not name codex"
    allowed=antigravity,codex; echo "AUDIT EXCEPTION $AUDIT_EXCEPTION: a codex attestation is accepted in place of antigravity"
  fi
  python3 -I - "$snap/attestation.json" "$snap/report.md" "$REV" "$allowed" "$AUDIT_EXCEPTION" <<'PY' || die "the audit of $REV does not authorize the trust root"
import hashlib, json, re, sys
att, report, rev = json.load(open(sys.argv[1])), open(sys.argv[2], "rb").read(), sys.argv[3]
allowed, exception = sys.argv[4].split(","), sys.argv[5]
assert att["head"] == att["checked_out_head"] == rev and att["os_user"] == "aao-auditor-alt" and att["auditor"] in allowed, "attestation is not for this REV or auditor"
assert att["auditor"] == "antigravity" or att.get("exception") == exception, "substitute attestation does not carry the CEO exception id"
assert hashlib.sha256(report).hexdigest() == att["report_sha256"], "report.md does not match the attestation"
# Every verdict line, whole: after "Veredicto:" only markdown (spaces, *, `) may surround the word.
verdicts = {re.sub(r"[\s*`]", "", line.split("Veredicto:", 1)[1]) for line in report.decode().splitlines() if "Veredicto:" in line}
assert verdicts == {"APPROVE-TECHNICAL"}, f"verdict is not APPROVE-TECHNICAL (the only favourable verdict of the pinned prompt): {sorted(verdicts) or 'none'}"
print("audit verdict", sorted(verdicts))
PY
  echo "audit attestation sha256=$(sha256sum "$snap/attestation.json" | cut -d' ' -f1) report sha256=$REPORT_SHA"
  ((APPLY)) && cp -- "$snap/attestation.json" "$snap/report.md" "$LOG/"
  return 0
}
freeze_trees() {
  for role in aao-auditor aao-supervisor aao-integrator; do
    f=/srv/aao/frozen/$role
    run g clone -q --no-hardlinks "$SRC" "$f/tree"
    run g -C "$f/tree" -c advice.detachedHead=false checkout -q "$REV"
    run g -C "$f/tree" remote remove origin
    run python3 -m venv "$f/venv"
    run "$f/venv/bin/pip" install -q -r "$f/tree/deploy/auditor-venv-constraints.txt"
  done
  run chown -R aao-auditor:aao-auditor /srv/aao/frozen/aao-auditor/tree
  run chmod -R go-w /srv/aao/frozen
  T=$SRC/deploy
  run install -o root -g root -m 0644 "$T"/systemd/*.service "$T"/systemd/*.timer "$T"/systemd/*.path /etc/systemd/system/
  run install -o root -g root -m 0644 "$T/tmpfiles.d/aao-trust-root.conf" /etc/tmpfiles.d/
  run systemd-tmpfiles --create /etc/tmpfiles.d/aao-trust-root.conf
}
generate_install() {
  G=$(mktemp -d)/out
  run /usr/bin/python3 -I /srv/aao/frozen/aao-supervisor/tree/scripts/make_trust_root_files.py --revision "$REV" \
    --policy-template /srv/aao/frozen/aao-supervisor/tree/docs/audit-runs/20261019-provisional/policy.json \
    --developer "$CEO" --repo "$LOOP_REPO" --out "$G" "${RA_ARGS[@]}"
  run install -d -o root -g root -m 0755 /etc/aao-audit /etc/aao-supervisor /etc/aao-integrator
  run install -o root -g root -m 0644 "$G/integrator-config.json" /etc/aao-integrator/config.json
  run install -o root -g root -m 0644 "$G/dispatch.json" /etc/aao-audit/dispatch.json
  run install -o root -g root -m 0644 "$G/trust-anchor.json" /etc/aao-audit/trust-anchor.json
  run install -o root -g root -m 0644 "$G/supervisor-config.json" /etc/aao-supervisor/config.json
  run install -o aao-trust -g aao-trust -m 0644 "$G/registry.json" /srv/aao/trust/registry.json
  run install -o aao-auditor -g aao-auditor -m 0644 "$G/policy.json" /var/lib/aao-auditor/policy.json
}
verify_and_enable() {
  run systemctl daemon-reload
  run systemctl enable --now aao-supervisor-intake.service aao-supervisor-heartbeat.timer aao-supervisor-attribution.timer aao-supervisor-watch.timer
  if ((APPLY)); then
    /usr/bin/python3 -I /srv/aao/frozen/aao-supervisor/tree/scripts/verify_trust_root_host.py --expected-revision "$REV" \
      --status-file /var/lib/aao-trust-verify/status.json | tee "$LOG/trust-root-verify.log" \
      || die "host verification FAILED: the auditor dispatch is NOT enabled ($LOG/trust-root-verify.log)${1:+; $1}"
  fi
  # Audits run; the integrator stays OFF (CEO order: not before P2/P3 PASS).
  run systemctl enable --now aao-trust-root-verify.timer aao-auditor-dispatch.path aao-auditor-dispatch.timer
}
if ((TRUST_ROOT)); then
  say "trust-root"
  check_audit
  # Fresh hosts only: refuse before writing anything if any trust-root artifact already exists.
  for f in /etc/aao-audit/trust-anchor.json /etc/aao-audit/dispatch.json /etc/aao-audit/expected-revision \
           /etc/aao-supervisor/config.json /etc/aao-integrator/config.json /srv/aao/trust/registry.json \
           /var/lib/aao-auditor/policy.json /srv/aao/frozen/aao-auditor/tree /srv/aao/frozen/aao-supervisor/tree \
           /srv/aao/frozen/aao-integrator/tree /etc/aao-audit/ledger.anchor /etc/tmpfiles.d/aao-trust-root.conf \
           /var/lib/aao-supervisor/keys/supervisor-ed25519.pem /var/lib/aao-integrator/integrator-ed25519.pem \
           /srv/aao/trust/keys/aao-supervisor-ed25519.pub /srv/aao/trust/keys/aao-integrator-ed25519.pub \
           /var/lib/aao-trust-verify/status.json /var/lib/aao-auditor/ledger/governance.jsonl "$SRC"/deploy/systemd/*; do
    [[ $f == "$SRC"/* ]] && f=/etc/systemd/system/${f##*/}
    [[ ! -e $f && ! -L $f ]] || die "$f already exists: the trust-root phase only runs on a host without one (rotation is a separate procedure)"
  done
  # Every directory the trust-root tmpfiles manage must be absent or empty (no leftover data).
  while read -r d; do
    [[ ! -e $d && ! -L $d ]] || [[ -d $d && ! -L $d && -z $(ls -A "$d") ]] || die "$d is not empty: not a fresh host"
  done < <(awk '$1 == "d" {print $2}' "$SRC/deploy/tmpfiles.d/aao-trust-root.conf")
  freeze_trees
  newkey() {  # uid private public: never overwrite an existing key
    if [[ -e $2 ]]; then echo "ok   $2 exists (kept)"; return; fi
    run runuser -u "$1" -- sh -c "umask 077 && openssl genpkey -algorithm ed25519 -out '$2'"
    if ((APPLY)); then runuser -u "$1" -- openssl pkey -in "$2" -pubout | install -o aao-trust -g aao-trust -m 0644 /dev/stdin "$3"; fi
  }
  newkey aao-supervisor /var/lib/aao-supervisor/keys/supervisor-ed25519.pem /srv/aao/trust/keys/aao-supervisor-ed25519.pub
  newkey aao-integrator /var/lib/aao-integrator/integrator-ed25519.pem /srv/aao/trust/keys/aao-integrator-ed25519.pub
  generate_install
  if [[ ! -e /etc/aao-audit/ledger.anchor ]]; then
    ((APPLY)) && printf '%064d\n' 0 | install -o root -g root -m 0644 /dev/stdin /etc/aao-audit/ledger.anchor
  fi
  ((APPLY)) && echo "$REV" | install -o root -g root -m 0644 /dev/stdin /etc/aao-audit/expected-revision
  # Empty auditor ledger (zero rows verifies; matches the all-zero anchor). The heartbeat refuses a missing one.
  run install -o aao-auditor -g aao-ledger-read -m 0640 /dev/null /var/lib/aao-auditor/ledger/governance.jsonl
  verify_and_enable
fi

# ---------- 5b. trust-root upgrade (opt-in) ----------
if ((UPGRADE)); then
  say "trust-root-upgrade"
  check_audit
  OLD=$(cat /etc/aao-audit/expected-revision 2>/dev/null) || die "no installed trust root (use --trust-root on a fresh host)"
  [[ $OLD =~ ^[0-9a-f]{40}$ && $OLD != "$REV" ]] || die "installed revision '$OLD' is invalid or already $REV"
  g -C "$SRC" merge-base --is-ancestor "$OLD" "$REV" || die "$REV does not descend from the installed $OLD (no rollback/side-grade)"
  # Keys, the auditor ledger and its anchor are carried over untouched: the chain continues.
  for f in /var/lib/aao-supervisor/keys/supervisor-ed25519.pem /var/lib/aao-integrator/integrator-ed25519.pem \
           /srv/aao/trust/keys/aao-supervisor-ed25519.pub /srv/aao/trust/keys/aao-integrator-ed25519.pub \
           /etc/aao-audit/ledger.anchor /var/lib/aao-auditor/ledger/governance.jsonl; do
    [[ -f $f && ! -L $f ]] || die "$f missing: not a complete installed trust root"
  done
  # Validate every registry input BEFORE anything is stopped or moved (also in dry-run): same generator,
  # from the root clone at REV, into a throwaway directory.
  /usr/bin/python3 -I "$SRC/scripts/make_trust_root_files.py" --revision "$REV" \
    --policy-template "$SRC/docs/audit-runs/20261019-provisional/policy.json" \
    --developer "$CEO" --repo "$LOOP_REPO" --out "$(mktemp -d)/preflight" "${RA_ARGS[@]}" >/dev/null \
    || die "registry inputs rejected by make_trust_root_files.py; nothing was stopped or moved"
  BK=/var/backups/aao-trust-root/$(date -u +%Y%m%dT%H%M%SZ)-$OLD
  run install -d -o root -g root -m 0700 /var/backups/aao-trust-root "$BK"
  # Stop the loop first (integrator included): nothing runs against a half-replaced root.
  # Only units this host already has: an upgrade from an older revision lacks units added later (e.g. the watch).
  installed=(); for u in aao-integrator-tick.timer aao-auditor-dispatch.path aao-auditor-dispatch.timer aao-trust-root-verify.timer \
    aao-supervisor-attribution.timer aao-supervisor-watch.timer aao-supervisor-heartbeat.timer aao-supervisor-intake.service; do
    [[ -e /etc/systemd/system/$u ]] && installed+=("$u"); done
  run systemctl disable --now "${installed[@]}"
  # A oneshot already in flight would keep running against the old tree: stop the services too, then require all idle.
  LOOP_UNITS=(aao-integrator-tick.service aao-auditor-dispatch.service 'aao-auditor@*.service' aao-supervisor-attribution.service aao-supervisor-watch.service
              aao-supervisor-heartbeat.service aao-supervisor-intake.service aao-trust-root-verify.service)
  active=$(systemctl list-units --state=active,activating,deactivating --no-legend --plain "${LOOP_UNITS[@]}" | awk '{print $1}')
  echo "loop units running now: ${active:-none}"
  # systemctl stop fails (rc 5) on a unit that is not loaded, e.g. one added by REV on an older host.
  mapfile -t loaded < <(systemctl list-units --all --no-legend --plain "${LOOP_UNITS[@]}" | awk '{print $1}')
  ((${#loaded[@]} == 0)) || run systemctl stop "${loaded[@]}"
  if ((APPLY)); then
    active=$(systemctl list-units --state=active,activating,deactivating --no-legend --plain "${LOOP_UNITS[@]}" | awk '{print $1}')
    [[ -z $active ]] || die "still running, nothing replaced: $active"
  else
    echo "DRY: --apply stops them and refuses to continue if any is still running afterwards"
  fi
  # Installed unit files are part of the state a rollback must restore.
  mapfile -t UNIT_FILES < <(cd / && ls -d etc/systemd/system/aao-*.service etc/systemd/system/aao-*.timer etc/systemd/system/aao-*.path 2>/dev/null)
  run tar -C / -cpf "$BK/config.tar" --numeric-owner etc/aao-audit etc/aao-supervisor etc/aao-integrator \
    srv/aao/trust/registry.json var/lib/aao-auditor/policy.json etc/tmpfiles.d/aao-trust-root.conf "${UNIT_FILES[@]}"
  for role in aao-auditor aao-supervisor aao-integrator; do
    run install -d -o root -g root -m 0700 "$BK/frozen-$role"
    run mv /srv/aao/frozen/$role/tree /srv/aao/frozen/$role/venv "$BK/frozen-$role/"
  done
  freeze_trees
  generate_install
  ((APPLY)) && echo "$REV" | install -o root -g root -m 0644 /dev/stdin /etc/aao-audit/expected-revision
  verify_and_enable "roll back: stop the aao-* units, remove /etc/systemd/system/aao-* added by $REV, restore $BK (tar -C / -xpf config.tar restores config and the previous unit files; move frozen-*/ back), write $OLD to /etc/aao-audit/expected-revision, systemctl daemon-reload"
  echo "upgraded $OLD -> $REV; backup in $BK. The integrator is OFF: re-enable it only with --enable-integrator."
fi

# ---------- 6. integrator (opt-in, gated on RA PASS) ----------
if ((ENABLE_INTEGRATOR)); then
  say "integrator"
  python3 -I -c 'import json,sys; s=json.load(open(sys.argv[1]))["ra_status"]; need={"RA-01","RA-02","RA-03","RA-07","RA-09"}
bad=sorted(need-{k for k,v in s.items() if v=="PASS"}|set(s)-need); sys.exit("RA not exactly PASS: "+", ".join(bad) if bad else 0)' /srv/aao/trust/registry.json \
    || die "the integrator stays off until the P2/P3 trial sets every RA to PASS in the registry"
  # CEO-DEC-P2P3-2026-10-24 §5: never enable the integrator while main lacks verified preventive protection. The
  # rulesets of the repository the integrator serves are checked with the CEO's read access (exact A/B/C shape).
  irepo=$(python3 -I -c 'import json,sys; print(json.load(open(sys.argv[1]))["repo"])' /etc/aao-integrator/config.json) \
    || die "cannot read the integrator repository from /etc/aao-integrator/config.json"
  runuser -u "$CEO" -- env -i HOME="$(getent passwd "$CEO" | cut -d: -f6)" PATH=/usr/bin:/bin \
    python3 -I - --repo "$irepo" verify < "$SRC/scripts/governance/canonical_protection.py" \
    || die "rulesets of $irepo are not the verified A/B/C protection: the integrator stays off"
  run systemctl enable --now aao-integrator-tick.timer
fi
say "done (apply=$APPLY). Log: $LOG"
