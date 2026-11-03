"""Dedicated production mTLS listener for non-human AAO workloads."""

from __future__ import annotations

import os
from pathlib import Path

import uvicorn

from aao.uvicorn_mtls import MtlsH11Protocol


def build_config(*, credentials_dir: str | None = None) -> uvicorn.Config:
    """Build a fail-closed mTLS-only Uvicorn config from systemd credentials."""
    if os.environ.get("AAO_ENV", "").strip().lower() != "production":
        raise RuntimeError("workload API listener requires AAO_ENV=production")

    credential_root = credentials_dir or os.environ.get("CREDENTIALS_DIRECTORY")
    if not credential_root:
        raise RuntimeError("systemd credential directory is required")
    root = Path(credential_root)
    required = {
        "server-cert": root / "server-cert",
        "server-key": root / "server-key",
        "client-ca": root / "client-ca",
    }
    for name, path in required.items():
        if not path.is_file():
            raise RuntimeError(f"required workload TLS credential missing: {name}")

    return uvicorn.Config(
        "aao.work_management_api:app",
        host="127.0.0.1",
        port=8443,
        http=MtlsH11Protocol,
        ssl_certfile=str(required["server-cert"]),
        ssl_keyfile=str(required["server-key"]),
        ssl_ca_certs=str(required["client-ca"]),
        ssl_cert_reqs=2,  # ssl.CERT_REQUIRED
        log_level="info",
        access_log=False,
    )


def main() -> None:
    uvicorn.Server(build_config()).run()


if __name__ == "__main__":
    main()
