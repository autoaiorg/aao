from __future__ import annotations

import io
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


def test_pm_token_kind_maps_to_coordinator_file_only_for_aao_pm(monkeypatch, tmp_path):
    monkeypatch.setattr(install, "RUNTIME_ROOT", tmp_path / "run")
    uid = os.getuid()
    runtime = tmp_path / "run" / str(uid)
    runtime.mkdir(parents=True, mode=0o700)
    runtime.chmod(0o700)
    monkeypatch.setattr(install.pwd, "getpwnam", lambda _name: SimpleNamespace(pw_uid=uid))
    monkeypatch.setattr(install.os, "geteuid", lambda: uid)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime))

    assert install.target_path("aao-pm", "pm") == runtime / "aao-pm.token"
    assert install.target_path("aao-pm", "publisher") == runtime / "aao-publisher.token"
    assert install.target_path("aao-impl-codex") == runtime / "aao-publisher.token"
    with pytest.raises(install.TokenInstallError, match="unsupported token kind"):
        install.target_path("aao-impl-codex", "pm")
    with pytest.raises(install.TokenInstallError, match="unsupported token kind"):
        install.target_path("aao-pm", "ceo")


def test_selfdev_tokens_are_separate_and_bound_to_their_role(monkeypatch, tmp_path):
    monkeypatch.setattr(install, "RUNTIME_ROOT", tmp_path / "run")
    uid = os.getuid()
    uids = {"aao-impl-codex": uid, "aao-auditor": uid + 1}
    monkeypatch.setattr(install.pwd, "getpwnam", lambda name: SimpleNamespace(pw_uid=uids[name]))
    monkeypatch.setattr(install.os, "geteuid", lambda: uid)
    runtime = tmp_path / "run" / str(uid)
    runtime.mkdir(parents=True, mode=0o700)
    runtime.chmod(0o700)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime))
    assert install.target_path("aao-impl-codex", "selfdev-implementer") == (
        runtime / "aao-self-development-agent.token"
    )
    with pytest.raises(install.TokenInstallError, match="unsupported token kind"):
        install.target_path("aao-impl-codex", "selfdev-reviewer")
    with pytest.raises(install.TokenInstallError, match="unsupported token kind"):
        install.target_path("aao-auditor", "selfdev-implementer")
    with pytest.raises(install.TokenInstallError, match="unsupported token kind"):
        install.target_path("aao-auditor", "publisher")


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


# --- atomic replace -------------------------------------------------------

SELFDEV = "aao-self-development-agent.token"


def _runtime(tmp_path):
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)
    runtime.chmod(0o700)
    return runtime


def _temps(runtime):
    return sorted(p.name for p in runtime.iterdir() if p.name.endswith(".tmp"))


def test_replace_overwrites_atomically_with_a_new_private_inode(tmp_path):
    path = _runtime(tmp_path) / SELFDEV
    install.install(path, "old-token")
    old_inode = path.stat().st_ino

    install.replace(path, "new-token")

    assert path.read_text() == "new-token\n"
    info = path.stat()
    assert stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1
    assert info.st_ino != old_inode  # renamed over, not written in place
    assert _temps(path.parent) == []
    install.verify(path, "new-token")


def test_replace_creates_target_when_absent(tmp_path):
    path = _runtime(tmp_path) / SELFDEV
    install.replace(path, "first-token")
    install.verify(path, "first-token")


def test_install_still_refuses_overwrite_after_replace(tmp_path):
    path = _runtime(tmp_path) / SELFDEV
    install.replace(path, "first-token")
    with pytest.raises(install.TokenInstallError, match="refusing overwrite"):
        install.install(path, "second-token")


def test_replace_refuses_identical_token(tmp_path):
    path = _runtime(tmp_path) / SELFDEV
    install.install(path, "same-token")
    with pytest.raises(install.TokenInstallError, match="equals the installed token"):
        install.replace(path, "same-token")
    install.verify(path, "same-token")


def test_replace_fsyncs_file_before_rename_and_directory_after(monkeypatch, tmp_path):
    path = _runtime(tmp_path) / SELFDEV
    install.install(path, "old-token")
    events = []
    real_fsync, real_replace = os.fsync, os.replace
    monkeypatch.setattr(install.os, "fsync", lambda fd: (events.append("fsync"), real_fsync(fd))[1])
    monkeypatch.setattr(
        install.os,
        "replace",
        lambda *a, **kw: (events.append("replace"), real_replace(*a, **kw))[1],
    )
    install.replace(path, "new-token")
    assert events == ["fsync", "replace", "fsync"]


@pytest.mark.parametrize("failing", ["write", "fsync", "replace"])
def test_crash_before_rename_leaves_old_file_intact_and_no_temp(monkeypatch, tmp_path, failing):
    path = _runtime(tmp_path) / SELFDEV
    install.install(path, "old-token")
    real_write = os.write

    def partial_write(fd, data):
        real_write(fd, bytes(data[:3]))
        raise OSError("simulated crash mid-write")

    def boom(*_a, **_kw):
        raise OSError("simulated crash")

    monkeypatch.setattr(install.os, failing, partial_write if failing == "write" else boom)
    with pytest.raises(OSError, match="simulated crash"):
        install.replace(path, "new-token")
    monkeypatch.undo()
    install.verify(path, "old-token")
    assert _temps(path.parent) == []


def test_leftover_temp_from_hard_crash_is_cleaned_on_next_run(tmp_path):
    runtime = _runtime(tmp_path)
    path = runtime / SELFDEV
    install.install(path, "old-token")
    stale = runtime / f".{SELFDEV}.deadbeef.tmp"
    stale.write_text("partial")
    unrelated = runtime / ".aao-pm.token.deadbeef.tmp"
    unrelated.write_text("not ours")

    install.replace(path, "new-token")

    assert not stale.exists()
    assert unrelated.exists()
    install.verify(path, "new-token")


def test_replace_refuses_preexisting_temp_name_with_o_excl(monkeypatch, tmp_path):
    runtime = _runtime(tmp_path)
    path = runtime / SELFDEV
    install.install(path, "old-token")
    planted = runtime / f".{SELFDEV}.fixed.tmp"

    def plant(_n):
        planted.write_text("attacker")  # appears after stale cleanup, before open
        return "fixed"

    monkeypatch.setattr(install.secrets, "token_hex", plant)
    with pytest.raises(install.TokenInstallError, match="already exists"):
        install.replace(path, "new-token")
    assert planted.read_text() == "attacker"
    install.verify(path, "old-token")


def test_replace_refuses_symlink_target(tmp_path):
    runtime = _runtime(tmp_path)
    path = runtime / SELFDEV
    elsewhere = tmp_path / "elsewhere"
    elsewhere.write_text("leave unchanged")
    path.symlink_to(elsewhere)
    with pytest.raises(install.TokenInstallError, match="not a regular file"):
        install.replace(path, "new-token")
    assert path.is_symlink() and elsewhere.read_text() == "leave unchanged"
    assert _temps(runtime) == []


def test_replace_refuses_non_regular_target(tmp_path):
    runtime = _runtime(tmp_path)
    os.mkfifo(runtime / SELFDEV)
    with pytest.raises(install.TokenInstallError, match="not a regular file"):
        install.replace(runtime / SELFDEV, "new-token")


@pytest.mark.parametrize("problem", ["mode", "hardlink"])
def test_replace_refuses_unsafe_existing_file(tmp_path, problem):
    path = _runtime(tmp_path) / SELFDEV
    install.install(path, "old-token")
    if problem == "mode":
        path.chmod(0o640)
    else:
        os.link(path, tmp_path / "second-link")
    with pytest.raises(install.TokenInstallError, match="not private"):
        install.replace(path, "new-token")
    assert path.read_text() == "old-token\n"


def test_replace_refuses_unsafe_directory(monkeypatch, tmp_path):
    runtime = _runtime(tmp_path)
    runtime.chmod(0o750)
    with pytest.raises(install.TokenInstallError, match="directory ownership or mode"):
        install.replace(runtime / SELFDEV, "new-token")
    runtime.chmod(0o700)
    monkeypatch.setattr(install.os, "geteuid", lambda: os.getuid() + 1)
    with pytest.raises(install.TokenInstallError, match="directory ownership or mode"):
        install.replace(runtime / SELFDEV, "new-token")
    link = tmp_path / "link"
    link.symlink_to(runtime)
    monkeypatch.undo()
    with pytest.raises(install.TokenInstallError, match="unavailable or a symlink"):
        install.replace(link / SELFDEV, "new-token")
    assert list(runtime.iterdir()) == []


def _run_main(monkeypatch, path, argv, secret):
    monkeypatch.setattr(install, "target_path", lambda _a, _t="publisher": path)
    monkeypatch.setattr(install.sys, "argv", ["installer", *argv])
    monkeypatch.setattr(install.sys, "stdin", io.TextIOWrapper(io.BytesIO(secret.encode())))
    return install.main()


def test_cli_replace_never_displays_token(monkeypatch, tmp_path, capsys):
    path = _runtime(tmp_path) / SELFDEV
    install.install(path, "old-secret-value")
    argv = ["--account", "aao-impl-codex", "--token", "selfdev-implementer", "--replace"]
    assert _run_main(monkeypatch, path, argv, "new-secret-value\n") == 0
    assert _run_main(monkeypatch, path, argv, "new-secret-value\n") == 1  # identical
    out = capsys.readouterr()
    for secret in ("old-secret-value", "new-secret-value"):
        assert secret not in out.out + out.err
        assert secret not in " ".join(install.sys.argv)
        assert secret not in str(os.environ)
    install.verify(path, "new-secret-value")


@pytest.mark.parametrize("kind", ["publisher", "pm"])
def test_cli_replace_is_limited_to_selfdev_tokens(monkeypatch, tmp_path, capsys, kind):
    path = _runtime(tmp_path) / "aao-publisher.token"
    argv = ["--account", "aao-pm", "--token", kind, "--replace"]
    assert _run_main(monkeypatch, path, argv, "secret-value\n") == 1
    assert "only supported for Self Development" in capsys.readouterr().err
    assert not path.exists()
