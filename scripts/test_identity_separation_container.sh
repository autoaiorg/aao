#!/usr/bin/env bash
# Usage (from repo root):
#   docker run --rm -v "$PWD/scripts:/s:ro" -v "$PWD:/repo:ro" ubuntu:24.04 bash /s/test_identity_separation_container.sh
# Disposable-container acceptance test for scripts/identity_separation.sh (F2).
set -u
S=/s; R=/repo
t() { local name=$1; shift; if "$@"; then echo "TEST PASS  $name"; else echo "TEST FAIL  $name"; FAILED=1; fi; }
FAILED=0
apt-get update -qq >/dev/null && apt-get install -y -qq openssl sudo acl python3 git >/dev/null 2>&1
useradd -m alessbarb && chmod 750 /home/alessbarb && usermod -aG sudo alessbarb
export CEO_USER=alessbarb
mkdir -p /home/alessbarb/.config/gh && echo token > /home/alessbarb/.config/gh/hosts.yml && chown -R alessbarb: /home/alessbarb && chmod 600 /home/alessbarb/.config/gh/hosts.yml
groupadd docker && touch /var/run/docker.sock && chown root:docker /var/run/docker.sock && chmod 660 /var/run/docker.sock
snap() { { getent passwd | sort; getent group | sort; ls -1A /etc/sudoers.d; ls -d /var/lib/aao-* /srv/aao /home/aao-* 2>/dev/null; } > "$1"; }
snap /tmp/state_before

echo "== T1 preflight rejects unexpected privileged group"
useradd -m -s /bin/bash aao-impl-codex && usermod -aG docker aao-impl-codex
t "unexpected group -> fail closed, no changes" bash -c "! bash $S/identity_separation.sh --apply >/tmp/o 2>&1 && grep -q \"unexpected group 'docker'\" /tmp/o && ! id aao-pm >/dev/null 2>&1"
gpasswd -d aao-impl-codex docker >/dev/null

echo "== T2 preflight rejects wrong shell"
usermod -s /bin/sh aao-impl-codex
t "wrong shell -> fail closed" bash -c "! bash $S/identity_separation.sh --apply >/tmp/o 2>&1 && grep -q 'has shell /bin/sh' /tmp/o"
usermod -s /bin/bash aao-impl-codex

echo "== T3 preflight rejects foreign sudoers rule"
echo 'aao-impl-codex ALL=(ALL) NOPASSWD: ALL' > /etc/sudoers.d/legacy && chmod 440 /etc/sudoers.d/legacy
t "foreign sudoers -> fail closed" bash -c "! bash $S/identity_separation.sh --apply >/tmp/o 2>&1 && grep -q 'foreign sudoers' /tmp/o"
rm /etc/sudoers.d/legacy

echo "== T4 apply twice (idempotent)"
t "first apply" bash -c "bash $S/identity_separation.sh --apply >/tmp/a1 2>&1"
k1=$(sha256sum /var/lib/aao-auditor/keys/auditor-ed25519.pem | cut -d' ' -f1)
t "second apply" bash -c "bash $S/identity_separation.sh --apply >/tmp/a2 2>&1"
k2=$(sha256sum /var/lib/aao-auditor/keys/auditor-ed25519.pem | cut -d' ' -f1)
t "key not regenerated" test "$k1" = "$k2"
t "no new users on second run" bash -c "! grep -q useradd /tmp/a2"

echo "== T5 sudoers: CEO cannot reach auditors"
t "sudoers excludes auditors" bash -c "! grep -q aao-auditor /etc/sudoers.d/aao-launch"
t "CEO sudo -l lists no auditor" bash -c "! sudo -l -U alessbarb | grep -q aao-auditor"

echo "== T6 verifier as every role"
for u in aao-pm aao-impl-codex aao-impl-claude aao-impl-ag aao-auditor aao-auditor-alt aao-integrator aao-supervisor aao-notifier; do
  t "verify $u" bash -c "runuser -u $u -- bash $S/verify_identity_separation.sh >/tmp/v_$u 2>&1"; grep -E "^(FAIL|NOT RUN)" /tmp/v_$u
done

echo "== T7 verifier catches an ACL grant (no false PASS)"
setfacl -m u:aao-impl-codex:x /var/lib/aao-auditor
t "ACL leak detected" bash -c "! runuser -u aao-impl-codex -- bash $S/verify_identity_separation.sh >/tmp/v 2>&1 && grep -q 'FAIL     enter /var/lib/aao-auditor' /tmp/v"
setfacl -b /var/lib/aao-auditor

echo "== T8 verifier: missing target is NOT RUN, not PASS"
mv /srv/aao/trust /srv/aao/trust.bak
t "missing target -> NOT RUN" bash -c "! runuser -u aao-pm -- bash $S/verify_identity_separation.sh >/tmp/v 2>&1 && grep -q 'NOT RUN  write trust registry' /tmp/v"
mv /srv/aao/trust.bak /srv/aao/trust

echo "== T8b verifier: a hidden or missing managed path is never PASS"
mv /var/lib/aao-auditor/keys /var/lib/aao-auditor/keys.bak
t "missing keys dir seen by supervisor -> NOT RUN" bash -c "! runuser -u aao-supervisor -- bash $S/verify_identity_separation.sh >/tmp/v 2>&1 && grep -q 'NOT RUN  enter aao-auditor keys dir' /tmp/v"
mv /var/lib/aao-auditor/keys.bak /var/lib/aao-auditor/keys
t "verifier has no ancestor inference" bash -c "! grep -qi ancestor $S/verify_identity_separation.sh"

echo "== T8c layout asserted as root"
lay_ok=1
while read -r p o g m; do [ "$(stat -c '%U %G %a' $p)" = "$o $g ${m#0}" ] || { echo "layout mismatch $p"; lay_ok=0; }; done <<'L'
/var/lib/aao-auditor aao-auditor aao-ledger-read 0750
/var/lib/aao-auditor/keys aao-auditor aao-auditor 0700
/var/lib/aao-auditor/ledger aao-auditor aao-ledger-read 0750
/var/lib/aao-auditor-alt aao-auditor-alt aao-ledger-read 0750
/var/lib/aao-auditor-alt/keys aao-auditor-alt aao-auditor-alt 0700
/var/lib/aao-supervisor/events aao-supervisor aao-events 0750
/srv/aao/trust/keys aao-trust aao-trust 0755
/srv/aao/frozen/aao-auditor aao-trust aao-trust 0755
L
t "layout matches" test $lay_ok = 1
t "private key mode 600 owned by auditor" test "$(stat -c '%U %a' /var/lib/aao-auditor/keys/auditor-ed25519.pem)" = "aao-auditor 600"

echo "== T8d preflight rejects non-conforming existing state"
chmod 0755 /var/lib/aao-auditor/keys
t "wrong mode on existing dir -> fail closed" bash -c "! bash $S/identity_separation.sh --apply >/tmp/o 2>&1 && grep -q 'keys is' /tmp/o"
chmod 0700 /var/lib/aao-auditor/keys
setfacl -m u:aao-pm:rx /srv/aao/frozen
t "extended ACL on existing dir -> fail closed" bash -c "! bash $S/identity_separation.sh --apply >/tmp/o 2>&1 && grep -q 'extended ACL' /tmp/o"
setfacl -b /srv/aao/frozen
cp /srv/aao/trust/keys/aao-auditor-ed25519.pub /tmp/pub.bak && cp /srv/aao/trust/keys/aao-auditor-alt-ed25519.pub /srv/aao/trust/keys/aao-auditor-ed25519.pub
t "public key not matching private key -> fail closed" bash -c "! bash $S/identity_separation.sh --apply >/tmp/o 2>&1 && grep -q 'does not match' /tmp/o"
cp /tmp/pub.bak /srv/aao/trust/keys/aao-auditor-ed25519.pub
t "clean state applies again" bash -c "bash $S/identity_separation.sh --apply >/tmp/o 2>&1"
t "no temp key files left" bash -c "! ls -A /srv/aao/trust/keys | grep -q '^\\.pub'"

echo "== T8e preflight fails closed on missing tools and unsafe content"
mv /usr/bin/getfacl /usr/bin/getfacl.bak
t "getfacl missing -> fail closed" bash -c "! bash $S/identity_separation.sh --apply >/tmp/o 2>&1 && grep -q 'getfacl not found' /tmp/o"
mv /usr/bin/getfacl.bak /usr/bin/getfacl
echo 'aao-pm:Secret123' | chpasswd
t "role account with usable password -> fail closed" bash -c "! bash $S/identity_separation.sh --apply >/tmp/o 2>&1 && grep -q 'expected locked' /tmp/o"
usermod -L aao-pm
touch /var/lib/aao-auditor/ledger/x && chown aao-auditor /var/lib/aao-auditor/ledger/x && chmod 0666 /var/lib/aao-auditor/ledger/x
t "world-writable file in managed tree -> fail closed" bash -c "! bash $S/identity_separation.sh --apply >/tmp/o 2>&1 && grep -q 'world-writable' /tmp/o"
rm /var/lib/aao-auditor/ledger/x
ln -s /etc/shadow /srv/aao/trust/evil
t "symlink in managed tree -> fail closed" bash -c "! bash $S/identity_separation.sh --apply >/tmp/o 2>&1 && grep -q 'symlink inside managed tree' /tmp/o"
rm /srv/aao/trust/evil
chmod 0644 /var/lib/aao-auditor/keys/auditor-ed25519.pem
t "private key mode 644 -> fail closed" bash -c "! bash $S/identity_separation.sh --apply >/tmp/o 2>&1 && grep -q 'mode 600' /tmp/o"
chmod 0600 /var/lib/aao-auditor/keys/auditor-ed25519.pem

touch /var/lib/aao-auditor/ledger/y
t "file owned by another user in managed tree -> fail closed" bash -c "! bash $S/identity_separation.sh --apply >/tmp/o 2>&1 && grep -q 'not owned by the owner of its directory' /tmp/o"
rm /var/lib/aao-auditor/ledger/y

echo "== T8f induced failure while publishing a key leaves no temp file"
rm /srv/aao/trust/keys/aao-auditor-ed25519.pub
mkdir -p /tmp/shim && cat > /tmp/shim/openssl <<'SH'
#!/bin/sh
for a in "$@"; do [ "$a" = "-pubout" ] && exit 1; done
exec /usr/bin/openssl "$@"
SH
chmod 755 /tmp/shim/openssl
t "publish fails" bash -c "! PATH=/tmp/shim:\$PATH bash $S/identity_separation.sh --apply >/tmp/o 2>&1"
t "no temp key file left after failure" bash -c "! ls -A /srv/aao/trust/keys | grep -q '^\\.pub'"
t "no partial public key published" test ! -e /srv/aao/trust/keys/aao-auditor-ed25519.pub
t "recovery: clean re-apply publishes the key" bash -c "bash $S/identity_separation.sh --apply >/tmp/o 2>&1 && test -s /srv/aao/trust/keys/aao-auditor-ed25519.pub"

echo "== T9 auditor-auditor isolation"
t "alt cannot enter primary keys" bash -c "! runuser -u aao-auditor-alt -- test -x /var/lib/aao-auditor/keys"
t "primary cannot read alt ledger" bash -c "! runuser -u aao-auditor -- test -r /var/lib/aao-auditor-alt/ledger"
t "alt cannot write own frozen checkout" bash -c "! runuser -u aao-auditor-alt -- test -w /srv/aao/frozen/aao-auditor-alt"

echo "== T10 integration with independent_audit.py custody + signature"
cp -r $R /tmp/repo && chown -R aao-auditor: /tmp/repo && chmod -R a+rX /tmp/repo
cat > /tmp/custody.py <<'PY'
import sys; sys.path.insert(0, "/tmp/repo/src")
from pathlib import Path
from aao.independent_audit import custody_problems
policy = {"trusted_auditor_revisions": [], "auditor_os_user": "aao-auditor", "developer_os_users": ["alessbarb", "aao-impl-codex"]}
print("\n".join(custody_problems(policy, Path("/var/lib/aao-auditor/keys/auditor-ed25519.pem"))))
PY
runuser -u aao-auditor -- git config --global --add safe.directory /tmp/repo
runuser -u aao-auditor -- python3 /tmp/custody.py > /tmp/c_aud 2>&1
t "as auditor: only the expected 'revision not reviewed' problem" bash -c "grep -q 'not an independently reviewed revision' /tmp/c_aud && [ \$(grep -c . /tmp/c_aud) -eq 1 ]"
runuser -u aao-impl-codex -- python3 /tmp/custody.py > /tmp/c_impl 2>&1
t "as implementer: rejected (wrong account, key unavailable)" bash -c "grep -q 'not running as the designated auditor' /tmp/c_impl && grep -q 'signing key is unavailable' /tmp/c_impl"
echo '{"x":1}' > /tmp/r.json && chmod 644 /tmp/r.json
runuser -u aao-auditor -- openssl pkeyutl -sign -inkey /var/lib/aao-auditor/keys/auditor-ed25519.pem -rawin -in /tmp/r.json -out /tmp/r.sig
t "signature verifies with published trust key" openssl pkeyutl -verify -pubin -inkey /srv/aao/trust/keys/aao-auditor-ed25519.pub -rawin -in /tmp/r.json -sigfile /tmp/r.sig
t "signature fails with the other auditor's key" bash -c "! openssl pkeyutl -verify -pubin -inkey /srv/aao/trust/keys/aao-auditor-alt-ed25519.pub -rawin -in /tmp/r.json -sigfile /tmp/r.sig >/dev/null 2>&1"

echo "== T13 installed trust root: frozen trees, venvs and the mirror do not fail the preflight"
mkdir -p /srv/aao/frozen/aao-auditor/tree/.git /srv/aao/frozen/aao-integrator/tree /srv/aao/frozen/aao-integrator/venv/bin /srv/aao/mirror
touch /srv/aao/frozen/aao-auditor/tree/.git/index /srv/aao/frozen/aao-auditor/tree/README.md
chown -R aao-auditor:aao-auditor /srv/aao/frozen/aao-auditor/tree && chown root:root /srv/aao/frozen/aao-auditor/tree/.git/index
chown -R root:root /srv/aao/frozen/aao-integrator/tree /srv/aao/frozen/aao-integrator/venv
ln -s /usr/bin/python3 /srv/aao/frozen/aao-integrator/venv/bin/python
chown aao-integrator:aao-integrator /srv/aao/mirror
t "installed host passes the preflight" bash -c "bash $S/identity_separation.sh --apply >/tmp/t13 2>&1"
ln -s /etc /srv/aao/frozen/aao-supervisor/tree
t "a pruned path that is a symlink fails closed" bash -c "! bash $S/identity_separation.sh --apply >/tmp/t13b 2>&1 && grep -q 'aao-supervisor/tree exists and is not a plain directory' /tmp/t13b"
rm /srv/aao/frozen/aao-supervisor/tree
touch /srv/aao/frozen/stray && chown aao-auditor /srv/aao/frozen/stray
t "content outside the pruned trees is still checked" bash -c "! bash $S/identity_separation.sh --apply >/tmp/t13c 2>&1 && grep -q 'frozen/stray is not owned by the owner of its directory' /tmp/t13c"
rm -rf /srv/aao/frozen/stray /srv/aao/frozen/aao-auditor/tree /srv/aao/frozen/aao-integrator/tree /srv/aao/frozen/aao-integrator/venv /srv/aao/mirror

echo "== T11b purge fails closed when the archive cannot be written"
t "purge with unwritable archive dir fails" bash -c "! AAO_ARCHIVE_DIR=/nonexistent bash $S/identity_separation.sh --purge >/tmp/pf 2>&1 && grep -q 'nothing was removed' /tmp/pf"
t "accounts preserved after failed purge" bash -c "id aao-auditor && id aao-pm" 
t "keys preserved after failed purge" test -f /var/lib/aao-auditor/keys/auditor-ed25519.pem
t "trust registry preserved after failed purge" test -d /srv/aao/trust/keys
t "sudoers preserved after failed purge" test -f /etc/sudoers.d/aao-launch

echo "== T11 revert is non-destructive"
t "revert" bash -c "bash $S/identity_separation.sh --revert >/tmp/rv 2>&1"
t "sudoers removed" test ! -e /etc/sudoers.d/aao-launch
t "accounts locked" bash -c "passwd -S aao-pm | grep -q ' L '"
t "keys kept" test -f /var/lib/aao-auditor/keys/auditor-ed25519.pem
t "CEO untouched" bash -c "id -nG alessbarb | grep -qw sudo"

t "after --revert, --apply refuses (locked agent shells); documented path is --purge then --apply" bash -c "! bash $S/identity_separation.sh --apply >/tmp/ra 2>&1"

echo "== T12 purge restores the pre-install state"
t "purge" bash -c "bash $S/identity_separation.sh --purge >/tmp/pg 2>&1"
snap /tmp/state_after
t "passwd/group/sudoers/dirs identical to initial state" diff -u /tmp/state_before /tmp/state_after
t "evidence archive kept (0600)" bash -c "f=\$(ls /root/aao-identity-archive-*.tar.gz) && [ \$(stat -c %a \$f) = 600 ] && tar -tzf \$f | grep -q 'var/lib/aao-auditor/keys/auditor-ed25519.pem'"
t "CEO account intact after purge" bash -c "id -nG alessbarb | grep -qw sudo && test -f /home/alessbarb/.config/gh/hosts.yml"

echo "== RESULT: $([ $FAILED = 0 ] && echo ALL PASS || echo FAILURES)"
exit $FAILED
