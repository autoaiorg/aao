from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UNIT_PATHS = (
    ROOT / "deploy/systemd/user/aao-project-coordinator@.service",
    ROOT / "deploy/systemd/user/aao-selfdev-codex-worker.service",
)
EXPECTED_CREDENTIALS = {
    "client-cert": "client-cert.pem",
    "client-key": "client-key.pem",
    "server-ca": "server-ca.pem",
}


def _directives(unit: str, name: str) -> list[str]:
    return [line.split("=", 1)[1] for line in unit.splitlines() if line.startswith(f"{name}=")]


def test_production_workload_units_fail_closed_and_use_mtls() -> None:
    for path in UNIT_PATHS:
        unit = path.read_text()
        exec_start = _directives(unit, "ExecStart")
        assert len(exec_start) == 1
        # systemd applies EnvironmentFile after Environment=, so the final
        # command sets security-critical values via env immediately before exec.
        assert exec_start[0].startswith(
            "/usr/bin/env AAO_ENV=production "
            "AAO_API_BASE_URL=https://127.0.0.1:8443 "
        )
        assert "ConditionPathIsDirectory=%h/.config/aao/workload-tls" in unit
        assert "aao-self-development-agent.token" not in unit
        assert "aao-pm.token" not in unit

        credential_directives = _directives(unit, "LoadCredential")
        assert len(credential_directives) == len(EXPECTED_CREDENTIALS)
        for credential_name, filename in EXPECTED_CREDENTIALS.items():
            assert f"ConditionPathExists=%h/.config/aao/workload-tls/{filename}" in unit
            assert (
                f"{credential_name}:%h/.config/aao/workload-tls/{filename}"
                in credential_directives
            )


def test_workload_units_do_not_enable_production_bearer_fallback() -> None:
    for path in UNIT_PATHS:
        unit = path.read_text()
        assert "AAO_ENV=development" not in unit
        assert "X-Agent-Token" not in unit
        assert not any("token" in line.lower() for line in _directives(unit, "LoadCredential"))
