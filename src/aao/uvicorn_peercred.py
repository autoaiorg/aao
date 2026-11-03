"""Uvicorn H11 protocol adapter for kernel-authenticated Unix peer identity.

This only attests the UID/GID/PID of a local AF_UNIX connection. It does not
map that identity to an AAO principal or grant access by itself.
"""

from __future__ import annotations

import socket
import struct
from typing import Any

from uvicorn.protocols.http.h11_impl import H11Protocol

PEER_CREDENTIALS_EXTENSION = "aao.peer_credentials"
_PEERCRED_SIZE = struct.calcsize("3i")


def read_peer_credentials(sock: Any) -> dict[str, int] | None:
    """Return kernel-provided peer credentials for a connected Unix socket."""
    if getattr(sock, "family", None) != socket.AF_UNIX:
        return None
    if not hasattr(socket, "SO_PEERCRED"):
        return None
    try:
        pid, uid, gid = struct.unpack(
            "3i", sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, _PEERCRED_SIZE)
        )
    except (OSError, struct.error):
        return None
    if pid <= 0 or uid < 0 or gid < 0:
        return None
    return {"pid": pid, "uid": uid, "gid": gid}


class PeerCredH11Protocol(H11Protocol):
    """Add an unforgeable-by-HTTP scope extension on AF_UNIX connections."""

    def connection_made(self, transport) -> None:
        super().connection_made(transport)
        peer = read_peer_credentials(transport.get_extra_info("socket"))
        if peer is None:
            return

        app = self.app

        async def app_with_peer(scope, receive, send):
            scoped = dict(scope)
            extensions = dict(scope.get("extensions", {}))
            extensions[PEER_CREDENTIALS_EXTENSION] = peer.copy()
            scoped["extensions"] = extensions
            await app(scoped, receive, send)

        # One protocol instance is created per connection; the closure therefore
        # cannot leak one connection's UID to another request/socket.
        self.app = app_with_peer
