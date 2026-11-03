import subprocess
from pathlib import Path

import pytest

from aao.agent_runner import AgentRunnerError, run_agent_patch


def _git(path, *args):
    return subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True, text=True).stdout


def test_fixture_runs_in_clone_and_preserves_source(tmp_path, monkeypatch):
    from aao import agent_runner

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
    original_run = agent_runner.subprocess.run
    source_git_configs = []
    config_paths = []

    def record_git_command(argv, *args, **kwargs):
        if argv[:1] == ["git"] and str(repo) in argv and "--show-toplevel" in argv:
            config_path = kwargs["env"]["GIT_CONFIG_GLOBAL"]
            config_paths.append(Path(config_path))
            source_git_configs.append((Path(config_path).read_text(), Path(config_path).stat().st_mode & 0o777))
        return original_run(argv, *args, **kwargs)

    monkeypatch.setattr(agent_runner.subprocess, "run", record_git_command)
    before = _git(repo, "status", "--porcelain")
    result = run_agent_patch(repo, sha, "instructions", backend="fixture", timeout=20)
    assert result["changed_paths"] == ["src/aao/x.py"]
    assert result["patch"]
    assert _git(repo, "status", "--porcelain") == before
    assert source_git_configs
    assert all(f"directory = {repo.resolve()}" in config for config, _mode in source_git_configs)
    assert all(mode == 0o600 for _config, mode in source_git_configs)
    assert all(not path.exists() for path in config_paths)
    assert (repo / "src/aao/x.py").read_text() == "before\n"
    assert (result["provider"], result["model"], result["backend_version"]) == ("fixture", None, "fixture-v1")


def test_git_safe_directory_rejects_newline_in_path():
    from aao.agent_runner import AgentRunnerError, _git

    with pytest.raises(AgentRunnerError, match="unsafe Git safe.directory path"):
        _git(Path("/tmp/aao-safe\ndirectory = *"), "rev-parse", "HEAD",
             safe_directories=(Path("/tmp/aao-safe\ndirectory = *"),))


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
    monkeypatch.setenv("AAO_AGENT_DAILY_BUDGET_USD", "5")
    monkeypatch.delenv("AAO_AGENT_CODEX_HOME", raising=False)
    with pytest.raises(AgentRunnerError, match="dedicated AAO_AGENT_CODEX_HOME"):
        run_agent_patch(repo, sha, "x", backend="codex", timeout=3)


def _empty_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "--allow-empty", "-qm", "base"], check=True)
    return repo, _git(repo, "rev-parse", "HEAD").strip()


def test_codex_run_records_provider_pinned_model_and_real_cli_release(monkeypatch, tmp_path):
    """Evidence names who produced the patch; the recorded model is the one actually passed to codex."""
    from aao import agent_runner
    repo, sha = _empty_repo(tmp_path)
    argv_file = tmp_path / "argv"
    (tmp_path / "codex-home").mkdir()
    monkeypatch.setenv("AAO_AGENT_PROVIDER", "codex")
    monkeypatch.setenv("AAO_AGENT_DAILY_BUDGET_USD", "5")
    monkeypatch.setenv("AAO_AGENT_CODEX_HOME", str(tmp_path / "codex-home"))
    monkeypatch.setenv("AAO_AGENT_CODEX_MODEL", "gpt-5.1-codex")
    monkeypatch.setattr(agent_runner, "codex_release", lambda: tmp_path / "releases" / "0.164.0-x86_64-unknown-linux-musl")
    # Stand-in for the jailed CLI: records its argv and changes nothing (no model call).
    monkeypatch.setattr(agent_runner, "agent_jail", lambda argv, **kw: [
        "/bin/sh", "-c", 'printf "%s\\n" "$@" > "$0"', str(argv_file), *argv])
    result = run_agent_patch(repo, sha, "x", backend="codex", timeout=20)
    assert result["patch"] == ""
    assert result["provider"] == "openai" and result["model"] == "gpt-5.1-codex"
    assert result["backend_version"] == "codex-cli 0.164.0-x86_64-unknown-linux-musl"
    args = argv_file.read_text().splitlines()
    assert args[args.index("-m") + 1] == "gpt-5.1-codex"
    # Without a pin, nothing is passed and nothing is claimed about the CLI's default model.
    monkeypatch.delenv("AAO_AGENT_CODEX_MODEL")
    result = run_agent_patch(repo, sha, "x", backend="codex", timeout=20)
    assert result["model"] is None and "-m" not in argv_file.read_text().splitlines()


def test_codex_model_pin_is_validated(monkeypatch):
    from aao.agent_runner import backend_identity
    monkeypatch.setenv("AAO_AGENT_CODEX_MODEL", "--dangerously-bypass")
    with pytest.raises(AgentRunnerError, match="invalid codex model id"):
        backend_identity("codex")


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


@pytest.mark.parametrize("budget", [None, "", "abc", "0", "-1", "nan", "inf"])
def test_codex_refuses_without_a_positive_daily_budget(monkeypatch, tmp_path, budget):
    """Fail closed: an activated model backend never runs without a positive finite daily budget."""
    repo, sha = _empty_repo(tmp_path)
    (tmp_path / "codex-home").mkdir()
    monkeypatch.setenv("AAO_AGENT_PROVIDER", "codex")
    monkeypatch.setenv("AAO_AGENT_CODEX_HOME", str(tmp_path / "codex-home"))
    if budget is None:
        monkeypatch.delenv("AAO_AGENT_DAILY_BUDGET_USD", raising=False)
    else:
        monkeypatch.setenv("AAO_AGENT_DAILY_BUDGET_USD", budget)
    with pytest.raises(AgentRunnerError, match="daily budget required"):
        run_agent_patch(repo, sha, "x", backend="codex", timeout=3)


def test_daily_budget_accepts_only_a_positive_finite_value(monkeypatch):
    from aao.agent_runner import daily_budget_usd
    monkeypatch.setenv("AAO_AGENT_DAILY_BUDGET_USD", "0.5")
    assert daily_budget_usd() == 0.5
    monkeypatch.setenv("AAO_AGENT_DAILY_BUDGET_USD", "0")
    assert daily_budget_usd() is None


def test_ollama_backend_uses_only_loopback_and_zero_cost(monkeypatch, tmp_path):
    import json

    from aao import agent_runner

    repo, sha = _empty_repo(tmp_path)
    (repo / "src/aao").mkdir(parents=True)
    (repo / "src/aao/x.py").write_text("before\n")
    _git(repo, "config", "user.name", "test")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "add file")
    sha = _git(repo, "rev-parse", "HEAD").strip()
    patch = b"diff --git a/src/aao/x.py b/src/aao/x.py\n--- a/src/aao/x.py\n+++ b/src/aao/x.py\n@@ -1 +1 @@\n-before\n+after\n"

    class Response:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def read(self, _limit): return json.dumps({"model": "qwen3.5:9b", "response": patch.decode()}).encode()

    class Opener:
        def open(self, request, timeout):
            assert request.full_url == "http://127.0.0.1:11434/api/generate"
            assert timeout == 20
            request_data = json.loads(request.data)
            assert request_data["options"]["num_predict"] == 384
            assert request_data["think"] is False
            assert "UNTRUSTED REPOSITORY FILE: src/aao/x.py" in request_data["prompt"]
            assert "before" in request_data["prompt"]
            return Response()

    monkeypatch.setenv("AAO_AGENT_PROVIDER", "ollama")
    monkeypatch.setenv("AAO_AGENT_OLLAMA_MODEL", "qwen3.5:9b")
    monkeypatch.setenv("AAO_AGENT_DAILY_BUDGET_USD", "0")
    monkeypatch.setattr(agent_runner, "_ollama_opener", lambda: Opener())
    result = run_agent_patch(repo, sha, "edit x", backend="ollama", timeout=20, model="qwen3.5:9b")
    assert result["provider"] == "ollama-local" and result["model"] == "qwen3.5:9b"
    assert "-before\n+after" in result["patch"]
    assert (repo / "src/aao/x.py").read_text() == "before\n"


def test_ollama_repository_context_is_bounded_and_excludes_untracked_secret_paths(tmp_path):
    from aao.agent_runner import _ollama_repository_context

    repo, _sha = _empty_repo(tmp_path)
    (repo / "src/aao").mkdir(parents=True)
    (repo / "src/aao/module.py").write_text("safe source\n")
    (repo / "src/aao/.env.secret.py").write_text("API_TOKEN=do-not-send\n")
    (repo / "src/aao/private_notes.md").write_text("PRIVATE=do-not-send\n")
    _git(repo, "add", "src/aao/module.py", "src/aao/.env.secret.py", "src/aao/private_notes.md")
    context = _ollama_repository_context(repo, max_chars=128)
    assert len(context) <= 128
    assert "safe source" in context
    assert "do-not-send" not in context
    (repo / "src/aao/untracked.py").write_text("untracked content\n")
    assert "untracked content" not in _ollama_repository_context(repo)


def test_ollama_opener_does_not_follow_redirects():
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from urllib.error import HTTPError

    from aao.agent_runner import _ollama_opener

    remote_requests = []

    class RemoteHandler(BaseHTTPRequestHandler):
        def do_POST(self):
            remote_requests.append(self.path)
            self.send_response(200)
            self.end_headers()

        def log_message(self, *_args):
            pass

    remote = HTTPServer(("127.0.0.1", 0), RemoteHandler)
    remote_thread = threading.Thread(target=remote.serve_forever, daemon=True)
    remote_thread.start()

    class RedirectHandler(BaseHTTPRequestHandler):
        def do_POST(self):
            # urllib does not normally follow 307 redirects for POST; use 302
            # so this test proves our opener's redirect handler is required.
            self.send_response(302)
            self.send_header("Location", f"http://127.0.0.1:{remote.server_port}/capture")
            self.end_headers()

        def log_message(self, *_args):
            pass

    redirect = HTTPServer(("127.0.0.1", 0), RedirectHandler)
    redirect_thread = threading.Thread(target=redirect.serve_forever, daemon=True)
    redirect_thread.start()
    try:
        from urllib.request import Request

        req = Request(f"http://127.0.0.1:{redirect.server_port}/generate", data=b"private prompt", method="POST")
        with pytest.raises(HTTPError):
            _ollama_opener().open(req, timeout=3)
        assert remote_requests == []
    finally:
        redirect.shutdown()
        remote.shutdown()
        redirect.server_close()
        remote.server_close()
        redirect_thread.join(timeout=3)
        remote_thread.join(timeout=3)


def test_ollama_backend_requires_activation_and_pinned_model(monkeypatch, tmp_path):
    from aao import agent_runner
    from aao.agent_runner import backend_identity
    monkeypatch.delenv("AAO_AGENT_PROVIDER", raising=False)
    monkeypatch.setenv("AAO_AGENT_OLLAMA_MODEL", "qwen3.5:9b")
    with pytest.raises(AgentRunnerError, match="pinned AAO_AGENT_OLLAMA_MODEL"):
        backend_identity("ollama", model="--unsafe")
    repo, sha = _empty_repo(tmp_path)
    monkeypatch.setattr(agent_runner, "build_opener", lambda *_args: pytest.fail("network call must not occur"))
    with pytest.raises(AgentRunnerError, match="ollama backend disabled"):
        agent_runner.run_agent_patch(repo, sha, "task", backend="ollama", timeout=3, model="qwen3.5:9b")
