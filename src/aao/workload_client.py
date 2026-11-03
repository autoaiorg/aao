"""Fail-closed client transport for production AAO workload requests."""

from __future__ import annotations

import os
import ssl
import urllib.parse
import urllib.request
from pathlib import Path


class WorkloadTransportError(RuntimeError):
    """Safe-to-display client transport configuration error."""


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


def validate_workload_origin(base_url: str) -> None:
    """Require HTTPS in production; allow only loopback HTTP for development."""
    parsed = urllib.parse.urlparse(base_url)
    production = os.environ.get("AAO_ENV", "").strip().lower() == "production"
    if production and parsed.scheme != "https":
        raise WorkloadTransportError("production workload API must use HTTPS")
    if parsed.scheme != "https" and not (
        parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    ):
        raise WorkloadTransportError("workload API must use HTTPS unless it targets localhost")
    if parsed.username or parsed.password or not parsed.hostname or parsed.path or parsed.query or parsed.fragment:
        raise WorkloadTransportError("workload API must be an origin without credentials or path")


def build_workload_opener() -> urllib.request.OpenerDirector:
    """Build an opener; production requires systemd-provided client mTLS credentials."""
    handlers: list[object] = [urllib.request.ProxyHandler({}), _RejectRedirects()]
    if os.environ.get("AAO_ENV", "").strip().lower() == "production":
        credentials_dir = os.environ.get("CREDENTIALS_DIRECTORY")
        if not credentials_dir:
            raise WorkloadTransportError("production workload TLS credentials are unavailable")
        root = Path(credentials_dir)
        cert = root / "client-cert"
        key = root / "client-key"
        ca = root / "server-ca"
        if not all(path.is_file() for path in (cert, key, ca)):
            raise WorkloadTransportError("production workload TLS credentials are incomplete")
        context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=str(ca))
        try:
            context.load_cert_chain(certfile=str(cert), keyfile=str(key))
        except (OSError, ssl.SSLError):
            raise WorkloadTransportError("production workload TLS credentials are invalid") from None
        handlers.append(urllib.request.HTTPSHandler(context=context))
    return urllib.request.build_opener(*handlers)


def workload_headers(token: str | None, *, has_body: bool = True) -> dict[str, str]:
    """In production never send bearer material; development retains legacy auth."""
    headers = {"Accept": "application/json"}
    if has_body:
        headers["Content-Type"] = "application/json"
    if os.environ.get("AAO_ENV", "").strip().lower() == "production":
        if not os.environ.get("CREDENTIALS_DIRECTORY"):
            raise WorkloadTransportError("production workload TLS credentials are unavailable")
        return headers
    if not token:
        raise WorkloadTransportError("development workload bearer credential is required")
    headers["X-Agent-Token"] = token
    return headers
