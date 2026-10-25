import subprocess
from pathlib import Path

import pytest

from aao.sandboxed_repository_checks import (
    RepositoryCheckError,
    _build_command,
    _candidate_sha,
    run_repository_check,
)


def _git(repository: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _candidate(repository: Path) -> None:
    (repository / "src").mkdir()
    (repository / "tests").mkdir()
    (repository / "src" / "module.py").write_text("value = 1\n", encoding="utf-8")
    (repository / "tests" / "test_module.py").write_text(
        "def test_value(): assert True\n", encoding="utf-8"
    )
    for name in (
        "test_core.py",
        "test_planner.py",
        "test_review.py",
        "test_authorization.py",
        "test_identity.py",
        "test_execution.py",
    ):
        (repository / "tests" / name).write_text(
            "def test_candidate(): assert True\n", encoding="utf-8"
        )
    (repository / "pyproject.toml").write_text("[project]\nname='candidate'\n", encoding="utf-8")
    _git(repository, "init", "-q")
    _git(
        repository, "-c", "user.name=AAO test", "-c", "user.email=test@example.invalid", "add", "."
    )
    _git(
        repository,
        "-c",
        "user.name=AAO test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-qm",
        "candidate",
    )


def test_check_requires_a_clean_full_git_revision(tmp_path: Path):
    _candidate(tmp_path)
    assert _candidate_sha(tmp_path) == _git(tmp_path, "rev-parse", "HEAD")

    (tmp_path / "src" / "module.py").write_text("value = 2\n", encoding="utf-8")
    with pytest.raises(RepositoryCheckError, match="must be clean"):
        _candidate_sha(tmp_path)


def test_check_id_is_fixed_and_arbitrary_command_is_rejected(tmp_path: Path):
    _candidate(tmp_path)
    with pytest.raises(RepositoryCheckError, match="unsupported repository check"):
        _build_command(tmp_path, "pytest tests/evil.py", tmp_path)


def test_sandbox_command_has_no_candidate_command_or_secret_mounts(tmp_path: Path):
    _candidate(tmp_path)
    command = _build_command(tmp_path, "core-unit", tmp_path)

    assert "--unshare-all" in command
    assert "--tmpfs" in command
    assert "--ro-bind" in command
    assert "--setenv" in command
    assert "/home" not in command
    assert ".env.local" not in command
    assert "--" in command
    assert (
        command[-6:]
        == [
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            *(
                "tests/test_core.py",
                "tests/test_planner.py",
                "tests/test_review.py",
                "tests/test_authorization.py",
                "tests/test_identity.py",
                "tests/test_execution.py",
            ),
        ][-6:]
    )


def test_fixed_check_runs_inside_bubblewrap_and_returns_candidate_sha(tmp_path: Path):
    _candidate(tmp_path)

    result = run_repository_check(tmp_path, "core-unit")

    assert result["kind"] == "aao.repository-check.v1"
    assert result["candidate_sha"] == _git(tmp_path, "rev-parse", "HEAD")
    if result["conclusion"] == "success":
        assert "6 passed" in result["stdout"]
    else:
        # Some hosted runners install bubblewrap but forbid creating the
        # isolated network namespace. Accept only that explicit fail-closed
        # environment limitation; never treat it as a successful check.
        assert result["exit_code"] != 0
        assert "Failed RTM_NEWADDR: Operation not permitted" in result["stderr"]


def test_run_result_binds_conclusion_to_head_and_bounds_output(tmp_path: Path, monkeypatch):
    _candidate(tmp_path)
    original_run = subprocess.run
    monkeypatch.setattr(
        "aao.sandboxed_repository_checks._build_command", lambda *_: ["fixed-command"]
    )

    def fake_run(arguments, **kwargs):
        if arguments == ["fixed-command"]:
            kwargs["stdout"].write(b"ok\n")
            return subprocess.CompletedProcess(args=arguments, returncode=0)
        return original_run(arguments, **kwargs)

    monkeypatch.setattr(
        "aao.sandboxed_repository_checks.subprocess.run",
        fake_run,
    )

    result = run_repository_check(tmp_path, "core-unit")

    assert result["kind"] == "aao.repository-check.v1"
    assert result["candidate_sha"] == _git(tmp_path, "rev-parse", "HEAD")
    assert result["conclusion"] == "success"
    assert result["stdout"] == "ok\n"
    assert result["limits"]["network"] == "unshared"


def test_extra_tests_must_be_top_level_test_files(tmp_path):
    import pytest

    from aao.sandboxed_repository_checks import RepositoryCheckError, _build_command

    for bad in ("../x.py", "tests/sub/test_x.py", "tests/conftest.py", "src/test_x.py"):
        with pytest.raises(RepositoryCheckError, match="extra tests"):
            _build_command(tmp_path, "core-unit", tmp_path, (bad,))
