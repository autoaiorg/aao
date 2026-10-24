#!/usr/bin/python3 -I
"""Read-only host verifier for the trust-root install preconditions (BOOTSTRAP_DOSSIER).

Run by the CEO as root:  sudo /usr/bin/python3 -I verify_trust_root_host.py --expected-revision <sha>
It changes nothing. Exit 0 only if every check passes. Paste the full output in the bootstrap issue.

  1. Runtime exclusivity of the aao-auditor uid: only the auditor systemd units run as it, the account
     cannot be entered another way, and nobody but root (or the auditor itself, for its own git tree)
     can write the code it executes.
  2. Custody of the supervisor intake socket and its parent directory, the heartbeat, and the anchor.

Scope of a PASS: it attests the host configuration at the time of the run. Every way of starting a
process as the auditor that this checks (sudo policy, cron, polkit, systemd units, group membership,
login shell) can only be changed by root, i.e. by the trust root itself (P5 (a)); so the property holds
until root changes it. aao-trust-root-verify.timer re-runs this daily and on boot, and any FAIL must be
treated as the trust root being withdrawn (the integrator stays fail-closed without a fresh PASS).
"""
from __future__ import annotations

import argparse
import grp
import hashlib
import json
import os
import pwd
import re
import shutil
import stat
import subprocess
import sys
import sysconfig
from pathlib import Path

AUDITOR, SUPERVISOR, TRUST = "aao-auditor", "aao-supervisor", "aao-trust"
ANCHOR = Path("/etc/aao-audit/trust-anchor.json")
ANCHOR_FIELDS = {"schema", "policy_path", "policy_sha256", "auditor_uid", "auditor_public_key", "ledger_path",
                 "ledger_anchor_path", "attribution_path", "attribution_writer_uid",
                 "supervisor_public_key", "supervisor_key_id",
                 "supervisor_heartbeat_path", "supervisor_intake_socket"}
INTAKE_DIR = Path("/run/aao-veto-intake")
INTAKE_SOCKET = INTAKE_DIR / "veto.sock"
HEARTBEAT = Path("/var/lib/aao-heartbeat/heartbeat.json")
AUDITOR_ROOT = Path("/srv/aao/frozen/aao-auditor")
AUDITOR_CGROUP = re.compile(r"^0::/system\.slice/(system-aao\\x2dauditor\.slice/)?aao-auditor(@[^/]+|-dispatch)\.service$")
INTAKE_CGROUP = re.compile(r"^0::/system\.slice/aao-supervisor-intake\.service$")
TOOLS = ("git", "bwrap", "openssl", "timeout", "prlimit")
# Root-equivalent principals are the trust root itself (P5 (a)), not a threat to exclusivity. Any other
# account that can become root or the auditor is a FAIL.
CEO_USER = os.environ.get("AAO_CEO_USER", "alessbarb")
ROOT_EQUIVALENT_GROUPS = ("sudo", "admin", "wheel", "docker", "lxd", "libvirt", "disk")
UNITS = {"aao-auditor@probe.service": "aao-auditor@.service",
         "aao-auditor-dispatch.service": "aao-auditor-dispatch.service",
         "aao-auditor-dispatch.path": "aao-auditor-dispatch.path",
         "aao-auditor-dispatch.timer": "aao-auditor-dispatch.timer",
         "aao-integrator-tick.service": "aao-integrator-tick.service",
         "aao-integrator-tick.timer": "aao-integrator-tick.timer",
         "aao-supervisor-attribution.service": "aao-supervisor-attribution.service",
         "aao-supervisor-attribution.timer": "aao-supervisor-attribution.timer",
         "aao-supervisor-intake.service": "aao-supervisor-intake.service"}
results: list[tuple[bool, str, str]] = []


def check(ok: bool, name: str, detail: str = "") -> bool:
    results.append((ok, name, detail))
    return ok


def uid(name: str) -> int:
    return pwd.getpwnam(name).pw_uid


def gid(name: str) -> int:
    return grp.getgrnam(name).gr_gid


def _group(name: str):
    try:
        return grp.getgrnam(name)
    except KeyError:
        return None


def ancestors_safe(path: Path, writers: set[int]) -> str:
    """'' if no ancestor of path is a symlink or writable by a uid outside `writers` (root always allowed)."""
    for parent in Path(os.path.abspath(path)).parents:
        info = os.lstat(parent)
        if stat.S_ISLNK(info.st_mode):
            return f"{parent} is a symlink"
        sticky_root = info.st_mode & stat.S_ISVTX and info.st_uid == 0
        if (info.st_mode & 0o022 and not sticky_root) or info.st_uid not in {0, *writers}:
            return f"{parent} owner={info.st_uid} mode={oct(stat.S_IMODE(info.st_mode))}"
    return ""


def root_only(path: Path) -> bool:
    """path (already resolved) and every ancestor are root-owned and not group/other writable."""
    info = os.lstat(path)
    return info.st_uid == 0 and not info.st_mode & 0o022 and not ancestors_safe(path, set())


def tree_writers(root: Path, owners: set[int]) -> list[str]:
    """Entries under root (inclusive) owned outside `owners`, or group/other writable. A symlink must resolve
    inside root, or to a root-only file outside it (e.g. the venv's /usr/bin/python3.12)."""
    bad = []
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in [".", *dirs, *files]:
            path = Path(directory) if name == "." else Path(directory) / name
            info = os.lstat(path)
            if stat.S_ISLNK(info.st_mode):
                target = Path(os.path.realpath(path))
                if not target.exists() or not (target.is_relative_to(root) or root_only(target)):
                    bad.append(f"{path} -> {target}")
                continue
            if info.st_uid not in owners or info.st_mode & 0o022:
                bad.append(f"{path} owner={info.st_uid} mode={oct(stat.S_IMODE(info.st_mode))}")
            if len(bad) >= 5:
                return bad
    return bad


def processes() -> list[tuple[int, set[int], str]]:
    found = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            status = (entry / "status").read_text()
            cgroup = (entry / "cgroup").read_text().strip()
        except OSError:
            continue
        uids = next((set(map(int, line.split()[1:])) for line in status.splitlines() if line.startswith("Uid:")), set())
        found.append((int(entry.name), uids, cgroup))
    return found


def runas_users(sudo_list_output: str) -> set[str]:
    """Run-as users from `sudo -l -U <user>` output (sudo resolves aliases and #include/@includedir itself)."""
    users: set[str] = set()
    for match in re.finditer(r"^\s*\(([^)]*)\)", sudo_list_output, re.MULTILINE):
        users.update(item.strip() for item in match.group(1).split(":", 1)[0].split(","))
    return users


def sudo_grants(target: str) -> list[str]:
    """Accounts other than root and the CEO whose effective sudo policy can run commands as `target` or ALL."""
    bad = []
    for account in pwd.getpwall():
        if account.pw_uid == 0 or account.pw_name == CEO_USER:
            continue
        result = subprocess.run(["sudo", "-n", "-l", "-U", account.pw_name], check=False, capture_output=True,
                                text=True, env={"PATH": "/usr/bin:/bin", "LANG": "C"})
        if result.returncode not in (0, 1):
            bad.append(f"{account.pw_name}: cannot evaluate sudo policy ({result.stderr.strip()[:80]})")
            continue
        # root reaches every uid, so a grant to run as root is a grant to run as the target.
        reach = runas_users(result.stdout) & {"ALL", target, f"#{uid(target)}", "root", "#0"}
        if reach:
            bad.append(f"{account.pw_name}: runas {sorted(reach)}")
    return bad


def cron_entries(target: str) -> list[str]:
    """User spools owned by target plus system crontabs whose user field is target."""
    found = [str(p) for d in ("/var/spool/cron/crontabs", "/var/spool/cron/atjobs") if Path(d).is_dir()
             for p in Path(d).iterdir() if p.lstat().st_uid == uid(target)]
    for path in [Path("/etc/crontab"), *sorted(Path("/etc/cron.d").glob("*"))]:
        if not path.is_file():
            continue
        for line in path.read_text(errors="replace").splitlines():
            fields = line.split("#", 1)[0].split()
            user = fields[1] if fields and fields[0].startswith("@") and len(fields) > 1 else (
                fields[5] if len(fields) > 5 else "")
            if user == target:
                found.append(f"{path}: {line.strip()}")
    return found


POLKIT_ACTIONS = ("org.freedesktop.systemd1.manage-units", "org.freedesktop.systemd1.manage-unit-files",
                  "org.freedesktop.systemd1.reload-daemon", "org.freedesktop.machine1.shell",
                  "org.freedesktop.machine1.host-shell")
POLKIT_DIRS = ("/etc/polkit-1/rules.d", "/usr/share/polkit-1/rules.d", "/usr/local/share/polkit-1/rules.d",
               "/run/polkit-1/rules.d", "/etc/polkit-1/localauthority", "/var/lib/polkit-1/localauthority",
               # AdminIdentities (who satisfies auth_admin) for the legacy local authority; for the JS
               # backend addAdminRule lives in the rules.d files above. Admins must be E5's groups.
               "/etc/polkit-1/localauthority.conf.d", "/usr/share/polkit-1/localauthority.conf.d")


def _package_pristine(path: Path) -> bool:
    """path is a regular file of an installed dpkg package and `dpkg --verify` reports no change to it."""
    if path.is_symlink() or not path.is_file():
        return False
    owner = subprocess.run(["dpkg", "-S", str(path)], check=False, capture_output=True, text=True)
    if owner.returncode:
        return False
    package = owner.stdout.split(":", 1)[0].strip()
    verify = subprocess.run(["dpkg", "--verify", package], check=False, capture_output=True, text=True)
    return verify.returncode == 0 and str(path) not in verify.stdout


def polkit_grants(target: str) -> list[str]:
    """Polkit paths to start processes as another uid (systemd-run --uid, transient units, machinectl shell).

    The verifier does not evaluate JavaScript rules, so it does not try to decide which rules are relevant:
    EVERY file in every rules/localauthority directory must be an unmodified file of an installed package.
    Implicit authorizations of the unit/machine actions must require an admin (E5's root-equivalent groups).
    Any query that cannot be completed is a FAIL (fail closed)."""
    found = []
    for action in POLKIT_ACTIONS:
        shown = subprocess.run(["pkaction", "--action-id", action, "--verbose"], check=False, capture_output=True,
                               text=True)
        values = re.findall(r"implicit (any|inactive|active):\s+(\S+)", shown.stdout)
        if shown.returncode == 1 and "No action with action id" in shown.stderr + shown.stdout:
            continue  # action not registered: polkit denies it
        if shown.returncode or len(values) != 3:
            found.append(f"{action}: cannot read implicit authorizations (rc={shown.returncode})")
            continue
        found += [f"{action} implicit {kind} {value}" for kind, value in values
                  if value not in ("auth_admin", "auth_admin_keep", "no")]
    for directory in POLKIT_DIRS:
        try:
            paths = sorted(Path(directory).rglob("*")) if Path(directory).exists() else []
        except OSError as error:
            found.append(f"{directory}: cannot list ({error})")
            continue
        files = [path for path in paths if not path.is_dir()]
        found += [f"{path} (local or modified rule)" for path in files if not _package_pristine(path)]
        identities, problems = admin_identities([path for path in files if path.is_file()])
        found += problems
        found += [f"{directory}: admin identity {identity} is not root or an E5 group"
                  for identity in admin_identities_ok(identities)]
    return found


_STRICT_ADMIN_RULE = re.compile(
    r"polkit\.addAdminRule\(\s*function\s*\([^)]*\)\s*\{\s*return\s*\[\s*"
    r"((?:\"unix-(?:user|group):[\w.-]+\"\s*,?\s*)*)\]\s*;?\s*\}\s*\)")


def admin_identities(paths: list[Path]) -> tuple[set[str], list[str]]:
    """Identities that can satisfy auth_admin: AdminIdentities= in local-authority .conf files, and the
    returned list of every addAdminRule. Fail closed: an addAdminRule whose whole body is not exactly
    `return ["unix-user:x", "unix-group:y", ...];` (only string literals) cannot be evaluated and is a problem."""
    identities: set[str] = set()
    problems = []
    for path in paths:
        # No comment/string stripping (that needs a JS parser): any occurrence of addAdminRule, even in a
        # comment or a string, must be a strict match, otherwise the file FAILs.
        text = path.read_text(errors="replace")
        strict = _STRICT_ADMIN_RULE.findall(text)
        if text.count("addAdminRule") != len(strict):
            problems.append(f"{path}: addAdminRule is not a plain list of literal identities")
        for body in strict:
            identities.update(re.findall(r"unix-(?:user|group):[\w.-]+", body))
        for line in text.splitlines():
            if line.strip().startswith("AdminIdentities"):
                identities.update(i.strip() for i in line.split("=", 1)[1].split(";") if i.strip())
    return identities, problems


def admin_identities_ok(identities: set[str]) -> list[str]:
    allowed = {"unix-user:0", "unix-user:root", *(f"unix-group:{g}" for g in ROOT_EQUIVALENT_GROUPS)}
    return sorted(identities - allowed)


UNIT_DIRS = ("/etc/systemd/system", "/run/systemd/system", "/run/systemd/transient", "/run/systemd/generator",
             "/run/systemd/generator.early", "/run/systemd/generator.late", "/usr/local/lib/systemd/system",
             "/usr/lib/systemd/system", "/lib/systemd/system")


def units_running_as(target: str, allowed: set[str]) -> list[str]:
    """Unit files or drop-ins (any search path) that set User= to the target, other than the reviewed ones."""
    found = []
    names = {target, str(uid(target))}
    for directory in UNIT_DIRS:
        for path in sorted(Path(directory).rglob("*")) if Path(directory).is_dir() else []:
            if not path.is_file():
                continue
            users = re.findall(r"^\s*User\s*=\s*(\S+)", path.read_text(errors="replace"), re.MULTILINE)
            if names & set(users) and path.name not in allowed:
                found.append(str(path))
    return found


def unit_is_expected(unit: str, expected: Path) -> str:
    """'' if systemd loads `unit` from exactly one root-only fragment equal to the reviewed file, no drop-ins."""
    shown = subprocess.run(["systemctl", "show", "-p", "FragmentPath", "-p", "DropInPaths", "--", unit],
                           check=False, capture_output=True, text=True).stdout
    props = dict(line.split("=", 1) for line in shown.splitlines() if "=" in line)
    fragment = props.get("FragmentPath", "")
    if not fragment or props.get("DropInPaths", ""):
        return f"fragment={fragment!r} dropins={props.get('DropInPaths', '')!r}"
    path = Path(fragment)
    if path.is_symlink() or not root_only(path):
        return f"{fragment} is a symlink or not root-only"
    if path.read_bytes() != expected.read_bytes():
        return f"{fragment} differs from reviewed {expected}"
    return ""


def exclusivity(expected_revision: str) -> None:
    account = pwd.getpwnam(AUDITOR)
    check(account.pw_shell in ("/usr/sbin/nologin", "/sbin/nologin", "/bin/false"), "E1 auditor shell is nologin",
          account.pw_shell)
    try:
        shadow = next((line.split(":")[1] for line in Path("/etc/shadow").read_text().splitlines()
                       if line.startswith(AUDITOR + ":")), "")
    except OSError as error:
        shadow = repr(error)
    check(shadow[:1] in ("!", "*"), "E2 auditor password is locked", shadow[:1] if shadow[:1] not in "!*" else "")
    check(not Path(f"/var/lib/systemd/linger/{AUDITOR}").exists(), "E3 no systemd user linger for auditor")
    cron = cron_entries(AUDITOR)
    check(not cron, "E4 no cron/at job runs as auditor (user spools, /etc/crontab, /etc/cron.d)", "; ".join(cron))
    # SSH: sshd always executes the account shell (also for ForceCommand), so E1 already denies it.
    groups = [g for g in map(_group, ROOT_EQUIVALENT_GROUPS) if g]
    root_eq = sorted(({m for g in groups for m in g.gr_mem} |
                      {a.pw_name for a in pwd.getpwall() if any(a.pw_gid == g.gr_gid for g in groups)}) - {CEO_USER})
    check(not root_eq, "E5 no account besides the CEO is in a root-equivalent group", ", ".join(root_eq))
    grants = sudo_grants(AUDITOR)
    check(not grants, "E6 effective sudo policy (sudo -l -U, aliases/includes resolved): only root/CEO can "
          "run as auditor", "; ".join(grants))
    polkit = polkit_grants(AUDITOR)
    check(not polkit, "E6b no local polkit rule grants unit management or mentions the auditor", "; ".join(polkit))
    units = units_running_as(AUDITOR, {"aao-auditor@.service", "aao-auditor-dispatch.service"})
    check(not units, "E7a no other unit (any search path, incl. transient/generated) sets User=aao-auditor",
          "; ".join(units))
    strays = [f"pid {pid} {cg}" for pid, uids, cg in processes()
              if account.pw_uid in uids and not AUDITOR_CGROUP.match(cg)]
    check(not strays, "E7 every auditor-uid process is inside an aao-auditor unit", "; ".join(strays[:5]))
    for unit, reviewed in UNITS.items():
        problem = unit_is_expected(unit, AUDITOR_ROOT / "tree" / "deploy" / "systemd" / reviewed)
        check(not problem, f"E8 {unit}: single root-only fragment identical to the reviewed file, no drop-ins",
              problem)
    # Write closure of the auditor's code.
    tree, venv = AUDITOR_ROOT / "tree", AUDITOR_ROOT / "venv"
    problem = ancestors_safe(AUDITOR_ROOT, {uid(TRUST)})
    check(not problem, "E9 frozen auditor directory ancestors are protected", problem)
    bad = tree_writers(tree, {0, account.pw_uid})
    check(tree.is_dir() and not bad, "E10 auditor git tree: no writer besides root/auditor", "; ".join(bad))
    revision = subprocess.run(["git", "-c", "safe.directory=*", "-C", str(tree), "rev-parse", "HEAD"],
                              check=False, capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "-c", "safe.directory=*", "-C", str(tree), "status", "--porcelain",
                            "--untracked-files=all"], check=False, capture_output=True, text=True).stdout.strip()
    check(revision == expected_revision and not dirty, "E11 auditor tree is clean at the expected revision",
          f"HEAD={revision} dirty={bool(dirty)}")
    bad = tree_writers(venv, {0})
    check(venv.is_dir() and not bad, "E12 auditor venv is root-owned, no group/other write", "; ".join(bad))
    # Same write closure for the other frozen roles (C-1 of the 0a55daf audit): root-built by host_bootstrap,
    # skipped by identity_separation.sh on an installed host, so they are verified here.
    for role in ("aao-supervisor", "aao-integrator"):
        frozen = AUDITOR_ROOT.parent / role
        problem = ancestors_safe(frozen, {uid(TRUST)})
        check(not problem, f"E9 frozen {role} directory ancestors are protected", problem)
        bad = tree_writers(frozen / "tree", {0})
        check((frozen / "tree").is_dir() and not bad, f"E10 {role} git tree is root-only writable", "; ".join(bad))
        revision = subprocess.run(["git", "-c", "safe.directory=*", "-C", str(frozen / "tree"), "rev-parse", "HEAD"],
                                  check=False, capture_output=True, text=True).stdout.strip()
        dirty = subprocess.run(["git", "-c", "safe.directory=*", "-C", str(frozen / "tree"), "status", "--porcelain",
                                "--untracked-files=all"], check=False, capture_output=True, text=True).stdout.strip()
        check(revision == expected_revision and not dirty, f"E11 {role} tree is clean at the expected revision",
              f"HEAD={revision} dirty={bool(dirty)}")
        bad = tree_writers(frozen / "venv", {0})
        check((frozen / "venv").is_dir() and not bad, f"E12 {role} venv is root-owned, no group/other write", "; ".join(bad))
    base = Path(os.path.realpath(venv / "bin" / "python"))
    stdlib = Path(sysconfig.get_paths()["stdlib"])
    bad = [f"{base}"] if base.lstat().st_uid != 0 or base.lstat().st_mode & 0o022 or ancestors_safe(base, set()) else []
    bad += tree_writers(stdlib, {0})
    check(not bad, "E13 base interpreter and stdlib are root-only writable", "; ".join(bad))
    bad = []
    for tool in TOOLS:
        path = shutil.which(tool, path="/usr/bin:/bin")
        real = Path(os.path.realpath(path)) if path else None
        if real is None or real.lstat().st_uid != 0 or real.lstat().st_mode & 0o022 or ancestors_safe(real, set()):
            bad.append(f"{tool}={real}")
    check(not bad, "E14 git/bwrap/openssl/timeout/prlimit are root-only writable", ", ".join(bad))
    key = Path(f"/var/lib/{AUDITOR}/keys/auditor-ed25519.pem")
    info = key.lstat() if key.exists() else None
    check(bool(info) and stat.S_ISREG(info.st_mode) and info.st_uid == account.pw_uid and
          stat.S_IMODE(info.st_mode) == 0o600, "E15 auditor signing key is auditor-owned 0600")


def socket_custody() -> None:
    supervisor, auditor_gid, ledger_gid = uid(SUPERVISOR), gid(AUDITOR), gid("aao-ledger-read")
    info = os.lstat(INTAKE_DIR) if INTAKE_DIR.exists() else None
    check(bool(info) and stat.S_ISDIR(info.st_mode) and info.st_uid == supervisor and info.st_gid == auditor_gid
          and stat.S_IMODE(info.st_mode) == 0o2750, "S1 intake dir is aao-supervisor:aao-auditor 2750",
          f"{info and (info.st_uid, info.st_gid, oct(stat.S_IMODE(info.st_mode)))}")
    problem = ancestors_safe(INTAKE_DIR, set())
    check(not problem, "S2 intake dir ancestors are root-owned and not writable", problem)
    info = os.lstat(INTAKE_SOCKET) if INTAKE_SOCKET.exists() else None
    check(bool(info) and stat.S_ISSOCK(info.st_mode) and info.st_uid == supervisor and info.st_gid == auditor_gid
          and stat.S_IMODE(info.st_mode) == 0o660, "S3 intake socket is aao-supervisor:aao-auditor 0660")
    inodes = {line.split()[6] for line in Path("/proc/net/unix").read_text().splitlines()[1:]
              if len(line.split()) >= 8 and line.split()[7] == str(INTAKE_SOCKET) and line.split()[5] == "01"}
    owners = set()
    for pid, uids, cgroup in processes():
        try:
            links = {os.readlink(fd) for fd in Path(f"/proc/{pid}/fd").iterdir()}
        except OSError:
            continue
        if any(f"socket:[{inode}]" in links for inode in inodes):
            owners.add((pid, frozenset(uids), cgroup))
    check(bool(owners) and all(uids == {supervisor} and INTAKE_CGROUP.match(cg) for _, uids, cg in owners),
          "S4 only aao-supervisor-intake.service listens on the socket", f"{sorted(owners, key=lambda o: o[0])}")
    info = os.lstat(HEARTBEAT.parent) if HEARTBEAT.parent.exists() else None
    check(bool(info) and info.st_uid == supervisor and info.st_gid == ledger_gid and
          stat.S_IMODE(info.st_mode) == 0o2750 and not ancestors_safe(HEARTBEAT.parent, set()),
          "S5 heartbeat dir is aao-supervisor:aao-ledger-read 2750")
    info = os.lstat(HEARTBEAT) if HEARTBEAT.exists() else None
    check(bool(info) and stat.S_ISREG(info.st_mode) and info.st_uid == supervisor and
          not info.st_mode & 0o022, "S6 heartbeat file is supervisor-owned, not group/other writable")


def anchor(expected_revision: str) -> None:
    info = os.lstat(ANCHOR) if ANCHOR.exists() else None
    if not check(bool(info) and stat.S_ISREG(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022
                 and not ancestors_safe(ANCHOR, set()), "T1 trust anchor is root-owned and protected"):
        return
    data = json.loads(ANCHOR.read_bytes())
    check(set(data) == ANCHOR_FIELDS, "T2 anchor has exactly the fields of manifest_audit._ANCHOR_FIELDS")
    check(data.get("auditor_uid") == uid(AUDITOR), "T3 anchor auditor_uid is aao-auditor")
    check(data.get("attribution_writer_uid") == uid(SUPERVISOR), "T3b attribution writer is aao-supervisor")
    check(data.get("supervisor_intake_socket") == str(INTAKE_SOCKET) and
          data.get("supervisor_heartbeat_path") == str(HEARTBEAT), "T4 anchor points at the verified socket/heartbeat")
    policy_path = Path(data.get("policy_path", "/nonexistent"))
    try:
        policy = json.loads(policy_path.read_bytes())
        digest = hashlib.sha256(json.dumps(policy, sort_keys=True, separators=(",", ":"),
                                           ensure_ascii=False).encode()).hexdigest()
    except (OSError, ValueError):
        policy, digest = {}, ""
    check(digest == data.get("policy_sha256") and policy_path.stat().st_uid == uid(AUDITOR) if policy else False,
          "T5 pinned policy digest matches and the policy is auditor-owned")
    check(expected_revision in policy.get("trusted_auditor_revisions", []),
          "T6 policy trusts exactly the frozen auditor revision", f"{policy.get('trusted_auditor_revisions')}")


STATUS_FILE = Path("/var/lib/aao-trust-verify/status.json")


def write_status(path: Path, expected_revision: str, verifier_sha256: str) -> None:
    """Atomic, root-owned 0644 status the integrator requires (fresh PASS) before any promotion."""
    from datetime import UTC, datetime

    failed = [name for ok, name, _ in results if not ok]
    status = {"schema": "aao.trust-root-verification.v1", "result": "FAIL" if failed else "PASS",
              "expected_revision": expected_revision, "verified_at": datetime.now(UTC).isoformat(),
              "failed": failed, "verifier_sha256": verifier_sha256}
    path.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(status, handle, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temporary, 0o644)
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--expected-revision", help="trust-root candidate SHA (40 hex)")
    source.add_argument("--expected-revision-file", type=Path, help="root-owned file holding that SHA")
    parser.add_argument("--smoke", action="store_true", help="non-root smoke run; unreadable checks FAIL")
    parser.add_argument("--status-file", type=Path, help=f"write the result for the integrator (production: {STATUS_FILE})")
    args = parser.parse_args()
    if os.geteuid() != 0 and not args.smoke:
        print("run as root (it only reads): sudo /usr/bin/python3 -I " + sys.argv[0], file=sys.stderr)
        return 2
    if args.expected_revision_file:
        if not root_only(args.expected_revision_file):
            print("expected-revision file must be root-only", file=sys.stderr)
            return 2
        args.expected_revision = args.expected_revision_file.read_text().strip()
    if not re.fullmatch(r"[0-9a-f]{40}", args.expected_revision):
        print("--expected-revision must be a full SHA", file=sys.stderr)
        return 2
    for section in (lambda: exclusivity(args.expected_revision), socket_custody,
                    lambda: anchor(args.expected_revision)):
        try:
            section()
        except (OSError, KeyError, ValueError) as error:
            check(False, "section aborted", repr(error))
    me = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    if args.status_file:
        write_status(args.status_file, args.expected_revision, me)
    print(f"verify_trust_root_host.py sha256={me} expected_revision={args.expected_revision}")
    for ok, name, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail and not ok else ""))
    failed = sum(not ok for ok, _, _ in results)
    print(f"RESULT: {'PASS' if not failed else f'{failed} FAIL'} ({len(results)} checks)")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
