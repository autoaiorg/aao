"""Run a bounded agent against a disposable clone and return its patch evidence."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from aao.patch_proposals import PatchProposalError, inspect_patch

_SHA = re.compile(r"^[0-9a-f]{40}$")

class AgentRunnerError(ValueError):
    pass

def _git(repo: Path, *args: str, timeout: int = 30) -> str:
    env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": "/nonexistent", "LANG": "C.UTF-8",
           "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
           "GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0",
           "GIT_NO_REPLACE_OBJECTS": "1"}
    try:
        p = subprocess.run(["git", "-C", str(repo), *args], cwd="/", env=env,
                           stdin=subprocess.DEVNULL, capture_output=True, text=True,
                           timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise AgentRunnerError("isolated Git operation failed") from exc
    if p.returncode:
        raise AgentRunnerError(f"isolated git {args[0]} failed: configured repository or revision unavailable")
    return p.stdout

# Codex's own sandbox for model-run commands: writes only in the workspace, no network (set explicitly).
CODEX_SANDBOX_FLAGS = ("-c", "sandbox_mode=workspace-write", "-c", "sandbox_workspace_write.network_access=false",
                       "-c", "sandbox_workspace_write.exclude_slash_tmp=true",
                       "-c", "sandbox_workspace_write.exclude_tmpdir_env_var=true")


def codex_release() -> Path:
    """The real codex install directory (``.../releases/<version>``), resolved from PATH."""
    found = shutil.which("codex")
    if not found:
        raise AgentRunnerError("codex CLI not found")
    binary = Path(found).resolve()
    return binary.parents[1]


_MODEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")


def backend_identity(backend: str) -> dict:
    """Who produces the patch, for the evidence: provider, model and the real CLI release.

    ``model`` is the one pinned with AAO_AGENT_CODEX_MODEL (passed to codex as ``-m``); None means the CLI's
    own default, which AAO does not observe and therefore does not record."""
    if backend != "codex":
        return {"backend": backend, "provider": "fixture", "model": None, "backend_version": "fixture-v1"}
    model = os.getenv("AAO_AGENT_CODEX_MODEL") or None
    if model is not None and not _MODEL.fullmatch(model):
        raise AgentRunnerError("invalid AAO_AGENT_CODEX_MODEL")
    try:
        version = "codex-cli " + codex_release().name
    except AgentRunnerError:
        version = "codex-cli unavailable"
    return {"backend": backend, "provider": "openai", "model": model, "backend_version": version}


def agent_jail(argv: list[str], *, workdir: Path, codex_home: Path, release: Path,
               cwd: Path | None = None) -> list[str]:
    """Outer bwrap around the codex CLI so that neither it nor the model's commands can read the operator's
    credentials: /home, /run (runtime tokens, docker socket), /tmp, /var/tmp and /srv are replaced by empty
    tmpfs; only the disposable workdir, the dedicated CODEX_HOME and the codex release are mounted back.
    Network stays shared for the CLI's own API calls; model commands are cut off by CODEX_SANDBOX_FLAGS."""
    bwrap = shutil.which("bwrap")
    if not bwrap:
        raise AgentRunnerError("bubblewrap is required for the codex backend")
    return [bwrap, "--die-with-parent", "--new-session", "--unshare-pid", "--unshare-ipc", "--unshare-uts",
            "--ro-bind", "/", "/", "--tmpfs", "/home", "--tmpfs", "/run",
            "--ro-bind-try", "/run/systemd/resolve", "/run/systemd/resolve",
            "--tmpfs", "/tmp", "--tmpfs", "/var/tmp", "--tmpfs", "/srv", "--dev", "/dev", "--proc", "/proc",
            "--bind", str(workdir), str(workdir), "--bind", str(codex_home), str(codex_home),
            "--ro-bind", str(release), str(release),
            "--clearenv", "--setenv", "PATH", "/usr/local/bin:/usr/bin:/bin", "--setenv", "LANG", "C.UTF-8",
            "--setenv", "HOME", str(workdir / "home"), "--setenv", "CODEX_HOME", str(codex_home),
            "--setenv", "TMPDIR", str(workdir / "scratch"),
            "--chdir", str(cwd or workdir), "--", *argv]


def codex_sandbox_flags(workdir: Path) -> tuple[str, ...]:
    """CODEX_SANDBOX_FLAGS plus the workdir's private scratch (TMPDIR) as the only extra writable root."""
    return (*CODEX_SANDBOX_FLAGS, "-c", f'sandbox_workspace_write.writable_roots=["{workdir / "scratch"}"]')


_EMAIL = re.compile(r"^[A-Za-z0-9._+-]{1,64}@[A-Za-z0-9.-]{1,128}$")


def _commit_candidate(clone: Path, env: dict, *, author_email: str, message: str,
                      store: Path, changed_paths: list[str], check_id: str | None) -> dict:
    """Commit the agent's worktree under a fixed identity, keep it under a durable ref, and test it."""
    if not _EMAIL.fullmatch(author_email):
        raise AgentRunnerError("invalid candidate author identity")
    identity = {"GIT_AUTHOR_NAME": "AAO agent", "GIT_AUTHOR_EMAIL": author_email,
                "GIT_COMMITTER_NAME": "AAO agent", "GIT_COMMITTER_EMAIL": author_email}
    _git(clone, "add", "-A", "--", ".", timeout=10)
    proc = subprocess.run(["git", "-C", str(clone), "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false",
                           "commit", "--quiet", "--no-verify", "-F", "-"], input=message, text=True,
                          capture_output=True, env={**env, **identity}, cwd="/", timeout=30, check=False)
    if proc.returncode:
        raise AgentRunnerError("failed to commit the candidate")
    candidate_sha = _git(clone, "rev-parse", "HEAD").strip()
    if not store.exists():
        store.parent.mkdir(parents=True, exist_ok=True)
        _git(store.parent, "init", "--quiet", "--bare", str(store))
        # Accept candidates from shallow sources (e.g. a depth-1 CI checkout).
        _git(store, "config", "receive.shallowUpdate", "true")
    ref = f"refs/aao/candidates/{candidate_sha}"
    _git(clone, "push", "--quiet", str(store), f"HEAD:{ref}")
    result: dict = {"candidate_sha": candidate_sha, "candidate_ref": ref}
    if check_id:
        from aao.sandboxed_repository_checks import RepositoryCheckError, run_repository_check
        # Only test files the patch adds: modified tests may need the host (e.g. they launch the sandbox
        # themselves) and are validated by CI on the PR.
        added = set(_git(clone, "diff", "--name-only", "--diff-filter=A", "HEAD~1", "HEAD").split())
        extra = tuple(p for p in changed_paths if p in added
                      and re.fullmatch(r"tests/test_[A-Za-z0-9_]+\.py", p) and (clone / p).is_file())
        try:
            check = run_repository_check(clone, check_id, extra)
        except RepositoryCheckError as exc:
            check = {"check_id": check_id, "conclusion": "failure", "error": str(exc)[:500]}
        if check.get("candidate_sha", candidate_sha) != candidate_sha:
            raise AgentRunnerError("checks ran on a different revision")
        result["check"] = check
    return result


def run_agent_patch(repository, base_sha: str, instructions: str, *, backend: str,
                    timeout: int, patch_file: str | None = None,
                    candidate_store: str | Path | None = None, author_email: str = "agent@aao.invalid",
                    commit_message: str = "AAO candidate", check_id: str | None = None) -> dict:
    if not _SHA.fullmatch(base_sha):
        raise AgentRunnerError("full base commit SHA required")
    if timeout < 1 or timeout > 3600:
        raise AgentRunnerError("timeout must be between 1 and 3600 seconds")
    source = Path(repository).resolve()
    if not source.is_dir():
        raise AgentRunnerError("source repository unavailable")
    root = Path(_git(source, "rev-parse", "--show-toplevel").strip()).resolve()
    if root != source:
        source = root
    _git(source, "cat-file", "-e", f"{base_sha}^{{commit}}")
    if backend == "codex" and os.getenv("AAO_AGENT_PROVIDER") != "codex":
        raise AgentRunnerError("codex backend disabled; CEO provider activation required (AAO_AGENT_PROVIDER=codex)")
    if backend not in {"fixture", "codex"}:
        raise AgentRunnerError("unsupported agent backend")
    identity = backend_identity(backend)
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="aao-agent-run-") as tmp:
        clone = Path(tmp) / "repo"
        clone.mkdir(mode=0o700)
        _git(clone, "init", "--quiet")
        _git(clone, "-c", "protocol.file.allow=always", "fetch", "--depth=1", "--no-tags", "--no-recurse-submodules", str(source), base_sha)
        _git(clone, "-c", "core.hooksPath=/dev/null", "checkout", "--quiet", "--detach", "FETCH_HEAD")
        env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": str(Path(tmp) / "home"), "LANG": "C.UTF-8",
               "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_NO_REPLACE_OBJECTS": "1",
               "GIT_TERMINAL_PROMPT": "0"}
        (Path(tmp) / "home").mkdir(mode=0o700)
        exit_code = 0
        if backend == "fixture":
            path = patch_file or os.getenv("AAO_AGENT_FIXTURE_PATCH")
            if not path:
                raise AgentRunnerError("fixture patch file is required")
            patch = Path(path).read_bytes()
            if len(patch) > 65536:
                raise AgentRunnerError("patch exceeds size limit")
            proc = subprocess.run(["git", "-C", str(clone), "apply", "--binary", "-"], input=patch,
                                  capture_output=True, timeout=timeout, env=env, cwd="/", check=False)
            exit_code = proc.returncode
            if exit_code:
                raise AgentRunnerError("fixture patch did not apply")
        else:
            prompt = ("Fixed safety preamble: edit only inside this repository; do not use network actions; do not commit.\n\n"
                      + instructions)
            output = Path(tmp) / "last-message.txt"
            # Auth comes only from a dedicated CODEX_HOME (never the operator's ~/.codex); its config.toml is ignored.
            codex_home = os.getenv("AAO_AGENT_CODEX_HOME")
            if not codex_home or not Path(codex_home).is_dir():
                raise AgentRunnerError("codex backend requires a dedicated AAO_AGENT_CODEX_HOME")
            release = codex_release()
            (Path(tmp) / "scratch").mkdir(mode=0o700)
            command = agent_jail(
                [str(release / "bin" / "codex"), "exec", "--sandbox", "workspace-write",
                 *codex_sandbox_flags(Path(tmp))[2:],
                 *(["-m", identity["model"]] if identity["model"] else []),
                 "--ephemeral", "--skip-git-repo-check", "--ignore-user-config",
                 "-C", str(clone), "-c", "model_reasoning_effort=medium", "--disable=plugins",
                 "--disable=browser_use", "--disable=computer_use", "--disable=memories",
                 "--output-last-message", str(output), "-"],
                workdir=Path(tmp), codex_home=Path(codex_home).resolve(), release=release)
            try:
                proc = subprocess.run(command, input=prompt, text=True, capture_output=True, timeout=timeout,
                                      env=env, cwd="/", check=False)
            except subprocess.TimeoutExpired as exc:
                raise AgentRunnerError("agent backend timed out") from exc
            exit_code = proc.returncode
            if exit_code:
                raise AgentRunnerError(f"agent backend exited with status {exit_code}")
        try:
            patch = subprocess.run(["git", "-C", str(clone), "diff", "--binary", base_sha], cwd="/", env=env,
                                   stdin=subprocess.DEVNULL, capture_output=True, timeout=10, check=True).stdout.decode("utf-8")
        except (OSError, subprocess.SubprocessError, UnicodeDecodeError) as exc:
            raise AgentRunnerError("failed collecting agent patch") from exc
        # git diff omits untracked files: stage only for diff collection (never commit).
        _git(clone, "add", "-N", "--", ".", timeout=10)
        patch = subprocess.run(["git", "-C", str(clone), "diff", "--binary", base_sha], cwd="/", env=env,
                               stdin=subprocess.DEVNULL, capture_output=True, timeout=10, check=True).stdout.decode("utf-8")
        try:
            details = inspect_patch(patch) if patch else {"patch_sha256": None, "changed_paths": [], "patch_bytes": 0}
        except PatchProposalError as exc:
            raise AgentRunnerError(str(exc)) from exc
        candidate = {}
        if patch and candidate_store is not None:
            candidate = _commit_candidate(clone, env, author_email=author_email, message=commit_message,
                                          store=Path(candidate_store).resolve(),
                                          changed_paths=list(details["changed_paths"]), check_id=check_id)
        return {"patch": patch, **details, **candidate, **identity,
                "elapsed_seconds": round(time.monotonic() - started, 3), "exit_status": exit_code}
