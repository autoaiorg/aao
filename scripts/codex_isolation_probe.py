#!/usr/bin/env python3
"""Prove, without calling any model, what a codex-run command can reach in the AAO agent runner.

It builds exactly the runner's confinement (aao.agent_runner.agent_jail + CODEX_SANDBOX_FLAGS) and runs
a probe through `codex sandbox`, the same Linux sandbox codex applies to model-run commands. The probe
tries the network, loopback services (dev PostgreSQL, API), the operator's credentials, the Docker
socket and writes outside the workspace. Exit status 0 only if every check holds; the JSON on stdout
is the evidence. No provider is activated and no codex login is needed.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

PROBE = r'''
import json, os, socket, sys
targets = json.loads(sys.argv[1])
out = {}
def connect(host, port):
    try:
        socket.create_connection((host, port), 3).close(); return "OPEN"
    except OSError as e:
        return "blocked: " + type(e).__name__
try:
    socket.getaddrinfo("github.com", 443); out["dns"] = "OPEN"
except OSError as e:
    out["dns"] = "blocked: " + type(e).__name__
out["internet_tcp_1.1.1.1:443"] = connect("1.1.1.1", 443)
for name, port in targets["loopback"].items():
    out[f"loopback_{name}:{port}"] = connect("127.0.0.1", port)
for path in targets["secrets"]:
    out["read " + path] = "VISIBLE" if os.path.exists(path) else "hidden"
for path in targets["sockets"]:
    out["socket " + path] = "VISIBLE" if os.path.exists(path) else "hidden"
for path in targets["no_write"]:
    try:
        open(path, "w").close(); out["write " + path] = "WRITABLE"
    except OSError as e:
        out["write " + path] = "denied: " + type(e).__name__
try:
    import tempfile; tempfile.NamedTemporaryFile(dir=os.environ["TMPDIR"]).close(); out["write scratch TMPDIR"] = "ok"
except (OSError, KeyError) as e:
    out["write scratch TMPDIR"] = "FAILED: " + type(e).__name__
try:
    open("probe-ok", "w").close(); out["write workspace"] = "ok"
except OSError as e:
    out["write workspace"] = "FAILED: " + type(e).__name__
out["sensitive_env"] = sorted(k for k in os.environ if any(t in k for t in ("TOKEN", "AAO_", "GH_", "GITHUB", "SECRET", "KEY", "PASSWORD")))
out["visible_pids"] = len([p for p in os.listdir("/proc") if p.isdigit()])
print(json.dumps(out))
'''


def main() -> int:
    control = "--control" in sys.argv[1:]  # negative control: no outer jail, network allowed; must FAIL
    from aao.agent_runner import agent_jail, codex_release, codex_sandbox_flags

    home = Path.home()
    runtime = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    secrets = [str(home / p) for p in (".config/gh/hosts.yml", ".codex/auth.json", ".ssh", ".gitconfig",
                                       ".git-credentials", ".docker/config.json")]
    secrets += [str(p) for p in ROOT.parent.glob("*/.env.local")] + [str(ROOT / ".env.local")]
    secrets += [str(Path(runtime) / n) for n in ("aao-self-development-agent.token", "aao-auditor.token",
                                                 "aao-publisher.token")]
    # Like the runner: workdir in /tmp, CODEX_HOME outside it (the pilot uses ~/.local/share/aao/codex-agent).
    data = Path(os.environ.get("XDG_DATA_HOME") or home / ".local" / "share") / "aao"
    data.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="aao-isolation-") as tmp, \
            tempfile.TemporaryDirectory(prefix="probe-codex-home-", dir=data) as codex_tmp:
        workdir = Path(tmp) / "work"
        (workdir / "repo").mkdir(parents=True)
        (workdir / "home").mkdir()
        (workdir / "scratch").mkdir()
        codex_home = Path(codex_tmp)
        targets = {"loopback": {"dev_postgres": 54329, "test_postgres": 55432, "aao_api": 8001},
                   "secrets": secrets, "sockets": ["/run/docker.sock", "/var/run/docker.sock", runtime + "/bus"],
                   "no_write": ["/etc/aao-probe", "/usr/aao-probe", str(codex_home / "aao-probe"),
                                str(workdir / "home" / "aao-probe")]}
        release = codex_release()
        # Same layout as the runner: the jail mounts the whole workdir; codex runs in workdir/repo.
        flags = codex_sandbox_flags(workdir)
        inner = [str(release / "bin" / "codex"), "sandbox", *flags, "--", "/usr/bin/python3", "-c", PROBE,
                 json.dumps(targets)]
        if control:
            flags = ("-c", "sandbox_mode=workspace-write", "-c", "sandbox_workspace_write.network_access=true")
            inner = [str(release / "bin" / "codex"), "sandbox", *flags, "--", "/usr/bin/python3", "-c", PROBE,
                     json.dumps(targets)]
            command = inner
        else:
            command = agent_jail(inner, workdir=workdir, codex_home=codex_home, release=release,
                                 cwd=workdir / "repo")
        env = {"PATH": "/usr/bin:/bin"} if not control else {
            "PATH": "/usr/bin:/bin", "HOME": str(home), "CODEX_HOME": str(codex_home), "TMPDIR": str(workdir / "scratch")}
        proc = subprocess.run(command, check=False, capture_output=True, text=True, timeout=120,
                              cwd=str(workdir / "repo") if control else "/", env=env)
        try:
            observed = json.loads(proc.stdout.strip().splitlines()[-1])
        except (IndexError, json.JSONDecodeError):
            print(json.dumps({"ok": False, "error": "probe produced no result", "stderr": proc.stderr[-2000:]}))
            return 1
    failures = [k for k, v in observed.items() if isinstance(v, str) and v in {"OPEN", "VISIBLE", "WRITABLE"}]
    failures += [k for k in ("write workspace", "write scratch TMPDIR") if observed.get(k) != "ok"]
    if observed.get("sensitive_env"):
        failures.append("sensitive_env")
    print(json.dumps({"ok": not failures, "control": control, "failures": failures, "codex_release": release.name,
                      "sandbox_flags": list(flags), "observed": observed}, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
