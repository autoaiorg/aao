from __future__ import annotations

import os
import stat
from types import SimpleNamespace

import pytest

from scripts import install_publisher_token_for_role as install


def test_target_path_requires_exact_role_owned_private_runtime(monkeypatch, tmp_path):
    monkeypatch.setattr(install, "RUNTIME_ROOT", tmp_path / "run")
    uid = os.getuid()
    runtime = tmp_path / "run" / str(uid)
    runtime.mkdir(parents=True, mode=0o700)
    runtime.chmod(0o700)
    monkeypatch.setattr(install.pwd, "getpwnam", lambda _name: SimpleNamespace(pw_uid=uid))
    monkeypatch.setattr(install.os, "geteuid", lambda: uid)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime))

    assert install.target_path("aao-pm") == runtime / "aao-publisher.token"

    runtime.chmod(0o750)
    with pytest.raises(install.TokenInstallError, match="ownership or mode"):
        install.target_path("aao-pm")


def test_target_path_rejects_other_account_and_other_runtime(monkeypatch, tmp_path):
    monkeypatch.setattr(install, "RUNTIME_ROOT", tmp_path)
    with pytest.raises(install.TokenInstallError, match="unsupported"):
        install.target_path("aao-integrator")


def test_install_is_private_and_refuses_overwrite(tmp_path):
    path = tmp_path / "aao-publisher.token"
    install.install(path, "non-displayed-token")

    assert path.read_text() == "non-displayed-token\n"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    with pytest.raises(install.TokenInstallError, match="refusing overwrite"):
        install.install(path, "different-token")


def test_verify_requires_exact_token_and_private_regular_file(tmp_path):
    path = tmp_path / "aao-publisher.token"
    install.install(path, "non-displayed-token")
    install.verify(path, "non-displayed-token")

    with pytest.raises(install.TokenInstallError, match="does not match"):
        install.verify(path, "wrong-token")
    path.chmod(0o644)
    with pytest.raises(install.TokenInstallError, match="does not match"):
        install.verify(path, "non-displayed-token")


def test_install_rejects_symlink(tmp_path):
    path = tmp_path / "aao-publisher.token"
    target = tmp_path / "target"
    target.write_text("leave unchanged")
    path.symlink_to(target)

    with pytest.raises(install.TokenInstallError, match="refusing overwrite"):
        install.install(path, "non-displayed-token")
    assert target.read_text() == "leave unchanged"
