"""CEO governance script keeps each run's output under a private state directory."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts/governance/ceo_session.sh"


def _invoke(home: Path, *, state_home: Path | None = None, session_root: str | None = None):
    env = os.environ.copy()
    env["HOME"] = str(home)
    env.pop("XDG_STATE_HOME", None)
    env.pop("AAO_SESSION_ROOT", None)
    if state_home is not None:
        env["XDG_STATE_HOME"] = str(state_home)
    if session_root is not None:
        env["AAO_SESSION_ROOT"] = session_root
    return subprocess.run([str(SCRIPT), "invalid-command"], env=env, capture_output=True, check=False)


def test_sessions_default_to_xdg_state_and_are_unique_and_private(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    result1 = _invoke(home)
    result2 = _invoke(home)

    assert result1.returncode == result2.returncode == 2
    session_root = home / ".local/state/aao/sessions"
    sessions = sorted(session_root.glob("????/??/*"))
    assert len(sessions) == 2
    assert all(path.is_dir() and re.fullmatch(r"\d{8}T\d{6}Z-[A-Za-z0-9]{8}", path.name) for path in sessions)
    assert all(path.stat().st_mode & 0o777 == 0o700 for path in sessions)
    assert not list(home.glob("aao-session-*"))


def test_xdg_state_home_and_explicit_session_root_are_honored(tmp_path):
    home = tmp_path / "home"
    xdg = tmp_path / "xdg-state"
    home.mkdir()
    xdg.mkdir()
    result = _invoke(home, state_home=xdg)
    assert result.returncode == 2
    assert len(list((xdg / "aao/sessions").glob("????/??/*"))) == 1

    explicit = tmp_path / "explicit-sessions"
    result = _invoke(home, session_root=str(explicit))
    assert result.returncode == 2
    assert len(list(explicit.glob("????/??/*"))) == 1


def test_relative_session_paths_are_rejected_before_creating_output(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    result = _invoke(home, session_root="relative/sessions")
    assert result.returncode == 2
    assert b"AAO_SESSION_ROOT must be an absolute path" in result.stderr
    assert not (home / ".local/state/aao/sessions").exists()
