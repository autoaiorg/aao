"""Run a bounded agent against a disposable clone and return its patch evidence."""
from __future__ import annotations

import os
import re
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
        raise AgentRunnerError("configured source repository or base revision unavailable")
    return p.stdout

def run_agent_patch(repository, base_sha: str, instructions: str, *, backend: str,
                    timeout: int, patch_file: str | None = None) -> dict:
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
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="aao-agent-run-") as tmp:
        clone = Path(tmp) / "repo"
        clone.mkdir(mode=0o700)
        _git(clone, "init", "--quiet")
        _git(clone, "-c", "protocol.file.allow=always", "fetch", "--no-tags", "--no-recurse-submodules", str(source), base_sha)
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
            command = ["codex", "exec", "--sandbox", "workspace-write", "--ephemeral", "--skip-git-repo-check",
                       "-C", str(clone), "-c", "model_reasoning_effort=medium", "--disable=plugins",
                       "--disable=browser_use", "--disable=computer_use", "--disable=memories",
                       "--output-last-message", str(output), "-"]
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
        return {"patch": patch, **details, "backend": backend, "backend_version": "codex-cli" if backend == "codex" else "fixture-v1",
                "elapsed_seconds": round(time.monotonic() - started, 3), "exit_status": exit_code}
