import subprocess

import pytest

from aao.agent_runner import AgentRunnerError, run_agent_patch


def _git(path, *args):
    return subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True, text=True).stdout


def test_fixture_runs_in_clone_and_preserves_source(tmp_path, monkeypatch):
    repo = tmp_path / "source"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "test")
    (repo / "src/aao").mkdir(parents=True)
    (repo / "src/aao/x.py").write_text("before\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "base")
    sha = _git(repo, "rev-parse", "HEAD").strip()
    patch_file = tmp_path / "change.patch"
    patch_file.write_text("diff --git a/src/aao/x.py b/src/aao/x.py\nindex 3367afd..d39c77f 100644\n--- a/src/aao/x.py\n+++ b/src/aao/x.py\n@@ -1 +1 @@\n-before\n+after\n")
    monkeypatch.setenv("AAO_AGENT_FIXTURE_PATCH", str(patch_file))
    before = _git(repo, "status", "--porcelain")
    result = run_agent_patch(repo, sha, "instructions", backend="fixture", timeout=20)
    assert result["changed_paths"] == ["src/aao/x.py"]
    assert result["patch"]
    assert _git(repo, "status", "--porcelain") == before
    assert (repo / "src/aao/x.py").read_text() == "before\n"


def test_codex_requires_provider(monkeypatch, tmp_path):
    monkeypatch.delenv("AAO_AGENT_PROVIDER", raising=False)
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "--allow-empty", "-qm", "base"], check=True)
    sha = _git(repo, "rev-parse", "HEAD").strip()
    with pytest.raises(AgentRunnerError, match="CEO provider activation"):
        run_agent_patch(repo, sha, "x", backend="codex", timeout=3)


def test_codex_requires_a_dedicated_codex_home(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "--allow-empty", "-qm", "base"], check=True)
    sha = _git(repo, "rev-parse", "HEAD").strip()
    monkeypatch.setenv("AAO_AGENT_PROVIDER", "codex")
    monkeypatch.delenv("AAO_AGENT_CODEX_HOME", raising=False)
    with pytest.raises(AgentRunnerError, match="dedicated AAO_AGENT_CODEX_HOME"):
        run_agent_patch(repo, sha, "x", backend="codex", timeout=3)


def test_agent_jail_hides_operator_state_and_mounts_only_the_workdir(tmp_path):
    from itertools import pairwise

    from aao.agent_runner import agent_jail, codex_sandbox_flags

    workdir, codex_home, release = tmp_path / "w", tmp_path / "c", tmp_path / "r"
    argv = agent_jail(["codex", "exec"], workdir=workdir, codex_home=codex_home, release=release)
    pairs = list(pairwise(argv))
    for hidden in ("/home", "/run", "/tmp", "/var/tmp", "/srv"):
        assert ("--tmpfs", hidden) in pairs
    assert "--clearenv" in argv and "--unshare-pid" in argv and "--die-with-parent" in argv
    assert argv[argv.index("--bind") + 1] == str(workdir)
    assert ("--ro-bind", str(release)) in pairs
    assert argv[-2:] == ["codex", "exec"]
    flags = " ".join(codex_sandbox_flags(workdir))
    assert "network_access=false" in flags and "exclude_slash_tmp=true" in flags
    assert str(workdir / "scratch") in flags


def test_isolation_probe_finds_no_leak():
    """Runs the real probe when codex and bubblewrap are installed (dev host); CI has no codex."""
    import json
    import shutil
    import sys
    from pathlib import Path

    if not (shutil.which("codex") and shutil.which("bwrap")):
        pytest.skip("codex CLI or bubblewrap not installed")
    script = Path(__file__).resolve().parents[1] / "scripts" / "codex_isolation_probe.py"
    proc = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, timeout=180, check=False)
    report = json.loads(proc.stdout)
    assert proc.returncode == 0 and report["ok"], report.get("failures")
