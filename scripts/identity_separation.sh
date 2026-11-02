#!/usr/bin/env bash
# Create the AAO role identities and protected directories (plan F2 / proposal P1).
#
# Modes:
#   (default)   dry run: preflight checks plus the list of intended changes
#   --apply     make the changes (root only)
#   --revert    non-destructive rollback (root only): remove the sudoers rule
#               and lock the role accounts. Keys, ledgers and the trust
#               registry are kept so no evidence is lost.
#   --purge     full rollback to the pre-install state (root only): archive
#               all managed data to /root/aao-identity-archive-<ts>.tar.gz,
#               then remove the sudoers rule, role accounts, their groups
#               and managed directories.
#
# Fail closed: if an existing aao-* account or file does not match the
# expected state (shell, home, supplementary groups, foreign sudoers rules),
# the script stops before changing anything and reports why.
#
# Scope: static identities and file permissions only. Runtime isolation
# (private /tmp, venv, caches, sockets) belongs to the systemd units of F3a.
# Docker containers and the CEO account (CEO_USER) are never modified.
#
# Status: R2 candidate. Do not run on the host before independent review and
# the CEO decision on P1.
set -euo pipefail

CEO_USER="${CEO_USER:-alessbarb}"
MODE="${1:-dry-run}"
case "$MODE" in dry-run|--apply|--revert|--purge) ;; *) echo "usage: $0 [--apply|--revert|--purge]" >&2; exit 2;; esac
APPLY=0; [[ "$MODE" == --apply ]] && APPLY=1

AGENT_USERS=(aao-pm aao-impl-codex aao-impl-claude aao-impl-ag)
AUDITORS=(aao-auditor aao-auditor-alt)
SERVICE_USERS=("${AUDITORS[@]}" aao-integrator aao-supervisor aao-notifier aao-trust)
ALL_USERS=("${AGENT_USERS[@]}" "${SERVICE_USERS[@]}")
SUDOERS=/etc/sudoers.d/aao-launch
MARKER="# Managed by scripts/identity_separation.sh"

# The only supplementary groups each role may have. Anything else is rejected.
declare -A ALLOWED_GROUPS=(
  [aao-pm]="aao-host-id-read"
  [aao-impl-codex]="aao-host-id-read"
  [aao-impl-ag]="aao-host-id-read"
  [aao-integrator]="aao-ledger-read"
  [aao-supervisor]="aao-ledger-read"
  [aao-notifier]="aao-events"
)

expected_shell() {
  local u
  for u in "${AGENT_USERS[@]}"; do [[ "$1" == "$u" ]] && { echo /bin/bash; return; }; done
  echo /usr/sbin/nologin
}

# Managed directory layout: path owner group mode.
layout() {
  local a c
  for a in "${AUDITORS[@]}"; do
    echo "/var/lib/$a $a aao-ledger-read 0750"
    echo "/var/lib/$a/keys $a $a 0700"
    echo "/var/lib/$a/ledger $a aao-ledger-read 0750"
  done
  echo "/var/lib/aao-supervisor aao-supervisor aao-events 0750"
  echo "/var/lib/aao-supervisor/events aao-supervisor aao-events 0750"
  echo "/srv/aao aao-trust aao-trust 0755"
  echo "/srv/aao/trust aao-trust aao-trust 0755"
  echo "/srv/aao/trust/keys aao-trust aao-trust 0755"
  echo "/srv/aao/frozen aao-trust aao-trust 0755"
  for c in "${AUDITORS[@]}" aao-integrator aao-supervisor; do echo "/srv/aao/frozen/$c aao-trust aao-trust 0755"; done
}

run() { printf '+ %s\n' "$*"; if (( APPLY )); then "$@"; fi; }
die() { echo "PREFLIGHT FAIL: $*" >&2; exit 1; }

if [[ "$MODE" != dry-run ]] && (( EUID != 0 )); then die "$MODE requires root"; fi

# ---------- revert ----------
if [[ "$MODE" == --revert ]]; then
  if [[ -f "$SUDOERS" ]]; then
    grep -qxF "$MARKER" "$SUDOERS" || die "$SUDOERS is not managed by this script; leaving it untouched"
    rm -f "$SUDOERS"; echo "+ removed $SUDOERS"
  fi
  for u in "${ALL_USERS[@]}"; do
    if id "$u" >/dev/null 2>&1; then
      usermod -L -s /usr/sbin/nologin "$u"; echo "+ locked $u"
    fi
  done
  echo "Reverted. Data under /var/lib/aao-* and /srv/aao is kept. Remove it by hand only after archiving the evidence."
  exit 0
fi

# ---------- purge ----------
if [[ "$MODE" == --purge ]]; then
  if [[ -f "$SUDOERS" ]] && ! grep -qxF "$MARKER" "$SUDOERS"; then die "$SUDOERS is not managed by this script"; fi
  archive="${AAO_ARCHIVE_DIR:-/root}/aao-identity-archive-$(date +%Y%m%dT%H%M%S).tar.gz"
  paths=()
  for p in /var/lib/aao-auditor /var/lib/aao-auditor-alt /var/lib/aao-supervisor /srv/aao "$SUDOERS"; do [[ -e "$p" ]] && paths+=("$p"); done
  for u in "${ALL_USERS[@]}"; do [[ -d "/home/$u" ]] && paths+=("/home/$u"); done
  # Nothing is deleted unless the archive exists, is private and lists every
  # managed path. Any failure stops here with all accounts and data intact.
  if (( ${#paths[@]} )); then
    tar -czf "$archive" "${paths[@]}" || die "archive failed; nothing was removed"
    chmod 0600 "$archive" || die "cannot protect $archive; nothing was removed"
    listing=$(tar -tzf "$archive") || die "archive $archive is unreadable; nothing was removed"
    for p in "${paths[@]}"; do
      grep -qx "${p#/}/\{0,1\}" <<<"$listing" || die "archive lacks $p; nothing was removed"
    done
    echo "+ archived and verified $archive"
  fi
  rm -f "$SUDOERS"
  for u in "${ALL_USERS[@]}"; do id "$u" >/dev/null 2>&1 && { userdel -r "$u" 2>/dev/null || userdel "$u"; echo "+ removed $u"; }; done
  for g in aao-ledger-read aao-events aao-host-id-read; do getent group "$g" >/dev/null && groupdel "$g" && echo "+ removed group $g"; done
  rm -rf /var/lib/aao-auditor /var/lib/aao-auditor-alt /var/lib/aao-supervisor /srv/aao
  echo "Purged. Restore evidence from $archive if needed."
  exit 0
fi

# ---------- preflight (no changes) ----------
echo "# preflight"
command -v getfacl >/dev/null || die "getfacl not found (install package 'acl'); cannot verify ACLs"
command -v openssl >/dev/null || die "openssl not found"
# Ancestors of managed paths must be root-owned and not writable by group/others.
for anc in /var /var/lib /srv /etc/sudoers.d /home; do
  [[ -d "$anc" ]] || continue
  [[ "$(stat -c '%U' "$anc")" == root ]] || die "$anc is not owned by root"
  (( ( 0$(stat -c '%a' "$anc") & 022 ) == 0 )) || die "$anc is writable by group or others"
done
id "$CEO_USER" >/dev/null 2>&1 || die "CEO account $CEO_USER not found"
for u in "${ALL_USERS[@]}"; do
  id "$u" >/dev/null 2>&1 || continue
  shell=$(getent passwd "$u" | cut -d: -f7); home=$(getent passwd "$u" | cut -d: -f6)
  [[ "$shell" == "$(expected_shell "$u")" ]] || die "$u has shell $shell, expected $(expected_shell "$u")"
  [[ "$home" == "/home/$u" ]] || die "$u has home $home, expected /home/$u"
  # Role accounts have no usable password; login only through su/sudo by root.
  pw=$(passwd -S "$u" 2>/dev/null | awk '{print $2}')
  [[ "$pw" == L ]] || die "$u password state is '$pw', expected locked (L)"
  for g in $(id -nG "$u"); do
    [[ "$g" == "$u" ]] && continue
    [[ " ${ALLOWED_GROUPS[$u]:-} " == *" $g "* ]] || die "$u is in unexpected group '$g'"
  done
done
# No other sudoers rule may mention a role account (e.g. leftovers from manual setup).
if [[ -d /etc/sudoers.d ]]; then
  for f in /etc/sudoers /etc/sudoers.d/*; do
    [[ -f "$f" && "$f" != "$SUDOERS" ]] || continue
    if grep -Eq '(^|[^[:alnum:]_-])aao-' "$f" 2>/dev/null; then die "foreign sudoers rule mentions aao- in $f"; fi
  done
fi
if [[ -f "$SUDOERS" ]] && ! grep -qxF "$MARKER" "$SUDOERS"; then die "$SUDOERS exists and is not managed by this script"; fi
# Account identity: never uid 0, never shared with another account.
for u in "${ALL_USERS[@]}"; do
  id "$u" >/dev/null 2>&1 || continue
  uid=$(id -u "$u")
  (( uid != 0 )) || die "$u has uid 0"
  [[ $(getent passwd | awk -F: -v x="$uid" '$3==x' | wc -l) -eq 1 ]] || die "uid $uid of $u is shared"
done
# Existing managed paths must already have the expected owner, group, mode
# and no extended ACL; otherwise stop before changing anything.
check_path() {  # path owner group mode
  [[ -e "$1" ]] || return 0
  [[ -d "$1" && ! -L "$1" ]] || die "$1 exists and is not a plain directory"
  local actual; actual=$(stat -c '%U %G %a' "$1")
  [[ "$actual" == "$2 $3 ${4#0}" ]] || die "$1 is '$actual', expected '$2 $3 ${4#0}'"
  if command -v getfacl >/dev/null && [[ -n $(getfacl -s -p "$1" 2>/dev/null) ]]; then die "$1 has an extended ACL"; fi
}
while read -r path owner group mode; do check_path "$path" "$owner" "$group" "$mode"; done < <(layout)
# Existing content of managed directories: owned by the directory owner, no
# ACLs, no setuid/setgid, private keys mode 0600, nothing writable by others.
# The trust-root install later adds trees with other owners under /srv/aao: the frozen code trees and venvs
# (venvs contain symlinks) and the integrator's mirror. verify_trust_root_host.py governs those, and on a
# fresh host they did not exist yet, so they are skipped here. They must still be real directories, so a
# planted symlink cannot use the exclusion to hide content.
PRUNED=(/srv/aao/mirror)
for c in "${AUDITORS[@]}" aao-integrator aao-supervisor; do PRUNED+=("/srv/aao/frozen/$c/tree" "/srv/aao/frozen/$c/venv"); done
PRUNE_ARGS=(); for p in "${PRUNED[@]}"; do
  [[ ! -e $p && ! -L $p ]] || [[ -d $p && ! -L $p ]] || die "$p exists and is not a plain directory"
  PRUNE_ARGS+=(-path "$p" -o); done
unset 'PRUNE_ARGS[${#PRUNE_ARGS[@]}-1]'
for d in /var/lib/aao-auditor /var/lib/aao-auditor-alt /var/lib/aao-supervisor /srv/aao; do
  [[ -d "$d" ]] || continue
  while IFS= read -r -d '' f; do
    [[ -L "$f" ]] && die "symlink inside managed tree: $f"
    [[ "$(stat -c '%U' "$f")" == "$(stat -c '%U' "$(dirname "$f")")" ]] || die "$f is not owned by the owner of its directory"
    [[ -n $(getfacl -s -p "$f" 2>/dev/null) ]] && die "extended ACL on $f"
    m=$(stat -c '%a' "$f")
    (( ( 0$m & 06002 ) == 0 )) || die "$f has setuid/setgid or is world-writable ($m)"
  done < <(find "$d" -mindepth 1 \( "${PRUNE_ARGS[@]}" \) -prune -o -print0)
done
for a in "${AUDITORS[@]}"; do
  k="/var/lib/$a/keys/auditor-ed25519.pem"
  [[ -e "$k" ]] || continue
  [[ "$(stat -c '%U %a' "$k")" == "$a 600" ]] || die "$k must be owned by $a with mode 600"
done
# Existing role homes must be private to their owner.
for u in "${ALL_USERS[@]}"; do
  [[ -d "/home/$u" ]] || continue
  [[ "$(stat -c '%U' "/home/$u")" == "$u" ]] || die "/home/$u is not owned by $u"
done
# An existing public key must match its auditor's private key.
for a in "${AUDITORS[@]}"; do
  key="/var/lib/$a/keys/auditor-ed25519.pem"; pub="/srv/aao/trust/keys/$a-ed25519.pub"
  if [[ -e "$pub" ]]; then
    [[ -f "$key" ]] || die "$pub exists without its private key"
    cmp -s "$pub" <(openssl pkey -in "$key" -pubout 2>/dev/null) || die "$pub does not match $key"
  fi
done
echo "# preflight OK"
echo "# docker group members (not modified): $(getent group docker | cut -d: -f4)"
(( APPLY )) || echo "# DRY RUN: no changes will be made."

# ---------- apply ----------
ensure_group() { getent group "$1" >/dev/null || run groupadd --system "$1"; }
ensure_user() {
  id "$1" >/dev/null 2>&1 || run useradd --create-home --home-dir "/home/$1" --shell "$(expected_shell "$1")" --user-group "$1"
  run chmod 0700 "/home/$1"
}
ensure_dir() { run install -d -o "$2" -g "$3" -m "$4" "$1"; }  # path owner group mode

ensure_group aao-ledger-read
ensure_group aao-events
ensure_group aao-host-id-read
for u in "${ALL_USERS[@]}"; do ensure_user "$u"; done
for u in "${!ALLOWED_GROUPS[@]}"; do run usermod -aG "${ALLOWED_GROUPS[$u]}" "$u"; done

# Directories: the auditors cannot read each other; ledgers are readable by
# the supervisor and the integrator only; trust registry and frozen
# checkouts are owned by aao-trust, so no role can change its own code, key
# or policy.
while read -r path owner group mode; do ensure_dir "$path" "$owner" "$group" "$mode"; done < <(layout)

# Key path used by independent_audit.py:  --key /var/lib/<auditor>/keys/auditor-ed25519.pem
# The public key goes to the trust registry. policy.json is R3 trust root and is NOT written here.
for a in "${AUDITORS[@]}"; do
  key="/var/lib/$a/keys/auditor-ed25519.pem"
  pub="/srv/aao/trust/keys/$a-ed25519.pub"
  if (( APPLY )); then
    if [[ ! -f "$key" ]]; then
      runuser -u "$a" -- sh -c "umask 077 && openssl genpkey -algorithm ed25519 -out '$key'"
      echo "+ generated $key as $a"
    fi
    if [[ ! -e "$pub" ]]; then
      tmp=$(mktemp /srv/aao/trust/keys/.pub.XXXXXX)
      trap 'rm -f "$tmp"' EXIT
      runuser -u "$a" -- openssl pkey -in "$key" -pubout > "$tmp"
      openssl pkey -pubin -in "$tmp" -noout || { rm -f "$tmp"; die "generated public key for $a is invalid"; }
      chown aao-trust:aao-trust "$tmp"; chmod 0644 "$tmp"
      mv -f "$tmp" "$pub"   # atomic rename within the same directory
      trap - EXIT
      echo "+ published $pub"
    fi
  else
    echo "+ (would generate $key as $a if absent and publish $pub)"
  fi
done

# The CEO may launch AGENTS only. Auditors are not reachable through sudo;
# they run as systemd services (F3a). The rule still requires the CEO password.
rule="$CEO_USER ALL=($(IFS=,; echo "${AGENT_USERS[*]}")) ALL"
if (( APPLY )); then
  tmp=$(mktemp)
  printf '%s\n' "$MARKER" "$rule" > "$tmp"
  visudo -cf "$tmp" >/dev/null
  install -o root -g root -m 0440 "$tmp" "$SUDOERS"
  rm -f "$tmp"
  echo "+ wrote $SUDOERS"
else
  echo "+ (would write $SUDOERS: $rule)"
fi

cat <<'EOF'

Next steps (manual, one time):
  1. Log in each agent CLI as its own user, e.g.  sudo -u aao-impl-codex -i codex login
     Never copy the CEO's GitHub token (~/.config/gh) into an agent account.
  2. Clone the repository inside each agent home (not a shared working copy).
  3. Leave PostgreSQL running from the CEO account; agents reach it over
     TCP at 127.0.0.1:54329 and never use the docker socket.
  4. Run scripts/verify_identity_separation.sh as every role and attach the output to the F2 evidence.
  Rollback:  sudo scripts/identity_separation.sh --revert   (lock, keep data)
             sudo scripts/identity_separation.sh --purge    (archive + verify, then remove everything)
  After --revert, re-installing requires --purge first (--apply refuses locked accounts).
EOF
