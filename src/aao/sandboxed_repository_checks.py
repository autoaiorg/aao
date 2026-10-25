"""Run a small, fixed set of repository checks in a read-only Linux sandbox.

This is a local development executor, not a general-purpose command runner.
Candidate source and tests are mounted read-only; the sandbox has no network,
home directory, repository metadata, or inherited credentials.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import time
from pathlib import Path

CHECKS: dict[str, tuple[str, ...]] = {
    "core-unit": (
        "tests/test_core.py",
        "tests/test_planner.py",
        "tests/test_review.py",
        "tests/test_authorization.py",
        "tests/test_identity.py",
        "tests/test_execution.py",
        "tests/test_agent_runner.py",
        "tests/test_pr_publisher.py",
    ),
}
_EXTRA_TEST = re.compile(r"^tests/test_[A-Za-z0-9_]+\.py$")
_OUTPUT_LIMIT = 12_000
_TIMEOUT_SECONDS = 120


class RepositoryCheckError(RuntimeError):
    """A repository check could not be safely started or identified."""


def _candidate_sha(repository: Path) -> str:
    try:
        sha = subprocess.run(
            ["git", "-C", str(repository), "rev-parse", "--verify", "HEAD^{commit}"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
            env={
                "PATH": "/usr/bin:/bin",
                "HOME": "/nonexistent",
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": "/dev/null",
                "GIT_OPTIONAL_LOCKS": "0",
            },
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "-C", str(repository), "status", "--porcelain", "--untracked-files=all"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
            env={
                "PATH": "/usr/bin:/bin",
                "HOME": "/nonexistent",
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": "/dev/null",
                "GIT_OPTIONAL_LOCKS": "0",
            },
        ).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        raise RepositoryCheckError("candidate revision is unavailable") from exc
    if len(sha) != 40 or any(character not in "0123456789abcdef" for character in sha):
        raise RepositoryCheckError("candidate revision is not a full Git SHA")
    if dirty:
        raise RepositoryCheckError("candidate worktree must be clean before checks")
    return sha


def _required_path(repository: Path, relative: str, *, directory: bool) -> Path:
    target = (repository / relative).resolve()
    if not target.is_relative_to(repository) or not (
        target.is_dir() if directory else target.is_file()
    ):
        raise RepositoryCheckError(f"required candidate path is unavailable: {relative}")
    return target


def _build_command(repository: Path, check_id: str, site_packages: Path,
                   extra_tests: tuple[str, ...] = ()) -> list[str]:
    files = CHECKS.get(check_id)
    if files is None:
        raise RepositoryCheckError("unsupported repository check")
    if any(not _EXTRA_TEST.fullmatch(test) for test in extra_tests):
        raise RepositoryCheckError("extra tests must be top-level tests/test_*.py files")
    files = tuple(dict.fromkeys((*files, *extra_tests)))
    if sys.platform != "linux":
        raise RepositoryCheckError("Linux bubblewrap is required")
    bwrap = shutil.which("bwrap")
    timeout = shutil.which("timeout")
    prlimit = shutil.which("prlimit")
    if not bwrap or not timeout or not prlimit:
        raise RepositoryCheckError("bubblewrap, timeout, and prlimit are required")
    python_root = Path(sys.base_prefix).resolve()
    python = python_root / "bin" / "python3"
    if not python.is_file():
        raise RepositoryCheckError("system Python interpreter is unavailable")

    src = _required_path(repository, "src", directory=True)
    tests = _required_path(repository, "tests", directory=True)
    config = _required_path(repository, "pyproject.toml", directory=False)
    packages = site_packages.resolve()
    if not packages.is_dir():
        raise RepositoryCheckError("Python test dependencies are unavailable")
    for test_file in files:
        _required_path(repository, test_file, directory=False)

    command = [
        bwrap,
        "--unshare-all",
        "--die-with-parent",
        "--new-session",
        "--ro-bind",
        "/usr",
        "/usr",
        "--ro-bind",
        "/bin",
        "/bin",
        "--ro-bind",
        "/lib",
        "/lib",
        "--ro-bind",
        "/lib64",
        "/lib64",
        "--ro-bind",
        "/etc",
        "/etc",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--size",
        "268435456",
        "--tmpfs",
        "/tmp",
        "--dir",
        "/tmp/home",
        "--dir",
        "/opt",
        "--ro-bind",
        str(python_root),
        "/opt/aao-python",
        "--ro-bind",
        str(packages),
        "/opt/aao-site-packages",
        "--dir",
        "/workspace",
        "--ro-bind",
        str(src),
        "/workspace/src",
        "--ro-bind",
        str(tests),
        "/workspace/tests",
        "--ro-bind",
        str(config),
        "/workspace/pyproject.toml",
        "--chdir",
        "/workspace",
        "--setenv",
        "HOME",
        "/tmp/home",
        "--setenv",
        "TMPDIR",
        "/tmp",
        "--setenv",
        "PATH",
        "/usr/bin:/bin",
        "--setenv",
        "PYTHONPATH",
        "/workspace/src:/opt/aao-site-packages",
        "--setenv",
        "PYTHONHOME",
        "/opt/aao-python",
        # A shared-libpython interpreter (e.g. CI's hostedtoolcache) must load its own
        # libpython, not a different patch release from /usr.
        *(("--setenv", "LD_LIBRARY_PATH", "/opt/aao-python/lib")
          if any((python_root / "lib").glob("libpython3*.so*")) else ()),
        "--setenv",
        "PYTHONDONTWRITEBYTECODE",
        "1",
        "--setenv",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD",
        "1",
        timeout,
        "--signal=TERM",
        "--kill-after=5",
        f"{_TIMEOUT_SECONDS}s",
        prlimit,
        "--cpu=90",
        "--as=1073741824",
        "--fsize=8388608",
        "--nproc=64",
        "--nofile=64",
        "--",
        "/opt/aao-python/bin/python3",
        "-B",
        "-m",
        "pytest",
        "-q",
        "-p",
        "no:cacheprovider",
        *files,
    ]
    return command


def run_repository_check(repository: str | Path, check_id: str,
                         extra_tests: tuple[str, ...] = ()) -> dict[str, object]:
    """Run one allow-listed unit check (plus candidate test files) tied to HEAD."""
    root = Path(repository).resolve()
    if not root.is_dir():
        raise RepositoryCheckError("candidate repository is unavailable")
    sha = _candidate_sha(root)
    site_packages = Path(sysconfig.get_paths()["purelib"])
    command = _build_command(root, check_id, site_packages, extra_tests)
    started = time.monotonic()
    try:
        with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
            result = subprocess.run(
                command,
                stdin=subprocess.DEVNULL,
                stdout=stdout_file,
                stderr=stderr_file,
                timeout=_TIMEOUT_SECONDS + 10,
                check=False,
                cwd="/",
                env={"PATH": "/usr/bin:/bin", "HOME": "/nonexistent", "LANG": "C.UTF-8"},
            )
            stdout_file.seek(0, 2)
            stdout_size = stdout_file.tell()
            stdout_file.seek(max(0, stdout_size - _OUTPUT_LIMIT))
            stdout = stdout_file.read().decode("utf-8", errors="replace")
            stderr_file.seek(0, 2)
            stderr_size = stderr_file.tell()
            stderr_file.seek(max(0, stderr_size - _OUTPUT_LIMIT))
            stderr = stderr_file.read().decode("utf-8", errors="replace")
    except subprocess.TimeoutExpired as exc:
        raise RepositoryCheckError("sandbox supervisor exceeded its hard timeout") from exc
    elapsed_ms = round((time.monotonic() - started) * 1000)
    if _candidate_sha(root) != sha:
        raise RepositoryCheckError("candidate revision changed while checks were running")
    return {
        "kind": "aao.repository-check.v1",
        "check_id": check_id,
        "extra_tests": list(extra_tests),
        "candidate_sha": sha,
        "conclusion": "success" if result.returncode == 0 else "failure",
        "exit_code": result.returncode,
        "duration_ms": elapsed_ms,
        "stdout": ("[output truncated]\n" if stdout_size > _OUTPUT_LIMIT else "") + stdout,
        "stderr": ("[output truncated]\n" if stderr_size > _OUTPUT_LIMIT else "") + stderr,
        "limits": {
            "network": "unshared",
            "source": "read-only mounted source/tests/config",
            "home_and_secrets": "not mounted; environment allow-listed",
            "timeout_seconds": _TIMEOUT_SECONDS,
            "memory_bytes": 1_073_741_824,
            "temporary_filesystem_bytes": 268_435_456,
        },
    }
