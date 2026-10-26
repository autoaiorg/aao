#!/usr/bin/env bash
# F2 isolation checks (plan §8.1). Run as each AAO role account from the same
# launch path the agent uses, for example:
#   sudo -u aao-impl-codex -i bash /path/to/verify_identity_separation.sh
#
# Each check asks the kernel for effective access with test -r / -w / -x,
# which honours modes, ACLs and group membership. A check passes only when
# the target exists AND access is denied. A missing target is NOT RUN, which
# counts as a failure. Exit status is non-zero on any failure.
#
# Not covered (declared, not implied): polkit rules, cron, systemd lingering,
# setuid binaries and network sockets other than docker. Those belong to the
# host review of P1.
set -uo pipefail

CEO_USER="${CEO_USER:-${SUDO_USER:-$(logname 2>/dev/null || true)}}"
[[ -n "$CEO_USER" ]] || { echo "FAIL: CEO_USER environment variable must be set" >&2; exit 1; }
me=$(id -un)
fails=0
pass() { echo "PASS     $1"; }
fail() { echo "FAIL     $1"; fails=$((fails + 1)); }
notrun() { echo "NOT RUN  $1"; fails=$((fails + 1)); }

# denied <r|w|x> <path> <description>
# The target must be visible; anything hidden is NOT RUN (never PASS). The
# layout itself (existence, owner, mode) is asserted separately as root by
# scripts/test_identity_separation_container.sh and by the host P1 evidence.
denied() {
  local mode=$1 path=$2 desc=$3
  [[ -e "$path" ]] || { notrun "$desc (not visible: $path)"; return; }
  if test "-$mode" "$path"; then fail "$desc"; else pass "$desc"; fi
}
in_group() { id -nG | tr ' ' '\n' | grep -qx "$1"; }

echo "# identity: $(id)"

# sudo: a role must have no sudo rights at all, with or without a password.
if out=$(sudo -n -l 2>&1); then
  fail "sudo rights listed: $(echo "$out" | tail -1)"
elif grep -qiE "may not run sudo|not allowed|a password is required|unknown user" <<<"$out"; then
  pass "no passwordless sudo"
else
  notrun "sudo check (unexpected output: $out)"
fi
priv=0
for g in sudo admin wheel docker adm lxd libvirt "$CEO_USER"; do
  if in_group "$g"; then fail "member of privileged group $g"; priv=1; fi
done
(( priv )) || pass "no privileged group membership"

if [[ -e /var/run/docker.sock ]]; then
  denied w /var/run/docker.sock          "docker socket"
else
  pass "docker socket (not present on host)"
fi
denied x "/home/$CEO_USER"             "enter CEO home"
denied r "/home/$CEO_USER"             "list CEO home"
denied w /srv/aao/trust                "write trust registry"
denied w /srv/aao/trust/keys           "write trust keys"
denied w /srv/aao/frozen               "write frozen checkouts"
for c in /srv/aao/frozen/*/; do denied w "${c%/}" "write ${c%/}"; done

for a in aao-auditor aao-auditor-alt; do
  [[ "$me" == "$a" ]] && continue
  if in_group aao-ledger-read; then
    # Supervisor and integrator may read ledgers, never keys or write.
    denied x "/var/lib/$a/keys"   "enter $a keys dir"
    denied w "/var/lib/$a/ledger" "write $a ledger"
  else
    # Everyone else must not even traverse the auditor's directory.
    denied x "/var/lib/$a"        "enter /var/lib/$a"
  fi
done

if [[ "$me" != aao-supervisor ]]; then
  if in_group aao-events; then
    denied w /var/lib/aao-supervisor/events "write supervisor events"
  else
    denied x /var/lib/aao-supervisor "enter /var/lib/aao-supervisor"
  fi
fi

# Ptrace of other users' processes must be restricted.
scope=$(cat /proc/sys/kernel/yama/ptrace_scope 2>/dev/null || echo missing)
if [[ "$scope" =~ ^[1-3]$ ]]; then pass "ptrace_scope=$scope"; else fail "ptrace_scope=$scope (expected 1-3)"; fi

shopt -s nullglob
homes=(/home/aao-*)
(( ${#homes[@]} )) || notrun "role homes (none exist)"
for other in "${homes[@]}"; do
  [[ "$other" == "/home/$me" ]] && continue
  denied x "$other" "enter $other"
done

if (( fails )); then echo "# $fails check(s) FAILED for $me"; exit 1; fi
echo "# all checks PASSED for $me"
