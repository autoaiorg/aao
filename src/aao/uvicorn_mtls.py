"""Uvicorn H11 adapter for verified TLS client-certificate identity.

This exposes only a SHA-256 certificate fingerprint that the TLS layer has
already authenticated. It does not map that fingerprint to an AAO principal;
the application must resolve and authorize it against the database.
"""

from __future__ import annotations

import hashlib
from typing import Any

from uvicorn.protocols.http.h11_impl import H11Protocol

MTLS_CLIENT_CERT_EXTENSION = "aao.verified_mtls_client_cert"


def verified_peer_fingerprint(ssl_object: Any) -> str | None:
    """Return the SHA-256 fingerprint of a TLS peer certificate, if present.

    Certificate-chain and client-auth verification must be enforced by the
    listener's SSLContext (CERT_REQUIRED and a controlled client CA). This
    helper deliberately does not trust HTTP headers or certificate names.
    """
    if ssl_object is None:
        return None
    try:
        certificate_der = ssl_object.getpeercert(binary_form=True)
    except (AttributeError, OSError, ValueError):
        return None
    if not isinstance(certificate_der, bytes) or not certificate_der:
        return None
    return hashlib.sha256(certificate_der).hexdigest()


class MtlsH11Protocol(H11Protocol):
    """Attach the authenticated TLS peer fingerprint to the ASGI scope."""

    def connection_made(self, transport) -> None:
        super().connection_made(transport)
        fingerprint = verified_peer_fingerprint(transport.get_extra_info("ssl_object"))
        if fingerprint is None:
            return

        app = self.app

        async def app_with_certificate(scope, receive, send):
            scoped = dict(scope)
            extensions = dict(scope.get("extensions", {}))
            extensions[MTLS_CLIENT_CERT_EXTENSION] = {
                "sha256": fingerprint,
            }
            scoped["extensions"] = extensions
            await app(scoped, receive, send)

        # Uvicorn creates one HTTP protocol per TLS connection. The immutable
        # fingerprint closure is therefore connection-scoped, not request data.
        self.app = app_with_certificate
